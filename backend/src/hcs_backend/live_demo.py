"""Authenticated live view for a local pitch. Images are exact opt-in model payloads."""
import json
import re
from pathlib import Path

from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

ID = re.compile(r'^[a-f0-9]{32}$')


def frames(root):
    if root is None or not root.is_dir() or root.is_symlink():
        return []
    result = []
    paths = sorted(root.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:24]
    for path in paths:
        if path.is_symlink() or not ID.fullmatch(path.stem) or path.stat().st_size > 131072:
            continue
        try:
            value = json.loads(path.read_text())
            if isinstance(value, dict) and value.get('id') == path.stem:
                result.append(value)
        except (OSError, ValueError):
            continue
    return result


def mount(app, store, settings, authenticate):
    auth = [Depends(authenticate)]

    @app.get('/dashboard/live', response_class=HTMLResponse, dependencies=auth)
    def live_page():
        return HTMLResponse(PAGE, headers={'Cache-Control': 'no-store'})

    @app.get('/dashboard/live/data', dependencies=auth)
    def live_data():
        current = getattr(app.state, 'live_status', lambda: {})()
        cases = store.list_cases()[-12:]
        data = {'current': current.get('current'), 'vision': current.get('vision'),
                'visual_grounding_demo': getattr(app.state, 'visual_grounding_demo', False),
                'frames': frames(settings.vision_evidence_dir),
                'events': store.recent_events(30),
                'cases': [{'case_id': c.case_id, 'session_id': c.session_id,
                           'goal': c.report.get('goal'), 'status': c.report.get('status'),
                           'verified': (c.report.get('verification') or {}).get('satisfied'),
                           'useful': (c.report.get('feedback') or {}).get('useful'),
                           'simulated': c.simulated} for c in reversed(cases)]}
        return JSONResponse(data, headers={'Cache-Control': 'no-store'})

    @app.get('/dashboard/live/frames/{identifier}.jpg', dependencies=auth)
    def live_image(identifier: str):
        root = settings.vision_evidence_dir
        if root is None or root.is_symlink() or not ID.fullmatch(identifier):
            raise HTTPException(404)
        path = root / (identifier + '.jpg')
        if path.is_symlink() or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, media_type='image/jpeg', headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


