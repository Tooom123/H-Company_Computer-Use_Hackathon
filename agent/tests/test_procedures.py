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


def test_answer_without_result_falls_back_on_session_outcome():
    from hcs_agent.backend import InterventionAnswer, _lenient

    raw = {"blocker": "Opportunity not found", "summary": "no record", "steps_taken": ["opened CRM"]}
    ans = _lenient(InterventionAnswer, raw)
    assert ans is not None
    assert ans.to_declared("blocked").outcome == "blocked"
    assert ans.to_declared("success").outcome == "done"
    assert ans.to_declared(None).outcome == "unclear"


def test_actor_closing_separates_conversation_from_structured_audit():
    from hcs_agent.contract import Mode
    from hcs_agent.backend import InterventionAnswer
    req = InterventionRequest(software='h-company', goal='A quick welcome tour', procedure_id='generic', mode=Mode.act)
    bound = ProcedureRegistry().for_request(req).bound(req)
    message = bound.task_message()
    assert 'one short conversational closing' in message
    assert 'never in public content' in message
    assert 'without recapping the areas already explained' in message
    assert 'one-paragraph summary' not in message
    assert 'without repeating' in InterventionAnswer.model_fields['summary'].description
