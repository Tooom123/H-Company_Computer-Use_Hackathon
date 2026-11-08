# H Platform — compact coach reference

Reviewed 2026-11-08 against official H references linked below. This is a curated map for the five demo journeys, not all H documentation or proof of this account's current settings. Exact UI labels, enabled controls and results come from the current observation.

## Product meaning and navigation

H Platform lets people configure and run computer-use agents. An **Agent** is reusable configuration: model, instructions, Skills and environments. A **Session** is one run of an agent. A **Skill** is focused Markdown guidance loaded when a matching task needs it. An **Environment** is where the agent works, such as a cloud browser or the user's browser/desktop.

Use the actual sidebar controls. These destinations are hints, never coordinates:

| User goal | Visible destination to seek | Official reference |
| --- | --- | --- |
| Configure behavior | Agents | https://hub.hcompany.ai/agents-api/agents/overview |
| Review a run and its answer | Sessions | https://hub.hcompany.ai/agents-api/sessions/overview |
| Create reusable procedures | Skills | https://hub.hcompany.ai/agents-api/skills/overview |
| Choose cloud execution | Environments or the selected agent's environment configuration | https://hub.hcompany.ai/agents-api/browser/configuration |
| Reuse a remote browser login | Browser Profiles | https://hub.hcompany.ai/agents-api/browser/profiles |
| Create a named API key | API keys in account navigation | Inspect the actual Platform form; expiration options are not assumed |
| Understand concurrent session allowance | Plans, Current plan, or read-only billing overview | https://hub.hcompany.ai/agents-api/plans-and-limits |

Known Platform entry: `https://platform.hcompany.ai`. Known Sessions list: `https://platform.hcompany.ai/agents/sessions`. Use the selected session's actual URL for details. Other account paths are deliberately not guessed from their labels.

## 1. Welcome tour

For “Hey Companion, I'm new here, give me a quick tour”, prepare a single `tour` decision. Intro example: “H Platform helps you build and run agents that work in browsers and on desktops.” Then up to three separate explanations, bound to the visible sidebar targets:

- Agents: “Agents is where you configure what your assistant does and which tools it uses.”
- Sessions: “Sessions shows each run, so you can follow its progress and read its answer.”
- Skills: “Skills give your agents reusable instructions for tasks they encounter repeatedly.”

These illustrate tone, not mandatory recorded lines. Use fewer points if fewer relevant targets are visible. Do not read the sidebar, claim to have opened pages, click, or repeat everything at the end. The runtime keeps the text central and highlights each button separately while speaking.

## 2. Named API key with limited duration

User example: “Create an API key named h-hackathon that expires in 24 hours.”

Navigate using the observed API keys control. Inspect the form before filling the requested name and selecting expiry. **No source here establishes that the UI offers a one-day expiry.** If it offers one day/24 hours, choose that. If an exact date/time is supported, use reliable displayed/current-time evidence; never invent a date. If the requested duration is unavailable, explain that fact and stop before creation rather than creating a permanent key.

A final Create/Generate action pauses for explicit human confirmation in the runtime. Use that observed button, never Enter to submit this form. Do not repeatedly propose it while waiting. The human's earlier request supplies the desired name/duration, but the final confirmation is still enforced by the local workflow. When the required expiry is unavailable, say “I can't create a key with the requested expiry here.” Do not claim that creation will proceed.

Never narrate, copy, export or place the generated secret in another field. Secret-like text is removed before model context and private observation logging. Inspect only the non-secret success message, row name and expiry. If they are visible, a suitable closing line is “Your h-hackathon key is created with the selected expiry.” Only mention the expiry if confirmed. Do not attach it to an agent, test it, or revoke other keys.

## 3. Run in the cloud without occupying the Mac

A cloud browser runs on H infrastructure; `user_device` uses the person's own browser. The documented browser environment has `host: cloud` by default. Product configuration and the screen still decide what is actually selected.

For “How can I launch an agent without monopolizing my computer?”, explain cloud execution in one sentence and show Environments or the selected agent's environment controls. This is focused configuration help, not a tour: select only the next relevant control. Stop when the correct cloud setting is visible. The question asks how/where: it does not request starting a session or saving changes. If the setting cannot be located on the current page, use the observed navigation or open the official browser reference in a new tab in ACT.

Signing into the H dashboard does not sign websites into a separate cloud browser. Browser Profiles preserve remote browser cookies/storage for later sessions; vaults are a different credential mechanism. Explain this only if the user asks; do not interrupt the cloud demo with a login tutorial.

