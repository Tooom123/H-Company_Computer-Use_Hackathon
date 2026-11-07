#!/usr/bin/env python3
"""Put the Odoo CRM demo instance back to its known state before a demo take (idempotent).

What it does (docs/TODO-tom.md, item 1):
- deletes every opportunity / lead named "Zz Test*" (archived ones included);
- makes sure the contact "Acme Corp" exists exactly once (creates it, archives duplicates);
- recreates "Acme Demo" in the first "New" stage: no contact, no expected revenue, no activity, no note,
  salesperson = the admin account running the reset (so a restricted sales user cannot change it);
- optionally creates / repairs a sales user WITHOUT manager rights ("Sales: User: Own Documents Only"),
  needed by the blocked scenario `odoo_crm_change_stage_restricted` (Won refused -> escalation). That user
  also gets a read-only rule on the whole pipeline (otherwise Odoo hides "Acme Demo" from them entirely),
  and the script logs in as them to prove the card is visible and Won is refused.

Standard library only (XML-RPC). Credentials come from the environment, never from the command line:

    ODOO_URL=http://holo.localhost:18090   ODOO_DB=<database>
    ODOO_USER=<admin login>                ODOO_PASSWORD=<admin password or API key>
    ODOO_SALES_LOGIN=demo.sales            ODOO_SALES_PASSWORD=<password for the restricted user>

    python scripts/odoo_reset.py                 # reset the demo data
    python scripts/odoo_reset.py --sales-user    # + create/repair the restricted sales user
    python scripts/odoo_reset.py --check         # only check the state, exit 1 if not clean
    python scripts/odoo_reset.py --dry-run       # show what would change
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import xmlrpc.client
from dataclasses import dataclass, field
from typing import Any

TEST_PREFIX = "Zz Test"
DEMO_OPPORTUNITY = "Acme Demo"
DEMO_CONTACT = "Acme Corp"
ALL = {"context": {"active_test": False}}  # include archived records


class OdooError(RuntimeError):
    pass


@dataclass
class Odoo:
    url: str
    db: str
    login: str
    password: str
    uid: int = 0
    _models: Any = field(default=None, repr=False)

    def connect(self) -> Odoo:
        common = xmlrpc.client.ServerProxy(f"{self.url.rstrip('/')}/xmlrpc/2/common", allow_none=True)
        try:
            self.uid = common.authenticate(self.db, self.login, self.password, {})
        except (OSError, xmlrpc.client.Error) as e:
            raise OdooError(f"cannot reach Odoo at {self.url}: {e}") from e
        if not self.uid:
            raise OdooError(f"authentication refused for {self.login!r} on database {self.db!r}")
        self._models = xmlrpc.client.ServerProxy(f"{self.url.rstrip('/')}/xmlrpc/2/object", allow_none=True)
        return self

    def call(self, model: str, method: str, *args: Any, **kw: Any) -> Any:
        try:
            return self._models.execute_kw(self.db, self.uid, self.password, model, method, list(args), kw)
        except xmlrpc.client.Fault as e:
            lines = [ln.strip() for ln in e.faultString.strip().splitlines() if ln.strip()]
            # Odoo access errors end with a joke line; keep the line that says what is refused
            useful = [ln for ln in lines if "access" in ln.lower() or "not allowed" in ln.lower()]
            raise OdooError(f"{model}.{method}: {(useful or lines or ['?'])[0]}") from e

    def search_read(self, model: str, domain: list, fields: list[str], **kw: Any) -> list[dict]:
        return self.call(model, "search_read", domain, fields=fields, **ALL, **kw)

    def xmlid(self, module: str, name: str) -> int | None:
        rows = self.call("ir.model.data", "search_read", [("module", "=", module), ("name", "=", name)],
                         fields=["res_id"], limit=1)
        return rows[0]["res_id"] if rows else None

    def has_field(self, model: str, name: str) -> bool:
        return name in self.call(model, "fields_get", [name], attributes=["type"])


def new_stage_id(odoo: Odoo) -> int:
    stages = odoo.call("crm.stage", "search_read", [], fields=["name", "sequence"], order="sequence,id")
    if not stages:
        raise OdooError("no CRM stage found (is the CRM app installed?)")
    named_new = [s for s in stages if str(s["name"]).strip().lower() == "new"]
    return (named_new or stages)[0]["id"]


def reset(odoo: Odoo, dry_run: bool = False) -> dict[str, Any]:
    report: dict[str, Any] = {}

    # 1. test leftovers
    leftovers = odoo.search_read("crm.lead", [("name", "=ilike", f"{TEST_PREFIX}%")], ["id", "name"])
    report["deleted_test_opportunities"] = [r["name"] for r in leftovers]
    if leftovers and not dry_run:
        odoo.call("crm.lead", "unlink", [r["id"] for r in leftovers])

    # 2. contact "Acme Corp", exactly once (active)
    contacts = odoo.search_read("res.partner", [("name", "=", DEMO_CONTACT)], ["id", "active"], order="id")
    if not contacts:
        report["contact"] = "created"
        if not dry_run:
            odoo.call("res.partner", "create", {"name": DEMO_CONTACT, "is_company": True})
    else:
        active = [c for c in contacts if c["active"]]
        keep = active[0] if active else contacts[0]
        extra = [c for c in active if c["id"] != keep["id"]]  # already-archived duplicates are left alone
        report["contact"] = ("kept" if keep["active"] else "restored") + (
            f", archived {len(extra)} duplicate(s)" if extra else "")
        if not dry_run:
            if not keep["active"]:
                odoo.call("res.partner", "write", [keep["id"]], {"active": True})
            if extra:
                odoo.call("res.partner", "write", [c["id"] for c in extra], {"active": False})

    # 3. "Acme Demo": recreated from scratch, so no activity / note / revenue / contact can survive
    old = odoo.search_read("crm.lead", [("name", "=", DEMO_OPPORTUNITY)], ["id"])
    report["recreated_opportunity"] = DEMO_OPPORTUNITY
    report["removed_previous_versions"] = len(old)
    if not dry_run:
        if old:
            odoo.call("crm.lead", "unlink", [r["id"] for r in old])
        odoo.call("crm.lead", "create", {
            "name": DEMO_OPPORTUNITY, "type": "opportunity", "stage_id": new_stage_id(odoo),
            "partner_id": False, "expected_revenue": 0, "user_id": odoo.uid,
        })
    return report


def groups_field(odoo: Odoo) -> str:
    """Odoo <= 18: groups_id; Odoo 19+: group_ids."""
    return "group_ids" if odoo.has_field("res.users", "group_ids") else "groups_id"


READ_ALL_GROUP = "H Companion demo: read the whole pipeline (read-only)"


def ensure_read_all_group(odoo: Odoo) -> int:
    """Group + record rule giving READ access to every opportunity, and nothing else.

    Odoo applies one record rule to read and write for "Own Documents Only" users, so such a user would not
    even see an opportunity owned by someone else. Rules are OR-ed per operation: adding a read-only rule
    lets the restricted user open "Acme Demo" while writes stay limited to their own documents, which is
    exactly the blocked scenario (moving it to Won is refused with an Access Error).
    """
    groups = odoo.call("res.groups", "search_read", [("name", "=", READ_ALL_GROUP)], fields=["id"], limit=1)
    gid = groups[0]["id"] if groups else odoo.call("res.groups", "create", {"name": READ_ALL_GROUP})
    model_id = odoo.call("ir.model", "search_read", [("model", "=", "crm.lead")], fields=["id"], limit=1)[0]["id"]
    rule = {"name": f"{READ_ALL_GROUP} (crm.lead)", "model_id": model_id, "domain_force": "[(1, '=', 1)]",
            "groups": [(6, 0, [gid])], "perm_read": True, "perm_write": False, "perm_create": False,
            "perm_unlink": False}
    rules = odoo.call("ir.rule", "search_read", [("name", "=", rule["name"])], fields=["id"], **ALL)
    if rules:
        odoo.call("ir.rule", "write", [rules[0]["id"]], {**rule, "active": True})
    else:
        odoo.call("ir.rule", "create", rule)
    return gid


def ensure_sales_user(odoo: Odoo, login: str, password: str, dry_run: bool = False) -> dict[str, Any]:
    """A sales user restricted to its own documents (no 'All Documents', no manager rights) who can still
    read the whole pipeline, so the blocked scenario shows an Access Error instead of a missing card."""
    internal = odoo.xmlid("base", "group_user")
    own_docs = odoo.xmlid("sales_team", "group_sale_salesman")
    forbidden = [g for g in (odoo.xmlid("sales_team", "group_sale_salesman_all_leads"),
                             odoo.xmlid("sales_team", "group_sale_manager"),
                             odoo.xmlid("base", "group_system"), odoo.xmlid("base", "group_erp_manager")) if g]
    if not (internal and own_docs):
        raise OdooError("sales_team groups not found (is the CRM / Sales app installed?)")
    gf = groups_field(odoo)
    users = odoo.search_read("res.users", [("login", "=", login)], ["id", "active"])
    out: dict[str, Any] = {"login": login, "groups": "Sales: User: Own Documents Only + read-only pipeline"}
    out["action"] = "repaired" if users else "created"
    if dry_run:
        return out
    groups = [internal, own_docs, ensure_read_all_group(odoo)]
    if not users:
        odoo.call("res.users", "create", {"name": "Demo Sales (restricted)", "login": login,
                                          "password": password, gf: [(6, 0, groups)]})
    else:
        # reset to exactly these groups (drops any manager / all-documents right added by hand)
        odoo.call("res.users", "write", [users[0]["id"]], {"active": True, "password": password,
                                                            gf: [(6, 0, groups)]})
    uid = odoo.search_read("res.users", [("login", "=", login)], ["id"])[0]["id"]
    has = set(odoo.search_read("res.users", [("id", "=", uid)], [gf])[0][gf])
    leaked = [g for g in forbidden if g in has]
    if leaked:
        raise OdooError(f"user {login} still has manager rights (implied groups {leaked}); fix by hand")
    out["verified_no_manager_rights"] = True
    out["blocked_scenario"] = verify_blocked_scenario(odoo, login, password)
    return out


def verify_blocked_scenario(admin: Odoo, login: str, password: str) -> dict[str, Any]:
    """Log in as the restricted user: Acme Demo must be visible, and moving it to Won must be refused."""
    user = Odoo(admin.url, admin.db, login, password).connect()
    leads = user.call("crm.lead", "search_read", [("name", "=", DEMO_OPPORTUNITY)], fields=["id"])
    if not leads:
        raise OdooError(f"{login} cannot see '{DEMO_OPPORTUNITY}': the blocked scenario would not show the card")
    won = [s["id"] for s in admin.call("crm.stage", "search_read", [], fields=["name"]) if s["name"].lower() == "won"]
    if not won:
        return {"visible": True, "won_refused": None, "note": "no 'Won' stage found"}
    try:
        user.call("crm.lead", "write", [leads[0]["id"]], {"stage_id": won[0]})
    except OdooError as e:
        return {"visible": True, "won_refused": True, "error_shown": str(e)[:160]}
    raise OdooError(f"{login} could move '{DEMO_OPPORTUNITY}' to Won: the blocked scenario would succeed")


def check(odoo: Odoo) -> dict[str, Any]:
    """Read-only: is the instance in the demo state?"""
    problems = []
    if odoo.search_read("crm.lead", [("name", "=ilike", f"{TEST_PREFIX}%")], ["id"]):
        problems.append(f"'{TEST_PREFIX}*' opportunities still present")
    contacts = odoo.search_read("res.partner", [("name", "=", DEMO_CONTACT), ("active", "=", True)], ["id"])
    if len(contacts) != 1:
        problems.append(f"{len(contacts)} active '{DEMO_CONTACT}' contacts (expected 1)")
    opps = odoo.search_read("crm.lead", [("name", "=", DEMO_OPPORTUNITY)],
                            ["stage_id", "partner_id", "expected_revenue", "activity_ids", "active"])
    if len(opps) != 1:
        problems.append(f"{len(opps)} '{DEMO_OPPORTUNITY}' opportunities (expected 1)")
    else:
        o = opps[0]
        if not o["active"]:
            problems.append(f"'{DEMO_OPPORTUNITY}' is archived")
        if o["stage_id"] and o["stage_id"][0] != new_stage_id(odoo):
            problems.append(f"'{DEMO_OPPORTUNITY}' is in stage {o['stage_id'][1]!r}, not New")
        if o["partner_id"]:
            problems.append(f"'{DEMO_OPPORTUNITY}' has a contact")
        if o["expected_revenue"]:
            problems.append(f"'{DEMO_OPPORTUNITY}' has an expected revenue")
        if o["activity_ids"]:
            problems.append(f"'{DEMO_OPPORTUNITY}' has {len(o['activity_ids'])} activity(ies)")
        notes = odoo.call("mail.message", "search_count",
                          [("model", "=", "crm.lead"), ("res_id", "=", o["id"]), ("message_type", "=", "comment")])
        if notes:
            problems.append(f"'{DEMO_OPPORTUNITY}' has {notes} note(s)/message(s)")
    return {"clean": not problems, "problems": problems}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--check", action="store_true", help="only check the demo state (exit 1 if not clean)")
    p.add_argument("--dry-run", action="store_true", help="show what would change, change nothing")
    p.add_argument("--sales-user", action="store_true", help="also create/repair the restricted sales user")
    a = p.parse_args(argv)
    env = {k: os.environ.get(k, "") for k in ("ODOO_URL", "ODOO_DB", "ODOO_USER", "ODOO_PASSWORD")}
    missing = [k for k, v in env.items() if not v]
    if missing:
        print(f"missing environment variables: {', '.join(missing)}", file=sys.stderr)
        return 2
    try:
        odoo = Odoo(env["ODOO_URL"], env["ODOO_DB"], env["ODOO_USER"], env["ODOO_PASSWORD"]).connect()
        if a.check:
            result = check(odoo)
        else:
            result = {"reset": reset(odoo, dry_run=a.dry_run), "dry_run": a.dry_run}
            if a.sales_user:
                login = os.environ.get("ODOO_SALES_LOGIN", "demo.sales")
                pwd = os.environ.get("ODOO_SALES_PASSWORD", "")
                if not pwd:
                    print("ODOO_SALES_PASSWORD is required with --sales-user", file=sys.stderr)
                    return 2
                result["sales_user"] = ensure_sales_user(odoo, login, pwd, dry_run=a.dry_run)
            if not a.dry_run:
                result["check"] = check(odoo)
    except OdooError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if a.check or "check" in result:
        return 0 if (result if a.check else result["check"])["clean"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
