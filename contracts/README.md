# Shared contracts

JSON Schemas generated from `agent/src/hcs_agent/contract.py` with `scripts/export_contracts.py`.
Do not edit by hand; change the pydantic models and regenerate.

| Schema | Direction | Purpose |
| --- | --- | --- |
| `InterventionRequest` | app → agent | session_id, software, role, goal, symptom, procedure_id, parameters |
| `ApproveCommand` | app → agent | approve or decline the proposed scope, optional scope_note |
| `StopCommand` | app → agent | stop now; changes already made are not reverted |
| `FeedbackCommand` | app → agent | user feedback, consent to share screenshots with support |
| `ProposedPlan` | agent → app | objective, planned changes, allowed / forbidden actions, reversible, max_attempts |
| `AgentEvent` | agent → app, backend | type, state, message, data, `simulated` |
| `InterventionReport` | agent → backend | declared vs verified result, category, status, escalation, evidence, timings |

Enumerations: `State` (created, preflight_failed, awaiting_approval, running, verifying, stopping, stopped,
resolved, escalated, failed), `Category` (usage, configuration, permissions, data, suspected_product_defect,
environment, agent_failure, unknown), `CaseStatus` (resolved, workaround, escalated, abandoned),
`SessionType` (onboarding, configuration, support, discovery, feedback).
