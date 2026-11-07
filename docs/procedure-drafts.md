# Drafting procedures from the vendor documentation

`scripts/draft_procedure.py` turns a documentation page into a draft guide procedure for the engine
(`agent/src/hcs_agent/procedures/*.yaml`), to show that a vendor can scale from a handful of hand-written tasks
to dozens (docs/TODO-tom.md, item 6).

```bash
python scripts/draft_procedure.py --url <doc page> --id odoo_crm_<task> --title "<title>" \
    --objective 'Do X on "{opportunity}"' -o draft.yaml          # Linkup fetch if LINKUP_API_KEY, else HTTP
python scripts/draft_procedure.py --file page.html|page.md ...    # offline
```

How it works:

- menu paths (`CRM app ‣ Configuration ‣ Activity Types`) become one click per level;
- for each action verb, the control acted on is the first UI label after it, unless "scroll to", "see"…
  sits in between ("scroll to **Chatter** and click **Activities**" frames Activities);
- input steps only when the verb is an instruction ("enter the…", "type a…"), since "type" is also a noun;
- every step gets an `element` description for grounding and a `done_when` hint for the reviewer (not used by
  the engine yet);
- objective, postcondition checks, planned changes and the escalation decision are marked `DRAFT:` and must
  be written by hand;
- the draft is validated against the engine's `Procedure` model before being written.

It is a starting point, never a procedure to run as is: descriptions are guesses from the documentation and
Odoo 20 labels may differ. Matteo / Claude Code validate each step against the live screen (control framed?
progress detected?) before the YAML joins the procedures folder.

Tried on the real Odoo 19 page *Activities* (utilize_activities.html): 12 steps in documentation order, menu
paths split correctly, "Activity Types link" framed rather than the "Discuss" section scrolled to.
`scripts/test_draft_procedure.py` covers an offline fixture (HTML and Linkup-style Markdown) and engine validation.
