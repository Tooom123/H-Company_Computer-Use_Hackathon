# Eight questions for the H-Companion rehearsal

These are **rehearsal candidates**, not eight successful Holo runs. Use an
existing logged-in session, ask in English, and keep the product in front while
the companion guides. Start with **Show me**, hold **Right Option**, speak, then
release. Follow one instruction at a time. Stop task remains available in the
companion and its menu-bar icon.

## Odoo — two business questions

Start at https://holo-demo.62.83.79.254.sslip.io/odoo/crm.
This public HTTPS address needs no SSH tunnel. There are two separate logins:
the HTTP access prompt (`holo`), then Odoo (`holo-demo`). The two passwords are in
the private access handoff on Edouard's Mac; do not paste them in the companion,
the recording or Git. Select **Holo — Déjà Bu Démo · DONNÉES FICTIVES**.

1. **CRM**, start at the pipeline:

   > Help me find “Coffrets de fin d’année — Maison Aube · Démo”. Show me its current stage and next follow-up, without changing anything.

   Useful result: the correct opportunity, its stage and activity are visible.
   An activity date and a commercial stage are different fields. A partial
   answer must remain partial in the feedback.

2. **Purchases**, start at the app overview or purchase list:

   > Help me understand what is still waiting to be received on the purchase order with vendor reference DEMO-ACHAT-029. Don’t validate any receipt.

   Useful result: the correct supplier reference, ordered/received quantities,
   and the remaining receipt are identified. The supplier reference is not the
   native Odoo order number. Do not seed the answer with expected quantities.

## SAP — two purchasing questions

Open https://my426318.s4hana.cloud.sap/ui?sap-language=en&help-mixedLanguages=false
with the same user who prepared the personal draft. This is a shared trial;
the current state wins over the preparation notes.

3. **My Home**, with the tile *Holo - Achats à préparer* available:

   > Help me find my purchase draft HOLO-1107 and check whether it has already been ordered. Don’t submit it.

   Useful result: the exact draft is open and its editing/business state is
   explained. Clicking Order is outside this scenario.

4. **The same draft open**, pricing and payment terms accessible:

   > Explain why Net Order Value and Effective Value are different on this draft. Show me the relevant pricing and payment terms, without editing them.

   Useful result: both fields and the applicable condition are read. A possible
   cash discount is not proof of a payment or an already-earned discount.

## H Company — two platform questions

5. **Documentation**, start at https://hub.hcompany.ai/:

   > Show me how to run an agent in a cloud browser without taking over my Mac, and where I would attach a saved browser profile.

   Useful result: cloud/local environment distinction and the profile option are
   explained from the docs. No new run is needed. References:
   [Cloud browser](https://hub.hcompany.ai/agents-api/browser/configuration),
   [Browser profiles](https://hub.hcompany.ai/agents-api/browser/profiles).

6. **H Platform**, open one of our completed or blocked demo sessions first:

   > Help me review this session. Show me the final answer and the steps that support it, and tell me what is still unverified. Don’t rerun it.

   Useful result: visible evidence is distinguished from the agent's own claim.
   A session marked completed is not automatically a successful user task.

## Cognition — two session review questions

Use Devin Desktop with an **existing demo session open**, rather than the empty
new-task composer. The session must contain command history for question 7 and
changes or test activity for question 8. If it does not, choose another prepared
session; do not fabricate history. The web documentation describes capabilities;
Desktop may expose a different layout and the current accessibility tree wins.

7. **Session details / progress**:

   > Show me the last command and its output in this session. Help me understand whether Devin is waiting for me or encountered an error. Don’t run anything.

8. **The same session**, with edits or test history:

   > Help me review what Devin changed and which checks actually ran. Show me the evidence and tell me what still needs checking, without editing or merging anything.

Reference: [Devin Session Tools](https://docs.devin.ai/work-with-devin/devin-session-tools).
A completed task, a generated PR and passing tests are distinct observations.

## App context and autonomy

The new runtime supports `talk --software auto`. At each new request it selects
H Company, the enriched Odoo instance, this SAP trial or Devin from the observed
foreground origin/native bundle. The utterance does not choose the product. It
retrieves excerpts only from that product's local Markdown corpus, retains
versioned source citations in the request and clears cross-product history.
This is lexical retrieval, not an embedding or hybrid RAG implementation.

The companion displays **Auto context**, the selected product and the number
of retrieved excerpts. Selection happens when a new request starts, not on every
idle screen change. Switching products during guidance stops that context; ask
again in the intended product. Unknown apps and login screens do not get a
guessed profile. This is a four-product demo allowlist, not a universal detector.

The Mac launcher reads `profile: "multi-product"` from its existing private
`launcher.json`; keep the configured Python path. It starts at **Show me** with
the slider enabled. Higher levels allow the normal team engine to navigate for
the user, within the consultation-only scope of these eight demos. Raising the
slider does not authorize placing an order, payment, message or code execution.
The original `--software cognition --native-devin` observation-only research
pilot remains available and its slider deliberately stays locked.

For another development machine, with dependencies and provider keys configured:

```sh
python scripts/run-h-company-human.py --software auto --allow-actions --key alt_r --input-language fr-en
```

The backend reports the selected product per request; the Markdown excerpts are
saved in the private request trace. Human feedback must still be recorded
explicitly after each trial: **task success**, **usefulness**, and a short
comment about wrong targets, missing steps or corrections. No automatic check
is a substitute for that human label.

## Recording order

Rehearse Odoo 2 and SAP 4 first: the user's business question and the supporting
screen are concrete. Keep H 5 and Devin 7 as additional examples if they pass a
live rehearsal. Record only clean completed passages, while preserving failed
trials in the dataset. The two-minute pitch does not need all eight passages.
