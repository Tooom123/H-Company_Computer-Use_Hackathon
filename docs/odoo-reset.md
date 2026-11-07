# Odoo demo reset and restricted sales user

`scripts/odoo_reset.py` puts the Odoo CRM demo instance back in its known state before each take
(docs/TODO-tom.md, item 1). Standard library only; credentials come from the environment, never from Git.

```bash
export ODOO_URL=http://holo.localhost:18090 ODOO_DB=<db> ODOO_USER=<admin login> ODOO_PASSWORD=<admin password or API key>
python scripts/odoo_reset.py --check        # read-only: exit 1 and list what is not clean
python scripts/odoo_reset.py --dry-run      # what would change
python scripts/odoo_reset.py                # reset (idempotent), then re-check

export ODOO_SALES_LOGIN=demo.sales ODOO_SALES_PASSWORD=<choose one, share it in the private channel>
python scripts/odoo_reset.py --sales-user   # + create/repair the restricted sales user and prove the blocked case
```

## Known state after a reset

- no opportunity named `Zz Test*` (archived ones included);
- exactly one active contact `Acme Corp` (duplicates archived, not deleted);
- `Acme Demo` recreated in the first `New` stage: no contact, no expected revenue, no activity, no note,
  salesperson = the admin account that ran the reset.

## Restricted sales user (blocked scenario `odoo_crm_change_stage_restricted`)

Groups: Internal user + **Sales: User: Own Documents Only** + a demo group *"H Companion demo: read the whole
pipeline (read-only)"*. Without that read-only rule Odoo hides `Acme Demo` from an own-documents user (one
rule covers read and write), so the agent would never reach the Won button. With it, the card is visible and
moving it to Won fails with Odoo's access error, which is the escalation we want to show.

The script logs in as that user and checks both points (`blocked_scenario.visible` and `won_refused`); it fails
loudly if the user could win the opportunity or cannot see it. Manager / "All Documents" rights are removed on
every run.

## Verified

Against a disposable Odoo 19 (Docker, `crm` installed, no demo data): dirty state (2 `Zz Test`, archived test
lead, duplicated contact, `Acme Demo` in Won with contact, revenue, activity and note) → `--check` lists the 7
problems → reset → clean; second run changes nothing; restricted user sees `Acme Demo`, Won refused, own
opportunity can be won. `scripts/test_odoo_reset.py` replays this (needs `ODOO_TEST_URL`, `ODOO_TEST_DB`;
skipped otherwise; never point it at the shared instance).

Still to do on the demo Mac (Odoo 20 on Netcup, labels may differ): run `--check` then the reset, create the
user with `--sales-user`, then the PRD rule: the success case passes **3 times in a row** from this state, each
run logged in `docs/test-log.md`.
