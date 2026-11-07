# Real run log

One line per run that actually drove H on the Mac. Simulated runs do not belong here.

| Date | Who | Scenario | Duration | Outcome (verified / escalated / stopped) | Human corrections | Notes |
| --- | --- | --- | --- | --- | --- | --- |

## Procedure audits (no H run, not counted above)

### 2026-11-07, Matteo + Claude Code: Odoo 20 label audit and Holo grounding check

Instance: `h-companion.odoo.com` (Odoo **20.0+e**, English UI, admin user). Each scripted procedure was walked
by hand in Chrome, then every `element` / `done_when` text of the YAMLs was sent to Holo (`holo4-35b-a3b`,
thinking off) on full-resolution screenshots of the real pages and compared with the DOM position of the control.

- Labels fixed: Odoo 20, not 19. Quick-create title field is "Opportunity's Name" and the cursor starts in
  "Contact"; Enter saves the card and an empty card reopens. Customer field is "Contact". Chatter sits on the
  right of the form. Activity dialog: type chips (To-Do preselected), summary prefilled "To-Do", buttons
  Save / Mark Done / Discard (no "Schedule"). Internal notes have no yellow background any more.
- Grounding: 26/28 element descriptions boxed the right control first time (0.7–2.0 s each, median 0.9 s; per-element table in `grounding-odoo20-2026-11-07.md`).
  Misses: "Expected Revenue (0.00 €)" fails once the amount is not 0 (value removed from the description);
  "New" column title is boxed ~10 px low because Odoo's onboarding tour pin sits on it (annotation only).
- `done_when` screen checks: 16/18 on the first wording. Holo read "Follow up" from the chatter behind the
  dialog, and answered negations ("no cloud icon") wrongly. Reworded; the rewrites passed 2/2 and 2/2.
- Test data: opportunity "Zz Test Guide" created, then deleted. No "Zz Test" record exists on this instance.
- Not done: a full guided run with the overlay (the Mac's screen was in use).

### Open setup need: "Won blocked" scenario (`odoo_crm_change_stage_restricted`)

Untestable on the current account: it is an administrator, so "Won" is never refused. Someone has to create a
non-admin Odoo user for the demo (Settings → Users → Sales: **User: Own Documents Only**) and check what that
user actually sees when clicking Won. Standard Odoo lets a salesperson mark their own opportunity Won, so the
block may need a record owned by another salesperson or a custom rule; confirm before relying on it on stage.
Also worth doing on the demo database: finish or dismiss the Odoo onboarding tour (its pin covers the "New"
button and column title).
