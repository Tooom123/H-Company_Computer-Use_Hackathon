"""Shared company-portal styling, matched to Tom's landing on main cbad15f.

All three OFL fonts are local assets; no portal request reaches a font CDN.
Font routes inherit the caller router's existing authentication and host guards.
"""
from pathlib import Path

from fastapi import HTTPException
from starlette.responses import Response

FONTS = {name: Path(__file__).with_name('assets') / 'fonts' / name
         for name in ('PlusJakartaSans.ttf', 'FiraCode.ttf', 'Caveat.ttf')}


def mount_portal_fonts(router):
    @router.get('/assets/fonts/{filename}', include_in_schema=False)
    async def font(filename: str):
        path = FONTS.get(filename)
        if path is None or not path.is_file() or path.is_symlink():
            raise HTTPException(404, 'Police indisponible.')
        return Response(path.read_bytes(), media_type='font/ttf', headers={
            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Cross-Origin-Resource-Policy': 'same-origin'})


def portal_header(current='/company/live', *, live=True):
    links = [('/company', 'Configuration'), ('/company/documents', 'Documentation'),
             ('/company/sessions', 'Sessions et retours')]
    if live:
        links.append(('/company/live', 'Tour de contrôle'))
    nav = ''.join('<a href="' + href + '"' + (' aria-current="page"' if current == href else '')
                  + '>' + label + '</a>' for href, label in links)
    return ('<header class="portal-header"><a class="brand" href="/company"><span class="brand-key" aria-hidden="true">H</span>'
            '<span class="brand-word">Companion<span class="brand-caption">ESPACE ENTREPRISE</span></span></a>'
            '<nav aria-label="Navigation entreprise">' + nav + '</nav></header>')


def portal_styles(font_base):
    # Only the two hard-coded router prefixes are permitted, never request input.
    if font_base not in {'/company/assets/fonts', '/company/live/assets/fonts'}:
        raise ValueError('Unknown portal font prefix')
    faces = ''.join('@font-face{font-family:"' + family + '";src:url("' + font_base + '/' + file
                    + '") format("truetype");font-style:normal;font-weight:' + weights + ';font-display:swap}'
                    for family, file, weights in [('Plus Jakarta Sans', 'PlusJakartaSans.ttf', '300 800'),
                                                  ('Fira Code', 'FiraCode.ttf', '300 700'),
                                                  ('Caveat', 'Caveat.ttf', '400 700')])
    return faces + BASE_CSS


BASE_CSS = r'''
:root{--black:#040405;--grey-800:#0d0d12;--grey-750:#1c1c26;--grey-700:#2e2e3a;--grey-600:#4a4a58;--grey-500:#7a7a8a;--grey-400:#adadbc;--grey-300:#d8d8e2;--grey-250:#ebebf1;--grey-200:#f2f2f5;--grey-100:#f9f9fb;--white:#fff;--red:#e3242b;--sans:"Plus Jakarta Sans",system-ui,sans-serif;--mono:"Fira Code",ui-monospace,monospace}
*{box-sizing:border-box}body{margin:0;background:var(--white);color:var(--grey-750);font:14px var(--sans);-webkit-font-smoothing:antialiased}a{color:inherit;text-underline-offset:4px}button,input,select,textarea{font:inherit}button,select,input,textarea{max-width:100%;border:1px solid var(--grey-300);border-radius:10px;padding:10px 13px;background:var(--white);color:var(--grey-750)}button{background:var(--black);color:var(--white);border-color:var(--black);border-radius:999px;font-weight:600;cursor:pointer}button:hover{background:var(--grey-700)}button:disabled{opacity:.5;cursor:default}:focus-visible{outline:2px solid var(--red);outline-offset:4px}input[type=checkbox]{accent-color:var(--black)}main{max-width:1680px;margin:auto;padding:20px 28px 28px}.portal-header{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:0 0 20px;border-bottom:1px solid var(--grey-250)}.brand{display:flex;gap:11px;align-items:center;text-decoration:none;flex:none}.brand-key{display:grid;place-items:center;background:var(--black);color:var(--white);font-size:26px;font-weight:800;width:43px;height:43px;border-radius:11px;box-shadow:0 3px 0 var(--grey-300);transform:rotate(-4deg)}.brand-word{font-size:20px;font-weight:750;letter-spacing:-.04em;line-height:1.1}.brand-caption{display:block;font:9px var(--mono);letter-spacing:.11em;color:var(--grey-500);margin-top:6px}.portal-header nav{display:flex;gap:6px;flex-wrap:wrap;align-items:center}.portal-header nav a{text-decoration:none;font-size:12px;font-weight:600;padding:10px 13px;border-radius:999px;color:var(--grey-600);white-space:nowrap}.portal-header nav a:hover{background:var(--grey-100);color:var(--black)}.portal-header nav a[aria-current=page]{background:var(--black);color:var(--white)}h1,h2,h3{font-weight:700;letter-spacing:-.035em;color:var(--grey-750)}h1{font-size:clamp(29px,3.2vw,42px);line-height:1.1;margin:7px 0 12px}h2{font-size:21px;line-height:1.25;margin:0 0 14px}h3{font-size:15px;letter-spacing:-.015em}p{line-height:1.6}.eyebrow{font:10px var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--grey-500);margin:0 0 9px}.pen-note{font:700 23px "Caveat",cursive;color:var(--red);transform:rotate(-3deg);display:inline-block}.ink-word{position:relative;white-space:nowrap}.ink-word::after{content:"";position:absolute;left:0;right:-2px;bottom:-5px;height:5px;border-bottom:2px solid var(--red);border-radius:50%;transform:rotate(-2deg)}.muted{color:var(--grey-600)}.small{font-size:11px}.mono,code,pre,time{font-family:var(--mono)}.page-intro{margin:26px 0 24px;padding-left:18px;border-left:2px solid rgba(227,36,43,.42)}.page-intro .subtitle{color:var(--grey-600);margin:0;font-size:13px}.page-footer{border-top:1px solid var(--grey-250);margin:24px 0 0;padding:17px 0 0;color:var(--grey-500);font-size:11px}.badge{display:inline-block;padding:5px 9px;border-radius:999px;background:var(--grey-200);color:var(--grey-600);font-size:10px;line-height:1.35}.badge.warn{background:#fff3e6;color:#8e571b}.badge.bad{background:#fff0f0;color:#b01f27}.error{color:#b01f27}.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse}th,td{text-align:left;vertical-align:top;border-bottom:1px solid var(--grey-250);padding:13px 14px}th{font:10px var(--mono);letter-spacing:.04em;color:var(--grey-500);text-transform:uppercase}td{font-size:12px}code{font-size:.92em;overflow-wrap:anywhere}summary{cursor:pointer;font-size:12px;font-weight:600}details[open] summary{margin-bottom:12px}dialog{border:1px solid var(--grey-300);border-radius:18px;padding:18px;background:var(--white);max-width:95vw}dialog::backdrop{background:#040405d9}dialog header{display:flex;gap:16px;align-items:center;justify-content:space-between;margin-bottom:12px}dialog img{max-width:90vw;width:1200px;height:78vh;object-fit:contain;background:var(--grey-100)}
@media(max-width:760px){main{padding:18px 15px}.portal-header{align-items:flex-start;gap:19px;flex-direction:column;padding-bottom:16px}.portal-header nav{gap:4px}.portal-header nav a{font-size:11px;padding:8px 10px}.brand-key{height:38px;width:38px;font-size:23px}.brand-word{font-size:18px}.page-intro{margin:22px 0 20px;padding-left:14px}.pen-note{font-size:21px}dialog img{height:65vh}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}
'''
