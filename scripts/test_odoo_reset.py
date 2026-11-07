"""Integration test of scripts/odoo_reset.py against a real, disposable Odoo (skipped without one).

    docker run ... odoo:19 -- -d hcstest -i crm --without-demo=all --stop-after-init   # once
    ODOO_TEST_URL=http://127.0.0.1:18069 ODOO_TEST_DB=hcstest pytest scripts/test_odoo_reset.py

Never point this at the shared demo instance: it creates and deletes records on purpose.
"""

import os
import sys
import xmlrpc.client
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import odoo_reset as R  # noqa: E402

URL, DB = os.environ.get("ODOO_TEST_URL"), os.environ.get("ODOO_TEST_DB")
pytestmark = pytest.mark.skipif(not (URL and DB), reason="needs a disposable Odoo (ODOO_TEST_URL, ODOO_TEST_DB)")


@pytest.fixture()
def admin():
    return R.Odoo(URL, DB, os.environ.get("ODOO_TEST_USER", "admin"), os.environ.get("ODOO_TEST_PASSWORD", "admin")).connect()


def _dirty(o):
    for n in ("Zz Test 1", "Zz Test 2"):
        o.call("crm.lead", "create", {"name": n, "type": "opportunity"})
    for _ in range(2):
        o.call("res.partner", "create", {"name": R.DEMO_CONTACT, "is_company": True})
    lead = o.call("crm.lead", "create", {"name": R.DEMO_OPPORTUNITY, "type": "opportunity", "expected_revenue": 900})
    o.call("crm.lead", "activity_schedule", [lead], act_type_xmlid="mail.mail_activity_data_todo", summary="x")
    o.call("crm.lead", "message_post", [lead], body="note", message_type="comment", subtype_xmlid="mail.mt_note")


def test_reset_cleans_a_dirty_instance_and_is_idempotent(admin):
    _dirty(admin)
    assert R.check(admin)["clean"] is False
    R.reset(admin)
    assert R.check(admin) == {"clean": True, "problems": []}
    second = R.reset(admin)
    assert second["deleted_test_opportunities"] == [] and "archived" not in second["contact"]
    assert R.check(admin)["clean"] is True


def test_dry_run_changes_nothing(admin):
    admin.call("crm.lead", "create", {"name": "Zz Test dry", "type": "opportunity"})
    plan = R.reset(admin, dry_run=True)
    assert "Zz Test dry" in plan["deleted_test_opportunities"]
    assert R.check(admin)["clean"] is False
    R.reset(admin)


def test_restricted_user_sees_acme_demo_but_cannot_win_it(admin):
    R.reset(admin)
    out = R.ensure_sales_user(admin, "hcs.test.sales", "hcs-test-pw")
    assert out["verified_no_manager_rights"] and out["blocked_scenario"]["won_refused"] is True
    user = R.Odoo(URL, DB, "hcs.test.sales", "hcs-test-pw").connect()
    own = user.call("crm.lead", "create", {"name": "Zz Test own", "type": "opportunity"})
    won = [s["id"] for s in admin.call("crm.stage", "search_read", [], fields=["name"]) if s["name"].lower() == "won"][0]
    user.call("crm.lead", "write", [own], {"stage_id": won})  # their own opportunity: allowed
    again = R.ensure_sales_user(admin, "hcs.test.sales", "hcs-test-pw")  # idempotent repair
    assert again["action"] == "repaired" and again["blocked_scenario"]["won_refused"] is True
    R.reset(admin)