## 4. Create a Skill that coaches users

A request to **create** a Skill in ACT authorizes filling and saving that Skill. A request about what Skills are or where to create one does not. Use the requested name; if none is given for this demo, use `guided-onboarding`. Check the current catalog before creating duplicates. If the same name exists, show it and ask whether the person wants to update it; do not overwrite silently.

H Skill fields are `name`, `description` (when to load it), and `body` (focused Markdown instructions). The description is the agent's trigger; the body should stand alone. Example description:

“Use when a person wants step-by-step help learning or navigating software while keeping control of their computer.”

Example short body to adapt to the request, placed in `text` for the editor rather than spoken:

```markdown
# Guided onboarding
Act as a patient software coach. Use the current page to identify the next useful step.
Explain one action at a time in one short sentence and identify its visible control.
Let the user click, type, scroll and submit. Do not perform their task or change application data.
Wait for the user to act, then inspect the updated screen before continuing.
If the expected result is missing, explain what is visible and offer one alternative.
Stop when the requested outcome is visible. Do not read a long recap or claim unverified success.
```

Fill observed fields one at a time using `type`, which focuses and fills the target in one step. Do not issue `click` with field text. Retain line breaks in the body. Narrate each stage briefly, for example “I'll give this Skill a clear trigger and a step-by-step coaching procedure.” Do not read its Markdown aloud. Save once. Then inspect the success message, saved row or reopened detail before saying it exists. Do not attach it to another agent unless requested.

A Skill is loaded on demand. H explicitly places always-on behavior in the agent's `instructions`; a strict coaching agent should also have an action policy that prevents autonomous user-task execution. Creating this Skill alone does not guarantee those settings are applied. Explain that in one short sentence if it matters to the user's request, without opening an unrelated configuration journey.

## 5. Concurrent sessions and plans

Use **sessions**, not the number of agent configurations: one agent can have multiple runs. H exposes a session quota with `limit`, `active` and `available`. The current observation may include an authenticated `account_quota` object from that endpoint. Its source is the H API account connected to Companion, which may differ from the account signed into the browser. Unless their identity is explicitly matched, describe it as the connected API account, not the browser account. The public plan table is general reference only.

If `account_quota.limit` is a number, state it as the connected API account’s concurrent-session limit; only call it the current browser account’s limit when their identity is confirmed. If `active` and `available` are supplied, distinguish them from the limit; “10 total, 3 in use, 7 available” are different facts. Use only present values. If no account evidence is available, say that the current limit has not been confirmed, and show where to check it.

For “how many”, give the verified allowance and highlight Plans/Current plan if visible; do not delay the fact with a long navigation sequence. For “open/show the plans page”, actually guide the user to that observed destination in GUIDE or navigate in ACT before concluding that the page is shown.

The public documentation currently lists Free 3, Builder 10, Startup 100, Enterprise custom. It also tells clients to read live allowance values rather than hard-code them. Do not infer this user's plan or quota from these numbers. Open the official plans documentation in a separate tab when useful, or inspect the observed account Plans/billing overview read-only. Never click Upgrade/Subscribe, change card details, or purchase.

A session consumes a slot after leaving queued until terminal. Queued sessions do not occupy a slot. This detail is useful only if the user asks why a run is waiting; do not lecture about queue mechanics during a short quota answer.

## Other useful support answers

An `interrupted` session may have been cancelled or ended while idle to free capacity. It can still contain an answer. Inspect the selected run's Answer/Agent Answer area separately from status. Neither a model answer nor `completed` independently proves the business task succeeded.

When opening documentation, preserve the current Platform tab, use the exact relevant official URL, and inspect the destination. Point to the relevant heading or scroll modestly to the useful section. Do not claim a paragraph is shown merely because the URL opened.

## Sources and limits

Official references consulted on 2026-11-08: [Agents](https://hub.hcompany.ai/agents-api/agents/overview), [Sessions](https://hub.hcompany.ai/agents-api/sessions/overview), [Skills](https://hub.hcompany.ai/agents-api/skills/overview), [Cloud browser](https://hub.hcompany.ai/agents-api/browser/configuration), [Browser profiles](https://hub.hcompany.ai/agents-api/browser/profiles), [Plans and limits](https://hub.hcompany.ai/agents-api/plans-and-limits).

These sources substantiate concepts, fields and general limits. They do not validate this coach's execution, the user's current plan, or the availability of one-day API-key expiration. Every demo still needs a live end-to-end rehearsal; traces, observed results and explicit human feedback remain separate.
