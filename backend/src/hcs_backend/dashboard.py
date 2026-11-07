"""Server-rendered support dashboard. No JS framework, no external assets; every value is escaped."""

from __future__ import annotations

from html import escape
from typing import Any

from .escalation import build_escalation
from .timeline import attempts, build_timeline, duration_s, had_takeover, stop_latency_s
from .grouping import Group
from .store import StoredCase

CSS = """
:root{--bg:#f7f7f5;--card:#fff;--fg:#1d1d1f;--muted:#6b6b70;--line:#e3e3e0;--accent:#3b5bdb;
--ok:#2b8a3e;--warn:#b35c00;--bad:#c92a2a;--chip:#eef0f6}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--card:#1d1d20;--fg:#ececee;--muted:#9a9aa2;
--line:#2e2e33;--accent:#8ea2ff;--ok:#69db7c;--warn:#ffa94d;--bad:#ff8787;--chip:#2a2c35}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 10px}
.sub{color:var(--muted);margin:0 0 20px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:8px}
.kpi,.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.kpi b{display:block;font-size:26px;font-variant-numeric:tabular-nums}.kpi span{color:var(--muted);font-size:13px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;text-transform:uppercase;letter-spacing:.03em;color:var(--muted);font-weight:600}
tr:last-child td{border-bottom:0}td.num{font-variant-numeric:tabular-nums;text-align:right}
.chip{display:inline-block;background:var(--chip);border-radius:999px;padding:1px 8px;font-size:12px;margin:1px 2px 1px 0}
.s-resolved{color:var(--ok)}.s-workaround{color:var(--warn)}.s-escalated{color:var(--bad)}.s-abandoned{color:var(--muted)}
.flag{display:inline-block;border:1px solid var(--warn);color:var(--warn);border-radius:4px;font-size:11px;
padding:0 5px;margin-left:6px;font-weight:600;letter-spacing:.03em}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media (max-width:720px){.grid2{grid-template-columns:1fr}
.hide-sm{display:none}}
dl{margin:0;display:grid;grid-template-columns:max-content 1fr;gap:4px 14px}dt{color:var(--muted)}dd{margin:0}
.decision{border-left:4px solid var(--bad)}.muted{color:var(--muted)}ol{margin:0;padding-left:20px}
.wrap{overflow-x:auto}
.timeline{list-style:none;margin:0;padding:0}.tl{display:grid;grid-template-columns:64px 104px 1fr;gap:10px;
padding:7px 8px;border-left:4px solid var(--line);margin:3px 0;border-radius:4px}.tl-when{color:var(--muted);
font-variant-numeric:tabular-nums}.tl-tag{font-size:12px;font-weight:600}.tl-explain{border-color:#7c4dff}
.tl-stuck{border-color:var(--warn);background:rgba(179,92,0,.06)}.tl-takeover{border-color:var(--bad)}
.tl-action,.tl-observe{border-color:var(--accent)}.tl-verify{border-color:var(--ok);background:rgba(43,138,62,.06)}
.tl-error{border-color:var(--bad)}.tl-system{border-color:var(--line)}
@media (max-width:720px){.tl{grid-template-columns:1fr}}.fixcard{margin-top:12px;border-left:4px solid var(--accent)}.devin-ask{margin-top:10px;padding:10px 12px;border-radius:8px;background:var(--chip)}.devin-ask textarea{width:100%;margin:6px 0;font:inherit;padding:6px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--fg)}.fixbtn{margin-top:4px;padding:8px 14px;border-radius:8px;border:0;background:var(--fg);color:var(--bg);font-weight:600;cursor:pointer}.card>b{display:block;margin:0 0 8px}
"""


def _page(title: str, body: str, refresh: bool = False) -> str:
    meta = '<meta http-equiv="refresh" content="10">' if refresh else ""
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">{meta}'
        f"<title>{escape(title)}</title><style>{CSS}</style></head><body><main>{body}</main></body></html>"
    )


def _flags(simulated: bool, demo: bool) -> str:
    out = ""
    if simulated:
        out += '<span class="flag" title="Produced without a real H run">SIMULATED</span>'
    if demo:
        out += '<span class="flag" title="Prepared demo data, not a real customer">DEMO</span>'
    return out


