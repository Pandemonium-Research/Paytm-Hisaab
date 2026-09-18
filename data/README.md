# Synthetic data

Everything in this folder except this file is generated, and gitignored. Rebuild it with:

```bash
python -m sim.generate                 # all four splits, about 30 s
python -m sim.generate --only demo     # just the demo split
```

The schema, the splits, the labels and the demo answer key are documented in
[sim/README.md](../sim/README.md). Every person, business, account and case reference is
fictional.

```
data/
  <split>/            demo | dev | eval | sweep
    visible/          what Paytm would see: the only thing product code may read
    hidden/           the generator's truth: for eval/, the demo answer key and the merchant harness
    manifest.json
```

**The one rule:** product code (core, the n8n workflows, the memory service, the web app) never
opens `hidden/`. That separation is what makes every accuracy number real.

The v1 data docs and `hsn_catalog.json` from the Agent Labs build are in
[archive/agent-labs-2026-09-12/](../archive/agent-labs-2026-09-12/). Old v1 splits, if you
generated them, sit in `data/_v1/`.