PAGE = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>H Companion · Live session</title><style>
*{box-sizing:border-box}body{margin:0;background:#f7f7f4;color:#161616;font:16px/1.5 -apple-system,BlinkMacSystemFont,sans-serif}
main{max-width:1440px;margin:auto;padding:26px 36px}header{display:flex;justify-content:space-between;align-items:center;margin-bottom:26px}
h1{font-size:28px;letter-spacing:-1px;margin:0}h2{font-size:20px;margin:0 0 12px}a{color:inherit}small,.muted{color:#68686d;font-size:13px}
.live{background:#e8f6eb;color:#287345;border-radius:30px;padding:7px 14px}.brand{color:#df2a23}
.grid{display:grid;grid-template-columns:1.65fr 1fr;gap:24px}.card{background:white;border:1px solid #deded9;border-radius:20px;padding:24px;margin-bottom:20px;overflow:hidden}
.question{font-size:25px;line-height:1.35;margin:10px 0}.meta{display:flex;gap:14px;flex-wrap:wrap}.meta b{font-size:23px;display:block}
#image{width:100%;max-height:430px;object-fit:contain;background:#efefed;border-radius:10px;margin:18px 0}
#map{width:150px;height:95px;background:#ededeb;border:1px solid #aaa;position:relative;border-radius:4px;flex-shrink:0}#region{position:absolute;border:2px solid #e52b26;background:#e52b2626}
.geometry{display:flex;gap:20px;align-items:center}.pill{font-size:12px;border-radius:6px;background:#f0f0ed;padding:3px 7px}
button{cursor:pointer;background:#fff;border:1px solid #ccc;border-radius:8px;padding:7px 10px;margin:4px 4px 0 0}button.on{border-color:#d22;color:#d22}
.row{border-top:1px solid #eee;padding:13px 0}.row:first-child{border:0}.goal{font-weight:600}.log{font-size:13px;max-height:245px;overflow:auto}
.state{color:#b0201b;font-size:13px;text-transform:uppercase;letter-spacing:1px}.hash{font:11px monospace;overflow-wrap:anywhere}summary{cursor:pointer}
@media(max-width:950px){.grid{grid-template-columns:1fr}main{padding:20px}}
</style><main><header><h1><span class="brand">H</span> Companion <small> / Live sessions</small></h1><div><span id="connection" class="live">Connecting…</span> &nbsp; <a href="/dashboard">All cases ↗</a></div></header>
<div class="grid"><div><section class="card"><span class="state" id="state">Ready</span><p class="question" id="question">Ask Companion a question on H Platform.</p><small id="session"></small><p id="instruction"></p></section>
<section class="card"><h2>What Holo received</h2><p class="muted" id="demoMode" hidden>Visual localisation demo · first target checked with Holo, then accessibility guidance.</p><p class="muted" id="empty">No image sent yet. Accessibility-only guidance can work without a screenshot.</p><div id="frame" hidden>
<div class="meta"><div><b id="kind"></b><small>image payload</small></div><div><b id="size"></b><small>actual JPEG dimensions</small></div><div><b id="latency"></b><small>model request · all retries</small></div><div><b id="tokens"></b><small>API input tokens · text + image</small></div></div>
<img id="image" alt="Exact JPEG payload sent to the model"><div class="geometry"><div id="map"><div id="region"></div></div><div><strong id="area"></strong><div id="coords" class="muted"></div><div id="transport" class="muted"></div></div></div>
<p class="muted">Screen area is not a token-saving measurement. Full-screen fallbacks remain visible below.</p><details><summary>Payload identity</summary><p class="hash" id="hash"></p><small id="association"></small></details></div><div id="history"></div></section></div>
<aside><section class="card"><h2>Recorded in the back-end</h2><p class="muted">Real reports; human feedback stays separate from automatic verification.</p><div id="cases"></div></section><section class="card"><h2>Live event trail</h2><div class="log" id="events"></div></section></aside></div></main>
<script>
const $=id=>document.getElementById(id);let selected=null,lastFrames=[];
function text(id,v){$(id).textContent=v??'—'}function node(tag,cls,content){const n=document.createElement(tag);n.className=cls;n.textContent=content??'';return n}
function frame(f){$('frame').hidden=!f;$('empty').hidden=!!f;if(!f)return;
text('kind',f.kind==='crop'?'Selected region':'Full screen');text('size',f.image_width+' × '+f.image_height);
text('latency',f.latency_ms==null?'Pending':(f.latency_ms/1000).toFixed(2)+' s');text('tokens',f.usage?.prompt_tokens??f.usage?.input_tokens??'Not returned');
const src='/dashboard/live/frames/'+f.id+'.jpg';if($('image').getAttribute('src')!==src)$('image').src=src;
const r=f.region,s=f.screen;const known=r&&s&&s[0]>0&&s[1]>0;$('map').hidden=!known;
if(known){$('map').style.height=(150*s[1]/s[0])+'px';Object.assign($('region').style,{left:r[0]/s[0]*100+'%',top:r[1]/s[1]*100+'%',width:r[2]/s[0]*100+'%',height:r[3]/s[1]*100+'%'});text('area',Math.round(r[2]*r[3]/(s[0]*s[1])*100)+'% of screen area');text('coords','x '+r[0]+' · y '+r[1]+' · '+r[2]+' × '+r[3]+' screen points');}else{text('area','Full-screen visual check');text('coords','')}
text('transport',f.status+' · '+f.attempts+' attempt(s) · '+new Date(f.created_at).toLocaleTimeString());text('hash','SHA-256 '+f.sha256);text('association',(f.session_id||'Independent visual request')+' · '+f.model);
}
async function refresh(){try{const response=await fetch('/dashboard/live/data',{cache:'no-store'});if(!response.ok)throw Error();const d=await response.json();text('connection','● Connected');
const c=d.current;text('state',c?.state||'Ready');text('question',c?.goal||'Ask Companion a question on H Platform.');text('session',c?.session_id||'');text('instruction',c?.step?.instruction||'');
$('demoMode').hidden=!d.visual_grounding_demo;
lastFrames=d.frames;const scoped=c?d.frames.filter(f=>f.session_id===c.session_id):d.frames;frame(lastFrames.find(f=>f.id===selected)||scoped[0]);
$('history').replaceChildren();for(const f of d.frames.slice(0,8)){const b=node('button',f.id===selected?'on':'',(f.kind==='crop'?'Crop':'Full')+' · '+new Date(f.created_at).toLocaleTimeString());b.onclick=()=>{selected=f.id;frame(f)};$('history').append(b)}
$('cases').replaceChildren();for(const c of d.cases){const row=node('div','row');const a=node('a','goal',c.goal);a.href='/dashboard/cases/'+encodeURIComponent(c.case_id);row.append(a,node('div','muted',(c.simulated?'SIMULATED · ':'Real · ')+c.status+' · verification: '+(c.verified===true?'confirmed':c.verified===false?'not confirmed':'not assessed')),node('div','muted','Human usefulness: '+(c.useful===true?'yes':c.useful===false?'no':'not rated')));$('cases').append(row)}if(!d.cases.length)$('cases').append(node('p','muted','The report appears when a session ends.'));
$('events').replaceChildren();for(const e of d.events.slice(0,12))$('events').append(node('div','row',e.type+' · '+(e.message||e.state)+' · '+e.session_id));
}catch{text('connection','Connection unavailable')}finally{setTimeout(refresh,1200)}}refresh();
</script></html>'''