def _status(s: str | None) -> str:
    s = s or "unknown"
    return f'<span class="s-{escape(s)}">{escape(s)}</span>'


def _chips(items: list[str]) -> str:
    return "".join(f'<span class="chip">{escape(str(i))}</span>' for i in items) or '<span class="muted">—</span>'


def _v(value: Any) -> str:
    if value in (None, "", [], {}):
        return '<span class="muted">—</span>'
    if isinstance(value, bool):
        return "yes" if value else "no"
    return escape(str(value))


def index_page(groups: list[Group], cases: list[StoredCase]) -> str:
    # metrics count real sessions only: simulated reports are flagged and listed, never counted
    real = [c for c in cases if not c.simulated]
    reports = [c.report for c in real]
    n_sim = len(cases) - len(real)
    verified = sum(1 for r in reports if (r.get("verification") or {}).get("satisfied") is True)
    escalated = sum(1 for r in reports if r.get("status") == "escalated")
    any_sim = any(c.simulated for c in cases)
    any_demo = any(c.demo_data for c in cases)
    kpis = [
        (len(real), "real assisted sessions"),
        (len({c.user_key for c in real}), "distinct users"),
        (len(groups), "difficulty groups"),
        (f"{verified}/{len(real)}" if real else "0", "verified resolved"),
        (escalated, "escalated to support"),
    ]
    body = [
        f"<h1>Support dashboard{_flags(any_sim, any_demo)}</h1>",
        '<p class="sub">Describes assisted sessions only — not all usage of the software. '
        + (f"<b>{n_sim} simulated session(s) excluded from the numbers</b> (listed below with their flag). " if n_sim else "")
        + 'Auto-refreshes every 10 s. <a href="/dashboard/metrics">Reliability metrics →</a></p>',
        '<div class="kpis">' + "".join(f'<div class="kpi"><b>{escape(str(v))}</b><span>{escape(k)}</span></div>' for v, k in kpis) + "</div>",
        "<h2>Difficulty groups</h2>",
    ]
    if not groups:
        body.append('<div class="card muted">No case received yet. The agent posts reports to <code>POST /cases</code>.</div>')
    else:
        rows = []
        for g in groups:
            s = g.summary()
            statuses = " ".join(f"{_status(k)}&nbsp;{v}" for k, v in sorted(s["statuses"].items()))
            rows.append(
                f'<tr><td><a href="/dashboard/groups/{escape(s["group_id"])}">{escape(s["label"])}</a>'
                f'{_flags(s["simulated"], s["demo_data"])}<br>{_chips(s["keywords"])}</td>'
                f'<td>{escape(s["software"] or "")}<br><span class="chip">{escape(s["category"])}</span></td>'
                f'<td class="num">{s["n_cases"]}</td><td class="num">{s["n_users"]}</td>'
                f"<td>{statuses}</td>"
                f'<td class="hide-sm">{_chips(s["procedures"])}</td></tr>'
            )
        body.append(
            '<div class="wrap"><table><thead><tr><th>Difficulty</th><th>Software / category</th><th>Cases</th>'
            '<th>Users</th><th>Status</th><th class="hide-sm">Procedures tried</th></tr></thead><tbody>'
            + "".join(rows)
            + "</tbody></table></div>"
        )
    body.append("<h2>Latest cases</h2>")
    body.append(_cases_table(list(reversed(cases))[:25]))
    return _page("Support dashboard", "".join(body), refresh=True)


def _cases_table(cases: list[StoredCase]) -> str:
    if not cases:
        return '<div class="card muted">No case.</div>'
    rows = []
    for c in cases:
        r = c.report
        v = (r.get("verification") or {}).get("satisfied")
        verified = {True: "observed ✓", False: "not met", None: "not checked"}[v]
        rows.append(
            f'<tr><td><a href="/dashboard/cases/{escape(c.case_id)}">{escape(c.case_id)}</a>{_flags(c.simulated, c.demo_data)}</td>'
            f'<td>{escape(r.get("goal") or "")}</td><td>{_status(r.get("status"))}</td>'
            f'<td><span class="chip">{escape(r.get("category") or "")}</span></td>'
            f'<td class="hide-sm">{escape(verified)}</td><td class="hide-sm muted">{escape(c.received_at)}</td></tr>'
        )
    return (
        '<div class="wrap"><table><thead><tr><th>Case</th><th>Goal</th><th>Status</th><th>Category</th>'
        '<th class="hide-sm">Postcondition</th><th class="hide-sm">Received</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table></div>"
    )


