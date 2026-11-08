# H Company — guided procedures for the platform and the documentation hub

Written 2026-11-08 from the public documentation (hub.hcompany.ai) and the platform's known sections. These
are **drafts for the guide engine**, in the same format as the Odoo procedures (`agent/src/hcs_agent/procedures/
hcompany_*.yaml`). **None has been run on the live site yet**: element descriptions and `done_when` sentences
must be checked with the grounding test (see `docs/grounding-odoo20-2026-11-07.md` for the method) before a demo.
Édouard's ten docs-QA scenarios (`h-company-scenarios.md`, H01–H10) stay the reference for the question-answering
arm; the procedures below are the "do it with me" arm on the same product.

## What a user can do on the H Company site, and which procedure covers it

| User need | Where | Procedure | Mode that makes sense | Risk |
| --- | --- | --- | --- | --- |
| Find the right documentation page (permissions, your browser, local runtime, skills, structured output…) | hub.hcompany.ai | `hcompany_hub_find_documentation` (param `topic`) | guide (teach the hub search) | none |
| Create an API key for a machine/project | platform › API keys | `hcompany_platform_create_api_key` | guide only — the key is a secret | the overlay never frames the key value; the verifier checks no full key is on screen |
| Redeem the hackathon promo code / check credits | platform › Settings › Billing | `hcompany_platform_redeem_credits` (param `promo_code`) | guide | must never touch Buy / Upgrade / payment method |
| Understand what an agent did (status, steps, screenshots, answer, cost) | platform › Sessions › Agent View | `hcompany_platform_review_session` | guide with a "tour" step | read-only |
| Create a reusable agent (name, environment, model) | platform › Agents | `hcompany_platform_create_agent` (params `agent_name`, `environment`) | guide or act | reversible (delete afterwards) |

Not covered on purpose: anything that spends money, shares a session publicly, deletes resources, or runs a
session from the platform UI (it would drive this very Mac while the guide is running).

## Voice requests that route to them (English or French)

- "Show me how to find the macOS permissions page in the H docs" → `hcompany_hub_find_documentation`, topic = desktop permissions
- "Montre-moi comment créer une clé API sur la plateforme H" → `hcompany_platform_create_api_key`
- "Comment entrer le code promo du hackathon ?" → `hcompany_platform_redeem_credits` (asks for the code)
- "Explique-moi ce que l'agent a fait dans la dernière session" → `hcompany_platform_review_session`
- "Crée un agent demo-web-reader avec un navigateur cloud" → `hcompany_platform_create_agent`

The router picks the software from the procedure (`hcompany`); the Odoo procedures stay available in the same
session, so one demo can chain "qualify an opportunity in Odoo" and "show me how to read the session in Agent
View" — the product story for the sponsor: the same assistant, two vendors.

## Guide steps and what is uncertain

Each YAML carries `guide_steps` with: an instruction (one short line), the `element` description Holo grounds on
a screenshot, a `why`, optional `annotations` (labels / boxes on nearby controls, e.g. "Not this: it is a
purchase" on the Upgrade button), and a `done_when` end state checked before moving on.

Uncertain until checked live (mark them in the grounding test):
- exact labels of the left navigation on platform.hcompany.ai (Agents / Sessions / API keys / Billing) and
  whether API keys live under the account menu;
- the create-key dialog: name field, one-time display, Copy button;
- the Billing page: promo code field name and the success message wording;
- Agent View: status badge, timeline, answer panel, screenshot thumbnails;
- the agent form: environment selector and Save label.

## Preconditions for a demo on the H site

- Logged in on platform.hcompany.ai in Chrome on the main display, the hub in another tab.
- A finished demo session exists (for the Agent View scenario) — not a customer's session.
- The promo code at hand; never a payment method.
- Expected screens: `expected_screen` in each YAML; recovery = H logo (home) then the Computer Use Agents section.

## Verification

Postconditions are screen checks (page displayed, item listed, no secret visible). For the API key scenario the
verifier is told never to read or repeat a key value, and the check `value_hidden` fails if a full key is shown.
