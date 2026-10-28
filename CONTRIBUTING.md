# Contributing

Run the local checks before submitting a change:

```bash
python -B -m unittest discover -s tests -v
python -B scripts/audit_release.py
```

The web app uses only the Python standard library. MCP, DeepAgents and HITL integration checks additionally require their Python dependencies and local synthetic services. Do not connect tests to a production ERP or include real procurement records, private keys, tokens, database exports or `.env` files.

This repository does not currently declare an open-source license. Before redistributing code or accepting external contributions, agree on distribution terms and review third-party provenance. See [docs/PROVENANCE.md](docs/PROVENANCE.md).
