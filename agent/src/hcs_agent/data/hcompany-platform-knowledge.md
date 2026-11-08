H Platform reference knowledge (official docs at hub.hcompany.ai, read 2026-11-08: agents, environments, cloud
browser, skills, subagents, sessions, watch and steer). Use it to explain what the person sees; the live page wins
when they differ.

Agents
- An agent is a saved configuration: environment + model + instructions + skills (+ subagents). Saving adds it to
  the catalog; every later edit creates a new revision ("name:3" pins one, a bare name runs the latest).
- Pre-built agents (h/...) run as-is, e.g. h/web-surfer-flash for quick web tasks.

Build an agent wizard (Details, Config, Instructions, Skills, Subagents, Session)
- Details. Name = the id passed as the agent when a session starts (lowercase letters, digits, hyphens).
  Description (required) = one line on what the agent does; a manager agent reads it to decide whether to
  delegate to this one, so write it as a capability ("Reads a web page and reports its main heading").
- Config, environment = where the agent acts. Cloud browser / web environment (the default): a browser H hosts for
  each session, nothing runs on your machine. Your browser: your own Chrome with your logins. Your desktop: your
  screen, mouse and keyboard. The cloud browser has two modes: visual (default; sees screenshots, can click and
  fill forms) and text (reads the page as text only: cheapest and fastest, but read-only).
- Config, model = the Holo model that drives the agent. Platform default holo4-27b; holo4-35b-a3b for lower
  latency. Reasoning effort, when shown, is how long the model thinks before each step.
- Config, answer format = free-form text by default; a JSON Schema makes the final answer structured data.
- Instructions = text appended to the system prompt to steer behaviour (output format, rules), e.g. "Return one
  line: the heading text and the URL."
- Skills = Markdown instructions the agent loads only when a task matches them; H ships ready-made computer-use
  skills under h/. None are needed for a simple read task.
- Subagents = other agents this one may delegate to: it becomes a manager that splits work into parallel child
  sessions (one per site or source) and merges the result. You still run one session and get one result. Each
  child is an isolated session with its own browser; the manager may spawn follow-ups to fill gaps or verify
  findings, and routes on each agent's description. Children count toward the concurrency limit (subagents fail
  when it is reached). Leave empty for a simple agent.
- Session = the first task. The prompt is the task, written as an imperative instruction. Starting it creates the
  agent and opens the session.

Sessions and Agent View
- A session is one agent working on one task. States: queued (waiting for a free slot: plans limit concurrent
  sessions), pending (launching), running, paused, idle (an interactive agent waits for your next message), then
  terminal: completed (the agent answered; its outcome says whether the task succeeded), failed, timed_out (waited
  24 h in the queue), interrupted (cancelled).
- Agent View shows every session live or as a replay: the agent's screen, each step it took (what it saw, what it
  did and why) and its final answer. Credits are consumed while sessions run.
- Steer a running agent: send a message (adds context or redirects it; picked up on the next step, also wakes an
  idle session and resumes a paused one); pause / resume (state preserved); cancel (ends it: interrupted).
- A message to a finished session restarts it and is billed again.
- Cloud session: H provisions a fresh browser on its servers for each session (nothing runs on the user's
  machine; the tab can be closed and the session found again under Sessions). It starts with no cookies: a
  browser profile (saved cookies and storage) makes it start signed in, a vault lets the agent fill a login
  mid-session. Sign-in, proxies and viewport size are cloud-browser options; "your browser" uses your Chrome.

Other sections
- Sessions list: every past session with status, agent and cost; open one to replay it in Agent View.
- API keys: create a key for the SDK / holo CLI (HAI_API_KEY); its value is shown once: copy it to a safe place;
  never read it aloud or leave it on screen.
- Billing / usage: credits, plan and usage; the plan sets the concurrent-session limit (Free: 3).
- Schedules run a session request on a cron; vaults hold credentials (and 2FA) an agent may fill into login forms.

Site map and how to get back (left sidebar and top bar read on the live platform, 2026-11-08)
- Sidebar, top to bottom: Home; Projects; under "Build": Agents (with a "+" New agent, shortcut ⌘B), Sessions (with
  a "+" New session, shortcut ⌘I), Skills, Environments, Browser Profiles, Vaults, Schedules; under "Configure":
  Organisation, API keys, Webhooks. At the bottom: the plan (e.g. "Free plan", % of credits used, days left,
  Upgrade) and the account menu. Collapse sidebar hides it (expand it again to see these entries).
- Top bar: breadcrumb (Organisation, Project, then Agents / Sessions), Notifications on the right. Help and
  feedback (bottom right): documentation, Discord, contact support, send feedback.
- Build an agent wizard: opened by Build (⌘B) on the Agents page or by New agent (⌘B) in the sidebar; Close or
  Escape leaves it, then reopen it the same way (what was typed may have to be entered again). Back / Next move
  between its six steps; the stepper at the top shows where you are.
- A session's page (Agent View): Sessions in the sidebar lists every session; click one to open it.
- To come back to the task from anywhere: use the sidebar entry of the section the task lives in (Agents for
  building an agent, Sessions for a session), then the button that reopens the task (Build ⌘B, a session row).