def group_page(group: Group) -> str:
    s = group.summary()
    fb = "".join(
        f'<li>“{escape(f["comment"])}” <a href="/dashboard/cases/{escape(f["case_id"])}">{escape(f["case_id"])}</a></li>'
        for f in s["feedback"]
    )
    body = (
        '<p><a href="/dashboard">← Dashboard</a></p>'
        f"<h1>{escape(s['label'])}{_flags(s['simulated'], s['demo_data'])}</h1>"
        f'<p class="sub">{escape(s["software"] or "")} · {escape(s["category"])} · {s["n_cases"]} case(s), '
        f'{s["n_users"]} distinct user(s) · first {escape(s["first_seen"])}, last {escape(s["last_seen"])}</p>'
        '<div class="grid2"><div class="card"><dl>'
        f"<dt>Shared keywords</dt><dd>{_chips(s['keywords'])}</dd>"
        f"<dt>Procedures</dt><dd>{_chips(s['procedures'])}</dd>"
        f"<dt>Verified resolved</dt><dd>{s['verified_resolved']}</dd>"
        f"<dt>Needs a human</dt><dd>{s['needs_human']}</dd>"
        "</dl></div>"
        f'<div class="card"><b>Feedback expressed by users</b><ul>{fb or "<li class=muted>none</li>"}</ul></div></div>'
        "<h2>Source cases</h2>"
        + _cases_table(group.cases)
    )
    return _page(f"Group {s['group_id']}", body)


def _fix_card(case: StoredCase, fix: dict | None, fix_repo: str | None) -> str:
    """Auto-fix with Devin: request button, session and pull request links."""
    if not fix_repo and not fix:
        return ""
    if not fix:
        auto = case.report.get("category") == "suspected_product_defect"
        return (
            '<div class="card fixcard"><b>Fix with Devin</b>'
            f'<p class="muted">Repository on the allowlist: <code>{escape(fix_repo or "")}</code>. '
            f'{"Suspected product defect: " if auto else ""}Devin reproduces the defect with a test, fixes it and '
            "opens a pull request on a <code>feature/</code> branch.</p>"
            f'<form method="post" action="/dashboard/cases/{escape(case.case_id)}/fix">'
            '<button class="fixbtn" type="submit">Send to Devin</button></form></div>'
        )
    status = "PR opened" if fix.get("pr_url") and fix.get("status_detail") == "waiting_for_user" else str(fix.get("status") or "")
    sim = _flags(bool(fix.get("simulated")), False)
    pr = fix.get("pr_url")
    pr_html = (f'<a href="{escape(pr.split(" ")[0])}">{escape(pr)}</a> <span class="muted">({escape(str(fix.get("pr_state") or ""))})</span>'
               if pr else '<span class="muted">not yet</span>')
    sess = fix.get("session_url")
    res = fix.get("result") or {}
    rows = [
        ("Status", f"<b>{escape(status)}</b> {escape(str(fix.get('status_detail') or ''))}"),
        ("Pull request", pr_html),
        ("Devin session", f'<a href="{escape(sess.split(" ")[0])}">{escape(fix.get("session_id") or "")}</a>' if sess else "—"),
        ("Repository", f"<code>{escape(fix.get('repo') or '')}</code> · branch <code>{escape(fix.get('branch') or '')}</code>"),
        ("Triggered", escape(f"{fix.get('trigger')} · {fix.get('created_at')}")),
    ]
    if res:
        rows += [("Reproduced", _v(res.get("reproduced"))), ("Root cause", _v(res.get("root_cause"))),
                 ("Fix", _v(res.get("fix_summary"))), ("Test added", _v(res.get("test_added")))]
    if fix.get("error") or fix.get("last_error"):
        rows.append(("Error", escape(str(fix.get("error") or fix.get("last_error")))))
    dl = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in rows)
    ask = ""
    if fix.get("devin_says"):
        head = "Devin's summary (reply to ask for changes)" if fix.get("pr_url") else "Devin is waiting for you"
        ask = (
            f'<div class="devin-ask"><b>{head}</b><p>{escape(fix["devin_says"])}</p>'
            f'<form method="post" action="/dashboard/cases/{escape(case.case_id)}/fix/message">'
            '<textarea name="message" rows="2" required placeholder="Answer Devin (e.g. access granted, go ahead)"></textarea>'
            '<button class="fixbtn" type="submit">Reply</button></form></div>'
        )
    replies = "".join(f"<li>{escape(r)}</li>" for r in fix.get("replies", []))
    replies = f'<p class="muted">Your replies:</p><ul>{replies}</ul>' if replies else ""
    return f'<div class="card fixcard"><b>Fix with Devin{sim}</b><dl>{dl}</dl>{ask}{replies}</div>'


