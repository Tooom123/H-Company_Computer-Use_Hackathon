# Demo checklist

Before the demo (from PRD "Démonstration et critères de réussite"):

- [ ] Test environment chosen and reachable from the Mac (Odoo test database with demo data flagged as such)
- [ ] Reproducible initial state + reset script in `scripts/`
- [ ] Success case passes 3 times in a row from that state (log in `docs/test-log.md`)
- [ ] Blocked case produces an escalation with no false success claim
- [ ] At least 3 recorded cases for grouping: two similar, one different
- [ ] Stop button tested during a real run, latency recorded
- [ ] macOS permissions granted to the app that launches the agent; preflight message checked when missing
- [ ] Dashboard requires authentication; no H key inside the distributed app
- [ ] Unrelated windows, tabs and password managers closed on the demo Mac
