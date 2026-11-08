# Autonomous iteration log — night of 2026-11-08 (branch `matteo`)

Goal: make the H Company experience reliable without supervision. Constraints: no action on the user's screen,
no sound, no H session that acts; only tree reads, text model calls, mock runs. One entry per iteration.

| # | When | What | Result |
| --- | --- | --- | --- |
| 1 | 02:5x | Routing eval set (40 FR/EN utterances) + `scripts/eval_routing.py` | first pass 26/30 correct before API rate-limit (429); 4 misroutes identified |
| 2 | 04:57 | Routing fixes: where-questions (FR/EN) always point; fact/capability/price questions always answered from docs; action sentences always tasks; new read-only procedure `hcompany_platform_check_credits`; eval script paces calls (429) | **40/40 = 100%** on the eval set (85 s) |
| 3 | 05:00 | `scripts/eval_grounding.py`: snapshot the Chrome page (labels only) and check a procedure's descriptions offline; matcher fix: labels must match as whole words, partial matches are weak hints | the H platform was not open (Chrome on another site), so H descriptions are not yet validated; harness ready for one `--snapshot` on the platform |
