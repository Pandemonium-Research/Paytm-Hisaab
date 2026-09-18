"""Synthetic world v2 for Paytm Hisaab.

Generates a year of merchant payments from a known process, split into what Paytm would see
(`visible/`) and what really happened (`hidden/`). Product code reads `visible/` only.
Run `python -m sim.generate`; see sim/README.md.
"""

GENERATOR_VERSION = "2.0.0"
