# Source publication checks

Before making the repository public or redistributing a source archive:

- [ ] Confirm copyright and third-party attribution for adapted Agent/MCP files, the original reference excerpts, and assets.
- [ ] Choose a license and include any required third-party notices. No license is assumed by default.
- [ ] Check dependency-license requirements for FastMCP, LangChain, DeepAgents, httpx and other imported libraries.
- [ ] Manually inspect the full Git history, configs, YAML, assets and source for sensitive values, private supplier details and credentials.
- [ ] Run `python -B -m unittest discover -s tests -v` and `python -B scripts/audit_release.py`.
- [ ] Verify claims against the exact code and run logs. Do not present deterministic model tests as production LLM performance or local mock writes as Java ERP writes.
- [ ] Check repository visibility and branch history before any public release.

`scripts/prepublish.py` reports outstanding automated and manual gates; it cannot approve legal or privacy matters automatically. This checklist is for source distribution, not for running the local application or using a private Git repository.
