"""Private, single-company HTML console. It never runs a computer-use action.

Mount behind a loopback listener. Every route authenticates independently, so the
pilot's bearer middleware may exempt exactly /company and /company/*. Credentials
are supplied by the launcher, never put in a URL or embedded in HTML. This is a
single-private-root viewer, not a multi-tenant authorization boundary.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
from email import policy
from email.parser import BytesParser
from pathlib import Path
import re
import secrets
import threading
import time
from typing import Callable
from urllib.parse import parse_qs, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import HTMLResponse, RedirectResponse

MAX_DOCUMENT_BYTES = 256 * 1024
MAX_FORM_BYTES = MAX_DOCUMENT_BYTES + 16384
SAFE_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$')
COOKIE = 'hcompanion_company_csrf'
PUBLIC_CONFIG = ('company', 'software', 'software_version', 'environment', 'model', 'transport',
                 'engine_revision', 'support_revision', 'allowed_origins', 'domains',
                 'knowledge_enabled', 'simulated')
TERMINAL = {'resolved', 'escalated', 'failed', 'stopped', 'preflight_failed',
            'cancelled', 'interrupted', 'completed'}


def _e(value) -> str:
    return html.escape(str(value if value is not None else 'Non renseigné'), quote=True)


def _verdict(value, default: str = 'Non évalué') -> str:
    """Translate presentation only; persisted labels retain their contract values."""
    if value is None:
        return default
    return {'success': 'Réussi', 'partial': 'Partiel', 'failure': 'Échec',
            'failed': 'Échec', 'unknown': 'Non évalué', 'yes': 'Oui', 'no': 'Non'}.get(str(value), str(value))


def _review_details(rationale) -> str:
    if isinstance(rationale, list):
        points = ''.join('<li>' + _e(point) + '</li>' for point in rationale)
        return ('<details><summary>Lire l’analyse IA (' + str(len(rationale)) +
                ' point(s))</summary><ul>' + points + '</ul></details>')
    if rationale:
        return '<details><summary>Lire l’analyse IA</summary><p>' + _e(rationale) + '</p></details>'
    return '<p>Aucune revue disponible.</p>'


def _safe_json(directory: Path, name: str) -> dict:
    """Never follow episode symlinks or read arbitrary filenames."""
    path = directory / name
    if path.is_symlink() or not path.is_file():
        return {}
    try:
        if path.stat().st_size > 4 * 1024 * 1024:
            return {}
        result = json.loads(path.read_text(encoding='utf-8'))
        return result if isinstance(result, dict) else {}
    except (OSError, UnicodeError, ValueError):
        return {}


def _episodes(root: Path) -> list[dict]:
    base = root / 'episodes'
    if base.is_symlink() or not base.is_dir():
        return []
    records = []
    for directory in base.iterdir():
        if (not SAFE_ID.fullmatch(directory.name) or directory.is_symlink()
                or not directory.is_dir()):
            continue
        # The presence of a quarantine marker is sufficient, even if unreadable.
        quarantined = (directory / 'quarantine.json').exists() or (directory / 'quarantine.json').is_symlink()
        meta = _safe_json(directory, 'episode.json')
        if not meta:
            continue
        row = {'id': directory.name, 'meta': meta, 'quarantined': quarantined}
        if not quarantined:
            row.update(report=_safe_json(directory, 'report.json'),
                       labels=_safe_json(directory, 'labels.json'),
                       review=_safe_json(directory, 'agent-review.json'))
        records.append(row)
    return sorted(records, key=lambda row: str(row['meta'].get('created_at', '')), reverse=True)


def _eligible(row: dict) -> bool:
    meta = row['meta']
    return (not row['quarantined'] and not meta.get('simulated', False)
            and not row.get('report', {}).get('simulated', False)
            and meta.get('state') in TERMINAL and bool(row.get('report')))


async def _form(request: Request) -> dict:
    """Bounded forms without python-multipart (not required by the pilot)."""
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_FORM_BYTES:
            raise HTTPException(413, 'Formulaire trop volumineux.')
    content_type = request.headers.get('content-type', '')
    if len(content_type) > 400:
        raise HTTPException(400, 'Type de formulaire invalide.')
    try:
        if content_type.split(';', 1)[0] == 'application/x-www-form-urlencoded':
            values = parse_qs(bytes(body).decode('utf-8'), keep_blank_values=True, max_num_fields=8)
            if any(len(value) != 1 for value in values.values()):
                raise ValueError('Duplicate fields')
            return {name: value[0] for name, value in values.items()}
        if content_type.startswith('multipart/form-data;'):
            message = BytesParser(policy=policy.default).parsebytes(
                ('Content-Type: ' + content_type + '\r\nMIME-Version: 1.0\r\n\r\n').encode('ascii') + bytes(body))
            if not message.is_multipart() or message.defects:
                raise ValueError('Invalid multipart')
            fields = {}
            parts = list(message.iter_parts())
            if len(parts) > 8:
                raise ValueError('Too many fields')
            for part in parts:
                name = part.get_param('name', header='content-disposition')
                if not name or name in fields or part.is_multipart() or part.defects:
                    raise ValueError('Invalid field')
                data = part.get_payload(decode=True) or b''
                filename = part.get_filename()
                fields[name] = {'filename': filename, 'content': data} if filename is not None else data.decode('utf-8')
            return fields
    except (UnicodeError, ValueError, TypeError):
        raise HTTPException(400, 'Formulaire invalide.') from None
    raise HTTPException(415, 'Utilisez un formulaire HTML.')


def mount_company_console(app, *, private_root: Path, knowledge, username: str,
                          password: str, config: dict, store=None,
                          is_busy: Callable[[], bool] | None = None, mutation_lock=None):
    """Mount authenticated pages; knowledge implements upload/list_documents/search.

    Config is an explicit safe allowlist, displayed read-only. Store is optional;
    only cases joined to non-quarantined real terminal episodes enter its summary.
    Supply the episode-creation RLock as mutation_lock so uploads cannot race the
    corpus snapshot taken while a new episode is being prepared.
    """
    if not username or len(password) < 16:
        raise ValueError('Company console requires a username and a strong password')
    root = Path(private_root).expanduser().resolve()
    mutation_lock = mutation_lock if mutation_lock is not None else threading.RLock()
    csrf_key = secrets.token_bytes(32)
    router = APIRouter(prefix='/company')

    async def authenticated(request: Request):
        try:
            host = urlsplit('//' + request.headers.get('host', '')).hostname
        except ValueError:
            raise HTTPException(403, 'Hôte invalide.') from None
        if host not in {'localhost', '127.0.0.1', '::1'}:
            raise HTTPException(403, 'Console disponible uniquement sur le serveur local.')
        supplied = request.headers.get('authorization', '')
        valid = False
        try:
            scheme, value = supplied.split(' ', 1)
            user, secret = base64.b64decode(value, validate=True).decode('utf-8').split(':', 1)
            valid = (scheme.lower() == 'basic'
                     and hmac.compare_digest(user.encode(), username.encode())
                     and hmac.compare_digest(secret.encode(), password.encode()))
        except (ValueError, UnicodeError):
            pass
        if not valid:
            raise HTTPException(401, 'Authentification entreprise requise.',
                                headers={'WWW-Authenticate': 'Basic realm="H-Companion entreprise", charset="UTF-8"'})
        origin = request.headers.get('origin')
        expected = f'{request.url.scheme}://{request.headers.get("host", "")}'
        if origin is not None and origin != expected:
            raise HTTPException(403, 'Origine du formulaire refusée.')

    router.dependencies.append(Depends(authenticated))

    def valid_csrf(value: str) -> bool:
        if not isinstance(value, str) or len(value) > 200:
            return False
        try:
            expires, nonce, signature = value.split('.')
            return (time.time() < int(expires) < time.time() + 7200 and len(nonce) == 32
                    and hmac.compare_digest(signature, hmac.new(
                        csrf_key, f'{expires}.{nonce}'.encode(), hashlib.sha256).hexdigest()))
        except (ValueError, TypeError):
            return False

    def csrf(request: Request) -> str:
        value = request.cookies.get(COOKIE, '')
        if valid_csrf(value):
            return value
        value = f'{int(time.time()) + 3600}.{secrets.token_hex(16)}'
        return value + '.' + hmac.new(csrf_key, value.encode(), hashlib.sha256).hexdigest()

    def check_csrf(request: Request, fields: dict):
        value = fields.get('csrf', '')
        cookie = request.cookies.get(COOKIE, '')
        if not valid_csrf(cookie) or not isinstance(value, str) or not hmac.compare_digest(cookie, value):
            raise HTTPException(403, 'Rechargez la page avant de soumettre le formulaire.')

    def page(request: Request, title: str, content: str, *, status_code=200):
        token = csrf(request)
        content = content.replace('<!--CSRF-->', f'<input type="hidden" name="csrf" value="{_e(token)}">')
        if config.get('simulated') is True:
            content = '<p class="badge">Mode simulé · aucun résultat réel de Holo</p>' + content
        response = HTMLResponse('''<!doctype html><html lang="fr"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>''' + _e(title) + ''' · H-Companion</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f5f8f5;color:#18332e;font:16px system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:32px 22px}header{display:flex;gap:24px;align-items:center;flex-wrap:wrap}nav{display:flex;gap:18px;flex-wrap:wrap}a{color:#087b64;overflow-wrap:anywhere}h1{margin-top:36px}h2{font-size:21px}.card{background:white;border:1px solid #d7e3dc;border-radius:12px;padding:22px;margin:18px 0}.muted{color:#536b62}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px}.metric strong{display:block;font-size:30px}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%}th,td{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid #e0e8e2}input,textarea,button{max-width:100%;font:inherit;padding:10px;border-radius:6px;border:1px solid #8da69c}textarea{width:95%;min-height:90px}button{background:#176b57;color:white;cursor:pointer}label{display:block;margin:12px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f5f1;padding:16px}code{overflow-wrap:anywhere}.warning{border-left:5px solid #b97316}.badge{display:inline-block;padding:3px 9px;border-radius:20px;background:#e4eee7}dl{display:grid;grid-template-columns:minmax(130px,220px) 1fr;gap:14px}dd{margin:0;overflow-wrap:anywhere}@media(max-width:600px){dl{grid-template-columns:1fr;gap:6px}dd{margin-bottom:14px}.card{padding:16px}main{padding:24px 16px}}</style>
<main><header><strong>H-Companion · Entreprise</strong><nav><a href="/company">Configuration</a><a href="/company/documents">Documentation</a><a href="/company/sessions">Sessions et retours</a></nav></header><h1>''' + _e(title) + '</h1>' + content +
            '<p class="muted">Console privée · une entreprise · aucun contrôle du bureau depuis ces pages.</p></main></html>', status_code=status_code)
        response.set_cookie(COOKIE, token, max_age=3600, httponly=True, secure=request.url.scheme == 'https', samesite='strict', path='/company')
        response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                                 'Referrer-Policy': 'same-origin', 'X-Frame-Options': 'DENY',
                                 'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"})
        return response

    @router.get('', response_class=HTMLResponse)
    @router.get('/', response_class=HTMLResponse, include_in_schema=False)
    async def configuration(request: Request):
        rows = ''.join(f'<dt>{_e(key)}</dt><dd>{_e(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))}</dd>'
                       for key, value in config.items() if key in PUBLIC_CONFIG)
        return page(request, 'Configuration active', '<section class="card"><dl>' + rows + '</dl></section>'
                    '<section class="card"><h2>Périmètre autorisé</h2><p>Les domaines, le logiciel et le modèle sont définis au lancement du pilote. '
                    'Cette page les affiche sans modifier la politique.</p><p>Les scénarios de cette campagne sont en lecture seule. '
                    'Aucune session, action, réinitialisation ni modification de label ne peut être déclenchée ici.</p></section>')

    def documents_html():
        documents = knowledge.list_documents() if knowledge is not None else []
        rows = ''.join('<tr><td>' + _e(doc.get('filename', doc.get('title', doc.get('document_id', 'Document')))) +
                       '</td><td><code>' + _e(doc.get('document_id')) + '</code></td><td><code title="' +
                       _e(doc.get('sha256')) + '">' + _e(str(doc.get('sha256', ''))[:12]) + '</code></td></tr>' for doc in documents)
        return ('<section class="card"><h2>Sources Markdown</h2><p>Documents locaux de cette entreprise ; les résultats ci-dessous sont des extraits sourcés. '
                'La recherche ne lance pas Holo.</p><div class="scroll"><table><thead><tr><th>Document</th><th>Identifiant</th><th>Version SHA-256</th></tr></thead><tbody>' + rows +
                '</tbody></table></div>' + ('<p>Aucun document chargé.</p>' if not documents else '') + '</section>'
                '<section class="card"><h2>Ajouter une source</h2><form action="/company/documents" method="post" enctype="multipart/form-data"><!--CSRF-->'
                '<label>Fichier Markdown (UTF-8, 256 Kio maximum)<br><input type="file" name="document" accept=".md,.markdown" required></label>'
                '<button>Importer le document</button></form><p class="muted">Import suspendu pendant une session active. Les documents ne doivent contenir aucun secret.</p></section>'
                '<section class="card"><h2>Tester une question</h2><form action="/company/documents/search" method="post"><!--CSRF-->'
                '<label>Question<textarea name="query" maxlength="2000" required></textarea></label><button>Rechercher dans la documentation</button></form></section>')

    @router.get('/documents', response_class=HTMLResponse)
    async def documents(request: Request):
        return page(request, 'Documentation', documents_html())

    @router.post('/documents', response_class=HTMLResponse)
    async def upload(request: Request):
        fields = await _form(request)
        check_csrf(request, fields)
        if knowledge is None:
            raise HTTPException(503, 'Documentation indisponible.')
        document = fields.get('document')
        if not isinstance(document, dict):
            raise HTTPException(422, 'Sélectionnez un fichier Markdown.')
        filename, content = document.get('filename', ''), document.get('content', b'')
        if (not isinstance(filename, str) or not filename or len(filename) > 160
                or any(c in filename for c in '/\\%') or any(ord(c) < 32 for c in filename)
                or Path(filename).suffix.lower() not in {'.md', '.markdown'}):
            raise HTTPException(422, 'Nom de fichier Markdown invalide.')
        if not content or len(content) > MAX_DOCUMENT_BYTES:
            raise HTTPException(413, 'Document vide ou trop volumineux.')
        try:
            content.decode('utf-8')
            with mutation_lock:
                if is_busy and is_busy():
                    raise HTTPException(409, 'Une session est active ; attendez sa fin avant de modifier les documents.')
                knowledge.upload(filename, content)
        except (UnicodeError, ValueError):
            raise HTTPException(422, 'Document Markdown invalide.') from None
        return RedirectResponse('/company/documents', status_code=303)

    @router.post('/documents/search', response_class=HTMLResponse)
    async def search(request: Request):
        fields = await _form(request)
        check_csrf(request, fields)
        query = fields.get('query', '')
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 2000:
            raise HTTPException(422, 'Question requise (2 000 caractères maximum).')
        hits = knowledge.search(query.strip(), top_k=4) if knowledge is not None else []
        result = '<section class="card"><h2>Extraits retrouvés</h2><p>Question : ' + _e(query) + '</p>'
        if not hits:
            result += '<p>Aucun passage pertinent trouvé. Aucune réponse métier ne peut être étayée par ces documents.</p>'
        for hit in hits:
            result += '<article><h3>' + _e(hit.get('section', 'Extrait')) + '</h3><p class="muted">' + _e(hit.get('title', hit.get('document_id', 'Document'))) + '</p><pre>' + _e(hit.get('text', '')) + '</pre>'
            for url in hit.get('source_urls', []):
                try:
                    parsed = urlsplit(str(url))
                except ValueError:
                    continue
                if parsed.scheme in {'https', 'http'} and parsed.hostname and not parsed.username and not parsed.password:
                    result += '<p><a rel="noreferrer noopener" href="' + _e(url) + '">' + _e(url) + '</a></p>'
            result += '<details><summary>Version et provenance</summary><p>Source : <code>' + _e(hit.get('citation_uri', hit.get('document_id'))) + '</code><br>Version : <code>' + _e(hit.get('sha256')) + '</code></p></details></article>'
        return page(request, 'Documentation', result + '</section>' + documents_html())

    @router.get('/sessions', response_class=HTMLResponse)
    async def sessions(request: Request):
        records = _episodes(root)
        eligible = [row for row in records if _eligible(row)]
        human = [row for row in eligible if row['labels'].get('user_confirmed') is True]
        ai = [row for row in eligible if row['review'].get('task_success_agent') in {'success', 'partial', 'failure', 'unknown'}]
        metrics = [('Sessions réelles terminées retenues', len(eligible)),
                   ('Retours humains confirmés', len(human)),
                   ('Revues IA disponibles', len(ai)),
                   ('Sessions en quarantaine', sum(row['quarantined'] for row in records))]
        body = '<div class="grid">' + ''.join('<div class="card metric"><span>' + _e(label) + '</span><strong>' + str(count) + '</strong></div>' for label, count in metrics) + '</div>'
        body += '<p class="muted">Les indicateurs de retours et revues excluent les sessions en quarantaine, simulées et inachevées. '
        body += 'Un verdict IA ne remplace pas un retour humain ; aucune utilité n’est déduite automatiquement.</p>'
        rows = ''
        for row in records:
            meta = row['meta']
            if row['quarantined']:
                rows += '<tr><td><code>' + _e(row['id']) + '</code></td><td colspan="5">Quarantaine · contenu masqué · exclu des indicateurs et de l’entraînement</td></tr>'
                continue
            labels, review = row['labels'], row['review']
            rows += '<tr><td><a href="/company/sessions/' + _e(row['id']) + '">' + _e(meta.get('scenario_id', row['id'])) + '</a><br><small>' + _e(row['id']) + '</small></td>'
            rows += '<td>' + _e(meta.get('state')) + (' · simulée' if meta.get('simulated') else '') + '</td>'
            rows += '<td>' + _e(_verdict(labels.get('task_success_user')) if labels.get('user_confirmed') is True else 'Non recueilli') + '</td>'
            rows += '<td>' + _e(_verdict(labels.get('useful')) if labels.get('user_confirmed') is True else 'Non recueillie') + '</td>'
            rows += '<td>' + _e(_verdict(review.get('task_success_agent'), 'Non revue')) + '</td><td>' + _e(meta.get('export_status', 'Non renseigné')) + '</td></tr>'
        body += '<section class="card scroll"><table><thead><tr><th>Session</th><th>État moteur</th><th>Réussite · humain</th><th>Utilité · humain</th><th>Réussite · revue IA</th><th>Archive</th></tr></thead><tbody>' + rows + '</tbody></table></section>'
        if store is not None:
            try:
                ids = {row['id'] for row in eligible}
                cases = [case for case in store.list_cases() if getattr(case, 'session_id', None) in ids
                         and not getattr(case, 'simulated', False) and not getattr(case, 'demo_data', False)]
                from hcs_backend.grouping import group_cases
                groups = [group.summary() for group in group_cases(cases)]
                body += '<section class="card"><h2>Cas support synchronisés</h2><p>' + str(len(cases)) + ' cas liés aux sessions retenues. Regroupement lexical indicatif.</p>'
                for group in groups:
                    body += '<p><strong>' + _e(group.get('label')) + '</strong> · ' + _e(group.get('n_cases')) + ' cas · ' + _e(group.get('needs_human')) + ' escalade(s)</p>'
                body += '</section>'
            except (ImportError, OSError, ValueError, TypeError, AttributeError):
                body += '<p class="muted">Synthèse du store support indisponible ; les épisodes locaux restent consultables.</p>'
        return page(request, 'Sessions et retours', body)

    @router.get('/sessions/{session_id}', response_class=HTMLResponse)
    async def session(request: Request, session_id: str):
        if not SAFE_ID.fullmatch(session_id):
            raise HTTPException(404, 'Session inconnue.')
        row = next((row for row in _episodes(root) if row['id'] == session_id), None)
        if row is None:
            raise HTTPException(404, 'Session inconnue.')
        if row['quarantined']:
            return page(request, 'Session en quarantaine', '<section class="card warning"><p>Contenu privé masqué. '
                        'Cette session est exclue des indicateurs de résultat et de l’entraînement. Aucune preuve ni transcription n’est servie ici.</p></section>')
        report, labels, review = row['report'], row['labels'], row['review']
        body = '<section class="card"><dl><dt>Session</dt><dd>' + _e(session_id) + '</dd><dt>État moteur</dt><dd>' + _e(row['meta'].get('state')) + '</dd><dt>Demande</dt><dd>' + _e(report.get('goal', row['meta'].get('title'))) + '</dd><dt>Archive</dt><dd>' + _e(row['meta'].get('export_status')) + '</dd></dl></section>'
        body += '<section class="card"><h2>Retour humain</h2><p>Réussite : ' + _e(_verdict(labels.get('task_success_user')) if labels.get('user_confirmed') is True else 'Non recueilli') + ' · Utilité : ' + _e(_verdict(labels.get('useful')) if labels.get('user_confirmed') is True else 'Non recueillie') + '</p><p>' + _e(labels.get('comment', '') if labels.get('user_confirmed') is True else '') + '</p></section>'
        body += '<section class="card"><h2>Revue IA indépendante</h2><p>Réussite : ' + _e(_verdict(review.get('task_success_agent'), 'Non revue')) + ' · Périmètre : ' + _e(_verdict(review.get('scope_compliance_agent'), 'Non revu')) + '</p>' + _review_details(review.get('rationale')) + '<p>Une revue humaine est nécessaire avant toute sélection pour entraînement.</p></section>'
        declared, verification = report.get('declared') or {}, report.get('verification') or {}
        body += '<section class="card"><h2>Rapport moteur</h2><p>Déclaration : ' + _e(declared.get('summary', 'Non renseignée')) + '</p><p>Vérification observée : ' + _e(verification.get('observed', 'Non renseignée')) + '</p><p>Critère satisfait selon le vérificateur : ' + _e(verification.get('satisfied', 'Non renseigné')) + '</p><p>Escalade : ' + _e(report.get('needs_human', 'Non renseignée')) + '</p><p class="muted">Les captures, fichiers audio et téléchargements de traces ne sont pas exposés par cette console.</p></section>'
        return page(request, 'Détail de session', body)

    app.include_router(router)
    return router
