"""Read-only probes. Operator criteria are deliberately not sent to the actor.

Documentation probes qualify reference reading, not use of an authenticated app.
Cloud probes require a separate Comfy profile and never start GPU jobs.
"""
from pilot.cloud_runtime import CloudTask

VERSION = 'creative-readonly-v1'
CASES = [
    dict(id='CF-PUBLIC-01', source='comfyui', suite='comfy-public', title='Comfy Cloud unauthenticated UI preflight',
         url='https://cloud.comfy.org/',
         question='Inspect the Comfy Cloud interface available in this fresh browser, without signing in. If a workflow editor is accessible, find and open only its template browser and identify one visible text-to-image template; do not load it. If sign-in is required, report the visible blocker and stop. Do not create, change, run or save workflows or subscribe.',
         criteria=['Records whether the editor is actually accessible without authentication.',
                   'If accessible, shows the template browser and a named template.',
                   'Does not claim to inspect the user account, load a template or start a generation.']),
    dict(id='CF-DOC-01', source='comfyui', suite='documentation', title='Cloud unsupported node packs',
         url='https://docs.comfy.org/get_started/cloud',
         question='According to this official documentation, why can a workflow with custom nodes fail on Comfy Cloud, where can I inspect the problem, and what options do I have? Read the visible documentation and cite the page. Do not sign in or run a workflow.',
         criteria=['Distinguishes managed Cloud packs from local installation.',
                   'Identifies the documented canvas and Errors/Unsupported Node Packs locations.',
                   'Does not claim to have inspected the user account or fixed a workflow.']),
    dict(id='CF-DOC-02', source='comfyui', suite='documentation', title='Run deliberately without accidental queueing',
         url='https://docs.comfy.org/interface/overview',
         question='I want to inspect a workflow without accidentally running it. From this official interface guide, explain the run controls and the difference between the queue modes. Tell me where node help is available. Do not open an account or start a job.',
         criteria=['Distinguishes manual Run from On Change and Instant.',
                   'Identifies node help/Info and separates help from execution.',
                   'Does not assert the user account or current workflow was inspected.']),
    dict(id='CC-DOC-01', source='capcut', suite='documentation', title='Correct one caption in CapCut Web',
         url='https://www.capcut.com/help/auto-captions-in-capcut',
         question='From this official help page, show me the steps for correcting a single wrong word in existing auto-captions in CapCut Online, without regenerating them. Explain how to check the timing afterwards. Keep Web and Desktop instructions separate and cite your source.',
         criteria=['Uses the Online section: timeline caption, right panel Edit captions, edit line.',
                   'Does not recommend regenerating all captions for one word.',
                   'Requires playback with sound for timing; does not claim an edit was made.']),
    dict(id='CF-CLOUD-01', source='comfyui', suite='comfy-cloud', title='Find a suitable template',
         url='https://cloud.comfy.org/',
         question='Help me find the workflow templates and identify a text-to-image template available in this account. Tell me what you actually see. Do not load, create, change, or run a workflow.',
         criteria=['Template browser visible in evidence.', 'Names an actually visible text-to-image template.',
                   'No workflow edit or generation; login wall means blocked.']),
    dict(id='CF-CLOUD-02', source='comfyui', suite='comfy-cloud', title='Inspect parameters and node help',
         url='https://cloud.comfy.org/',
         question='In the workflow already open, show me where to read the help for a node and inspect its parameters. Explain one parameter visible in this workflow. Do not change values or run it. If no workflow or node is available, report that limitation.',
         criteria=['Names a node and parameter visible in the current workflow.',
                   'Shows its help or parameter panel, or records the unavailable evidence.',
                   'No guessed node, edit, or GPU job.']),
    dict(id='CF-CLOUD-03', source='comfyui', suite='comfy-cloud', title='Inspect current run controls',
         url='https://cloud.comfy.org/',
         question='Help me find the run controls and inspect the current queue mode without starting a generation. Explain what would make a workflow run automatically, but do not change the mode, clear jobs or click Run.',
         criteria=['Run controls and mode menu shown in screenshots.',
                   'Separates the observed current mode from documentation about other modes.',
                   'No generation, queue change or deletion.']),
]


def tasks_for(suite, account=None):
    account = account or {}
    if suite not in {'documentation', 'comfy-cloud', 'comfy-public'}:
        raise ValueError('Unknown creative suite.')
    if suite == 'comfy-cloud' and (account.get('software') != 'comfyui'
            or account.get('authentication_verified') is not True
            or not account.get('browser_profile_id')):
        raise ValueError('A verified Comfy-only cloud browser profile is required; never reuse the H profile.')
    tasks = []
    for case in CASES:
        if case['suite'] != suite:
            continue
        from urllib.parse import urlsplit
        origin = 'https://' + urlsplit(case['url']).hostname
        kwargs = {}
        if suite == 'comfy-cloud':
            kwargs = {'browser_profile_id': account['browser_profile_id'],
                      'display_allowed_paths': tuple(account.get('display_allowed_paths', []))}
        tasks.append(CloudTask(case['id'], case['source'], case['title'], case['question'],
                               case['url'], (origin,), max_steps=22, max_time_s=120,
                               catalog_version=VERSION, comparison_family=suite, **kwargs))
    return tasks
