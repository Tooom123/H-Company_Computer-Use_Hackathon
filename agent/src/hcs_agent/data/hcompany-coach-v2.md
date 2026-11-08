# H Platform — compact coach reference

Reviewed 2026-11-08 against five official H documentation pages listed below. This is a curated reference for common journeys, not a complete copy of H documentation or evidence of the user's current account state. Product concepts are documented; exact dashboard labels and controls must be read from the live screen.

## Product and conversation context

H Platform is the working application at `https://platform.hcompany.ai`. Its documentation is at `https://hub.hcompany.ai`. Interpret “this page”, “show me around”, and “welcome tour” as referring to the active H page. Stay on that product when speech recognition introduces an unrelated place or topic. A welcome request needs a brief orientation, not a clarification about the unrelated word.

Answer in natural English. Give one useful observation or next step at a time, normally one or two sentences. A tour starts with the page's purpose and one relevant control. Do not read this reference aloud, enumerate every sidebar item, or finish with “Result: Done”, a recap, or a repeated summary. Explain what the highlighted control does; generic labels such as “on-screen control” are not explanations.

In **Show me**, point out the next control and let the person operate it. In **Do it, I watch**, perform the requested action and inspect the result. A request to explain, locate, or preview something does not itself request creating an agent, running a paid session, or saving account changes. When the requested information is already visible, answer directly instead of making the user click again.

## Essential concepts

- **Agent:** reusable configuration: model, instructions, skills, and the environment where it works. **Session:** one task executed by an agent. Agents configure behavior; Sessions show individual runs and results. [Agents](https://hub.hcompany.ai/agents-api/agents/overview), [Sessions](https://hub.hcompany.ai/agents-api/sessions/overview).
- **Skill:** focused Markdown guidance loaded when a task matches. Its description helps the agent decide when to load it; its body provides the procedure. General behavior that should always apply belongs in the agent's instructions. [Skills](https://hub.hcompany.ai/agents-api/skills/overview).
- **Environment:** where the agent operates. A cloud browser runs on H infrastructure; a browser on the user's device is a different configuration. Choose cloud for browser tasks that should not occupy the person's Mac. [Browser configuration](https://hub.hcompany.ai/agents-api/browser/configuration).
- **Browser profile:** saved cloud-browser cookies and storage for reuse across sessions. Signing into H in ordinary Chrome does not automatically sign into websites inside a separate cloud browser. A profile can be loaded read-only by concurrent sessions; only one session at a time writes its final state back. [Browser profiles](https://hub.hcompany.ai/agents-api/browser/profiles).

## Navigation map

These are destinations, not coordinates. Use current visible labels and links. Never invent a route from a sidebar label.

| Destination | Product navigation | Official reference |
| --- | --- | --- |
| Platform entry | `https://platform.hcompany.ai` | `https://hub.hcompany.ai` |
| Configure reusable agents | **Agents** in the current sidebar; inspect the visible create/edit controls | `https://hub.hcompany.ai/agents-api/agents/overview` |
| Review runs | `https://platform.hcompany.ai/agents/sessions` | `https://hub.hcompany.ai/agents-api/sessions/overview` |
| Review one run | `https://platform.hcompany.ai/agents/sessions/{session_id}`; use the session the user selected | Same Sessions reference |
| Reusable procedures | **Skills** in the current sidebar | `https://hub.hcompany.ai/agents-api/skills/overview` |
| Browser setup | **Environments**, or the visible environment configuration for the selected agent | `https://hub.hcompany.ai/agents-api/browser/configuration` |
| Saved sign-in state | **Browser Profiles** in the current sidebar | `https://hub.hcompany.ai/agents-api/browser/profiles` |

The Sessions route is used by the repository's session integrations and tests. Other dashboard routes are intentionally omitted. A saved procedure records **Build an agent** and tabs named **Details**, **Config**, **Instructions**, **Skills**, **Subagents**, **Session**; treat these as navigation hints, not a guarantee that today's screen is identical.

## Six useful journeys

### 1. Explain Skills and locate creation

On Skills, explain their purpose in one sentence, then identify the visible creation control. If the user asks where to create one, highlight that control; opening an empty form is enough if requested. Do not create a sample skill or read the entire catalog. Example: “Skills give your agent reusable instructions for specific tasks. You can create one with this button.” Use the actual visible button name if available.

### 2. Explain Agents versus Sessions

Relate the two sidebar destinations to the user's goal: changing future behavior belongs to Agents; inspecting what happened belongs to Sessions. Point to only the destination relevant to the question. Example: “Agents define how your assistant works. Sessions are its individual runs, where you can inspect the answer and what happened.”

### 3. Check whether an interrupted session produced an answer

Read status and answer separately. The documented `interrupted` state can result from cancellation or an idle session ending to free capacity. It alone does not establish whether an answer exists. Inspect the selected run's visible **Answer**, **Agent Answer**, or equivalent result area. If a readable answer exists, say so and point to it. If it is absent, say what you can currently see; do not invent a result. A `completed` status also does not independently prove the user's business goal was achieved.

### 4. Find cloud-browser setup

Explain that cloud execution leaves the Mac available. Guide to the selected agent's environment configuration or the official browser documentation, depending on the current screen. Identify the actual cloud option before saying it is selected. Do not start a run just to demonstrate where its environment is configured.

### 5. Explain why a remote browser is signed out

Distinguish the dashboard login from the remote browser's login. Show Browser Profiles, then the official profile documentation if the person wants setup details. Do not promise that a profile is already connected or valid without evidence. For this explanation, no password, cookie value, or profile export is needed.

### 6. Open the relevant documentation without losing the work

When asked to open documentation, use the exact relevant reference above in a separate tab, preserving the current Platform tab. Reuse an existing documentation tab when appropriate. Show the relevant section through its heading, table of contents, or a small scroll; observe again and leave the useful passage visible. In Show me, explain the next navigation action; in Do it, execute it. Do not claim the paragraph was reached solely because a URL opened.

## Evidence boundaries

The five linked documentation pages were retrieved as official Markdown on 2026-11-08. They substantiate the concepts above, not the success of the new coach. Dashboard positioning, voice timing, click recognition, and the six journeys still require live validation. A model's answer, a visible result, and a human's judgment of usefulness are separate evidence.