PHASE_LABEL = {
    "explain": "Explained", "stuck": "Stuck", "takeover": "Takeover", "action": "Agent action",
    "observe": "Agent saw", "verify": "Verifier", "error": "Error", "system": "Detail",
}


def _timeline_html(report: dict) -> str:
    """Steps explained -> where the user got stuck -> takeover -> agent actions -> verifier (PRD: keep the agent's
    claims and the verifier's observations visually apart)."""
    tl = build_timeline(report)
    if not tl:
        return "<h2>Timeline</h2><div class='card muted'>No step recorded.</div>"
    rows, detail = [], []
    for ev in tl:
        when = escape(str(ev.get("at") or "")[11:19])
        extra = ""
        if ev.get("seconds") is not None:
            extra += f' <span class="muted">· shown after {ev["seconds"]:.1f} s</span>'
        if ev.get("detail"):
            extra += f'<div class="muted">{escape(str(ev["detail"]))}</div>'
        line = (f'<li class="tl tl-{escape(ev["phase"])}"><span class="tl-when">{when}</span>'
                f'<span class="tl-tag">{escape(PHASE_LABEL.get(ev["phase"], ev["phase"]))}</span>'
                f'<span class="tl-text">{escape(str(ev["text"]))}{extra}</span></li>')
        (detail if ev["phase"] == "system" else rows).append(line)
    more = (f"<details><summary class='muted'>{len(detail)} grounding / screen-check detail(s)</summary>"
            f"<ol class='timeline'>{''.join(detail)}</ol></details>") if detail else ""
    return ("<h2>Timeline</h2><div class='card'><p class='muted'>Purple: the assistant explains · amber: the user "
            "got stuck · blue: the agent acts (its claims) · green: the separate verifier (observed).</p>"
            f"<ol class='timeline'>{''.join(rows)}</ol>{more}</div>")


def _knowledge_html(report: dict) -> str:
    notes = report.get("knowledge") or []
    if not notes:
        return ""
    items = []
    for n in notes:
        src = "".join(f'<li><a href="{escape(x.get("url") or "")}">{escape(x.get("name") or x.get("url") or "")}</a></li>'
                      for x in n.get("sources") or [])
        items.append(f'<div class="card" style="margin-bottom:8px"><span class="chip">{escape(n.get("purpose") or "")}</span>'
                     f'{_flags(bool(n.get("simulated")), False)}<p><b>{escape(n.get("query") or "")}</b></p>'
                     f'<p>{escape(n.get("answer") or "")}</p><ul>{src}</ul></div>')
    return "<h2>Documentation looked up (Linkup)</h2>" + "".join(items)


