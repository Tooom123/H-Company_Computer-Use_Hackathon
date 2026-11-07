import pytest

from hcs_agent.contract import InterventionRequest
from hcs_agent.procedures import ProcedureRegistry


def test_all_procedures_load_and_render():
    reg = ProcedureRegistry()
    assert {p.id for p in reg.all()} >= {"odoo_crm_followup_activity", "odoo_crm_change_stage_restricted"}
    req = InterventionRequest(software="odoo", goal="g", procedure_id="odoo_crm_followup_activity",
                              parameters={"opportunity": "Acme Demo", "due_date": "2026-11-14"})
    b = reg.for_request(req).bound(req)
    assert "Acme Demo" in b.objective and "2026-11-14" in b.objective
    assert "{" not in b.agent_instructions  # every placeholder resolved
    assert "{" not in b.task_message()
    plan = b.plan()
    assert plan.reversible and plan.max_attempts == 2
    assert any("email" in x.lower() for x in plan.forbidden_actions)


def test_ambiguous_software_requires_procedure_id():
    with pytest.raises(ValueError):
        ProcedureRegistry().for_request(InterventionRequest(software="odoo", goal="g"))


def test_agent_names_follow_h_rules():
    from hcs_agent.backend import _agent_name

    assert _agent_name("hcs-odoo_crm_followup_activity") == "hcs-odoo-crm-followup-activity"
    assert _agent_name("Hcs Verify__X-") == "hcs-verify-x"
