"""Private operator API and company console for native H cloud probes.

The cloud actor is a capability benchmark, not an interactive coaching session.
Authentication references and account bindings are supplied only by the operator
configuration. Browser requests cannot silently start campaigns.
"""
import hmac
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from starlette.responses import JSONResponse

from pilot.cloud_runtime import CloudTask
from pilot.company_console import mount_company_console
from pilot.control_tower import mount_control_tower
from pilot.sponsor_catalog import get_sponsor_scenario, load_sponsor_catalog


class OperatorAuth:
    def __init__(self, app, token):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        path = scope.get('path', '')
        if path == '/company' or path.startswith('/company/'):
            return await self.app(scope, receive, send)  # Independently gated Basic/CSRF routes.
        headers = dict(scope.get('headers', []))
        try:
            host = urlsplit('//' + headers.get(b'host', b'').decode()).hostname
        except ValueError:
            host = None
        valid = (host in {'localhost', '127.0.0.1', '::1'} and b'origin' not in headers
                 and hmac.compare_digest(headers.get(b'authorization', b''), ('Bearer ' + self.token).encode()))
        if not valid:
            return await JSONResponse({'detail': 'Private operator authentication required'}, status_code=401)(scope, receive, send)
        await self.app(scope, receive, send)


class Campaign(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scenario_ids: list[str] = Field(min_length=1, max_length=10)
    approved: StrictBool = False
    max_parallel: int = Field(default=2, ge=1, le=10, strict=True)
    use_knowledge: StrictBool = False


class HumanFeedback(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirmed_by_human: StrictBool = False
    success: str = Field(pattern='^(yes|partial|no|unknown)$')
    useful: str = Field(pattern='^(yes|no|unknown)$')
    comment: str = Field(default='', max_length=4000)
    training_consent: StrictBool = False


def create_cloud_app(*, private_root, token, runner, knowledge, username, password,
                     historical_sources=(), account_configuration=None, revisions=None):
    private = Path(private_root).resolve()
    cloud = private / 'cloud'
    cloud.mkdir(parents=True, exist_ok=True, mode=0o700)
    account = account_configuration or {}
    campaign_lock = threading.RLock()
    app = FastAPI(title='H-Companion cloud pilot', docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(OperatorAuth, token=token)

    @app.get('/cloud/status')
    def status():
        return {**runner.status(), 'transport': 'h_cloud_browser', 'purpose': 'capability_test',
                'profile_configured': bool(account.get('browser_profile_id')),
                'authentication_verified': account.get('authentication_verified') is True,
                'knowledge_documents': len(knowledge.list_documents()),
                'revisions': revisions or {}}

    @app.get('/cloud/scenarios')
    def scenarios():
        return {'scenarios': load_sponsor_catalog()}

    @app.post('/cloud/campaigns')
    def create_campaign(body: Campaign):
        if body.approved is not True:
            raise HTTPException(409, 'Explicit approval is required before starting cloud sessions.')
        if len(set(body.scenario_ids)) != len(body.scenario_ids):
            raise HTTPException(422, 'Duplicate scenario identifiers.')
        tasks = []
        for scenario_id in body.scenario_ids:
            try:
                scenario = get_sponsor_scenario(scenario_id, bindings=account.get('bindings', {}).get(scenario_id))
                authenticated = scenario['requires_auth']
                if authenticated and not account.get('browser_profile_id'):
                    raise ValueError('This case requires a dedicated authenticated browser profile and explicit demo-session bindings.')
                # Task bindings, not all sessions configured for the account,
                # define the restricted platform pages for this particular run.
                page_urls = tuple(value for name, value in scenario.get('bindings', {}).items()
                                  if name in {'session_url', 'comparison_session_url'}) if authenticated else ()
                context = ''
                if body.use_knowledge:
                    hits = knowledge.search(scenario['prompt'], top_k=6)
                    if not hits:
                        raise ValueError('No documentation matched; import documentation before a retrieval-assisted comparison.')
                    context = '\n\n'.join(
                        f"Source: {hit['citation_uri']}\nSection: {hit['section']}\n{hit['text']}"
                        for hit in hits)
                tasks.append(CloudTask(
                    scenario_id=scenario['id'], source=scenario['source'], title=scenario['title'],
                    question=scenario['prompt'], start_url=scenario['start_url'],
                    allowed_origins=tuple(scenario['allowed_origins']), max_steps=scenario['max_steps'],
                    max_time_s=scenario['max_time_s'],
                    catalog_version=scenario['catalog_version'], comparison_family=scenario['comparison_family'],
                    documentation_context=context,
                    browser_profile_id=account.get('browser_profile_id') if authenticated else None,
                    allowed_page_urls=page_urls,
                    display_allowed_paths=tuple(urlsplit(url).path for url in page_urls),
                ))
            except (ValueError, KeyError) as exc:
                raise HTTPException(422, str(exc)) from None
        with campaign_lock:
            runner.set_parallelism(body.max_parallel)
            # Validate every case before the first external operation. Submit does
            # not retry an ambiguous provider creation or duplicate a started run.
            created = []
            try:
                for task in tasks:
                    created.append(runner.submit(task, approved=True))
            except (RuntimeError, ValueError) as exc:
                raise HTTPException(409, {'message': str(exc), 'started_episode_ids': created}) from None
        return {'episode_ids': created, 'mode': 'act', 'purpose': 'capability_test',
                'simulated': runner.status()['simulated']}

    @app.get('/cloud/episodes')
    def episodes():
        return {'episodes': runner.list_episodes()}

    @app.get('/cloud/episodes/{episode_id}')
    def episode(episode_id: str):
        try:
            return runner.snapshot(episode_id)
        except KeyError:
            raise HTTPException(404, 'Unknown episode') from None

    @app.post('/cloud/episodes/{episode_id}/stop')
    def stop(episode_id: str):
        try:
            return runner.stop(episode_id)
        except KeyError:
            raise HTTPException(404, 'Only a session owned by this runner can be stopped.') from None

    @app.post('/cloud/episodes/{episode_id}/feedback')
    def feedback(episode_id: str, body: HumanFeedback):
        if body.confirmed_by_human is not True:
            raise HTTPException(409, 'Human feedback requires an actual human response.')
        if not re.fullmatch(r'cloud_[a-f0-9]{16}', episode_id):
            raise HTTPException(404, 'Unknown episode')
        current = episode(episode_id)
        if current['state'] not in {'completed', 'failed', 'timed_out', 'interrupted', 'not_started'}:
            raise HTTPException(409, 'Wait until this episode has finished.')
        folder = cloud / 'episodes' / episode_id
        if folder.is_symlink() or not folder.is_dir():
            raise HTTPException(404, 'Unknown episode')
        data = {**body.model_dump(), 'label_source': 'human', 'confirmed_at': datetime.now(timezone.utc).isoformat(),
                'task_success_user': {'yes': 'success', 'no': 'failure', 'partial': 'partial', 'unknown': 'unknown'}[body.success],
                'user_confirmed': True, 'allow_training': body.training_consent,
                'include_for_training': False, 'ready_for_sft': False, 'simulated': bool(current.get('simulated', runner.status()['simulated']))}
        with campaign_lock:
            try:
                with (folder / 'labels.json').open('x') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except FileExistsError:
                raise HTTPException(409, 'Human feedback is already recorded; it has not been overwritten.') from None
        return data

    mount_company_console(app, private_root=cloud, knowledge=knowledge, username=username, password=password,
                          config={'company': 'H-Companion Research', 'software': 'h-company',
                                  'environment': 'public_docs', 'model': 'holo4-35b-a3b',
                                  'transport': 'h_cloud_browser', 'simulated': runner.status()['simulated'],
                                  'control_tower_enabled': True, 'knowledge_enabled': 'Option par campagne · recherche lexicale BM25',
                                  **(revisions or {})},
                          is_busy=lambda: bool(runner.status()['running'] or runner.status()['queued']),
                          mutation_lock=campaign_lock)
    mount_control_tower(app, sources=[{'id': 'h-cloud', 'label': 'H Company · navigateurs H',
                                     'root': cloud, 'software': 'h-company'}, *historical_sources],
                        username=username, password=password)
    app.state.runner = runner
    return app
