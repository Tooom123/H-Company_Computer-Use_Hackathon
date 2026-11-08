# H Company — demo coaching reference

This is navigation guidance, not the state of an account or an expected test
answer. Confirm labels and the selected resource on the current screen. Account
access is prepared by the human separately. Never read or display key values.

When consulting H documentation from H Platform, preserve the user's working tab:
open the documentation in a separate tab, then select it. In Show me, explain the
new-tab action and let the human perform it. Once in the documentation, reuse that
tab for its sections instead of opening duplicates.

Show the relevant passage, not only the page title. Prefer a visible section or
table-of-contents link. In autonomous mode, scroll in small steps and reobserve;
leave the useful heading and paragraph visible while explaining them. Do not
scroll away a passage already visible. For a general page overview only, one
small downward preview and return is allowed if the original heading can be
reliably restored. In Show me, let the human navigate; after manual scrolling,
ask them to confirm the step in H Companion before reobserving. Never invent a
target position for an offscreen passage.

## Cloud browser versus the user's computer

Choose the environment according to where the work should run. A cloud browser
provides a separate browser for the agent; a user browser or user desktop acts on
the user's machine. To avoid monopolizing the Mac, help the user find the cloud
browser configuration and distinguish it from the local options. Reading the
configuration does not launch a session.

Reference: https://hub.hcompany.ai/agents-api/browser/configuration
Overview: https://hub.hcompany.ai/agents-api/overview

## Reusing a signed-in browser

A browser profile preserves browser state for later sessions. A login to H
Platform in the operator's Chrome is distinct from a login inside the agent's
remote browser. To understand a profile, first identify which browser and session
the user means. Explain how the profile is associated with the environment;
do not extract cookies, create credentials or expose stored authentication data.

Reference: https://hub.hcompany.ai/agents-api/browser/profiles

## Reviewing a session

Select the session explicitly designated by the user. Read its status, the
visible sequence of steps and the final agent answer separately. A completed
session is not proof that the task's intended result is correct. Compare the
answer with the visible evidence and identify missing evidence without inventing
the cause. A tool error, a timeout, an agent-declared blocker and a human pause
are different outcomes. Do not restart or cancel a session during consultation.

Reference: https://hub.hcompany.ai/agents-api/sessions/overview

## Explaining configuration

Use the documentation search and the visible navigation to locate the exact
feature. Skills, custom tools, environments and browser profiles solve different
needs; do not treat them as interchangeable. Explain the next relevant action
and its purpose, then observe the human's action. An open menu is evidence that
the menu opened; it is not evidence that a setting was changed.

Reference: https://hub.hcompany.ai/agents-api/skills/overview
Reference: https://hub.hcompany.ai/agents-api/custom-tools