def case_page(case: StoredCase, group_id: str | None, fix: dict | None = None, fix_repo: str | None = None) -> str:
    e = build_escalation(case)
    ctx, user, agent, obs = e["context"], e["user_declared"], e["agent_declared"], e["observed"]
    decision = ""
    if e["needs_human"] or e["decision_expected"]:
        decision = (
            '<div class="card decision"><b>Decision expected from support</b>'
            f"<p>{_v(e['decision_expected'])}</p><dl>"
            f"<dt>Blocked on</dt><dd>{_v(e['blocked_on'])}</dd>"
            f"<dt>Attempts</dt><dd>{_v(e['attempts'])}</dd>"
            f"<dt>Suspected cause</dt><dd>{_v(e['suspected_cause'])} <span class='muted'>(hypothesis)</span></dd>"
            f"<dt>Suggested next step</dt><dd>{_v(e['suggested_next_step'])}</dd></dl></div>"
        )
    checks = "".join(f"<li><code>{escape(k)}</code>: {'ok' if v else 'FAILED'}</li>" for k, v in obs["checks"].items())
    evidence = "".join(
        f"<li><code>{escape(ev['ref'])}</code> ({escape(ev['kind'])}) {escape(ev['description'])}</li>" for ev in e["evidence"]
    )
    if e["evidence_withheld"]:
        evidence += f"<li class='muted'>{e['evidence_withheld']} screenshot(s) withheld — not allowed by the user.</li>"
    fb = user["feedback"] or {}
    group_link = f' · <a href="/dashboard/groups/{escape(group_id)}">group</a>' if group_id else ""
    r = case.report
    dur, stop = duration_s(r), stop_latency_s(r)
    facts = [
        ("mode", r.get("mode") or "act"),
        ("takeover", "yes" if had_takeover(r) else "no") if r.get("mode") == "guide" else None,
        ("attempts", attempts(r)),
        ("duration", f"{dur:.0f} s" if dur is not None else None),
        ("stop latency", f"{stop:.2f} s" if stop is not None else None),
        ("cost", f"${r['cost_usd']:.2f}" if r.get("cost_usd") is not None else None),
    ]
    facts_html = "".join(f'<span class="chip">{escape(k)}: <b>{escape(str(v))}</b></span>'
                         for f in facts if f and f[1] is not None for k, v in [f])
    body = (
        '<p><a href="/dashboard">← Dashboard</a></p>'
        f"<h1>Case {escape(e['case_id'])}{_flags(e['simulated'], e['demo_data'])}</h1>"
        f'<p class="sub">{_status(e["status"])} · <span class="chip">{escape(e["category"] or "")}</span> · '
        f'{escape(str(ctx["software"]))} {escape(str(ctx["software_version"] or ""))} · {escape(str(ctx["os"]))}{group_link} · '
        f'<a href="/cases/{escape(e["case_id"])}/escalation.md">escalation file (.md)</a></p>'
        f'<p>{facts_html}</p>'
        + decision
        + _fix_card(case, fix, fix_repo)
        + '<div class="grid2" style="margin-top:12px">'
        '<div class="card"><b>Declared by the user</b><dl>'
        f"<dt>Role</dt><dd>{_v(user['role'])}</dd><dt>Goal</dt><dd>{_v(user['goal'])}</dd>"
        f"<dt>Symptom</dt><dd>{_v(user['symptom'])}</dd>"
        f"<dt>Useful?</dt><dd>{_v(fb.get('useful'))}</dd><dt>Feedback</dt><dd>{_v(fb.get('comment'))}</dd></dl></div>"
        '<div class="card"><b>Declared by the agent</b><dl>'
        f"<dt>Outcome</dt><dd>{_v(agent['outcome'])}</dd><dt>Summary</dt><dd>{_v(agent['summary'])}</dd>"
        f"<dt>Blocker</dt><dd>{_v(agent['blocker'])}</dd></dl></div>"
        '<div class="card"><b>Observed (verification)</b><dl>'
        f"<dt>Performed</dt><dd>{_v(obs['verification_performed'])}</dd>"
        f"<dt>Postcondition</dt><dd>{_v(obs['postcondition'])}</dd>"
        f"<dt>Satisfied</dt><dd>{_v(obs['postcondition_satisfied'])}</dd>"
        f"<dt>Observed</dt><dd>{_v(obs['observed_state'])}</dd>"
        f"<dt>User confirmed</dt><dd>{_v(obs['user_confirmed'])}</dd></dl>"
        f"<ul>{checks}</ul></div>"
        f'<div class="card"><b>Evidence</b><ul>{evidence or "<li class=muted>none</li>"}</ul>'
        f"<b>H sessions</b><div>{_chips(e['h_session_ids'])}</div></div></div>"
        + _timeline_html(r)
        + _knowledge_html(r)
    )
    return _page(f"Case {e['case_id']}", body)
