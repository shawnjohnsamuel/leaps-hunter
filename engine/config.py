"""Loads the v7 §20 machine-readable config — ADR 0010: this file (or its
production copy) is the single source of every threshold. Add a new
threshold here, never as a literal in another engine module.

config.example.yaml is a byte-identical extraction of §20 from
framework/v7.md — it exists for tests and as a template, and is not edited
by hand; if §20 changes, re-extract it. The deployed file (state/config.yaml
in the private data repo, added in Phase 4) is a copy of this template plus
one addition: portfolio.account_ref, naming which Robinhood account to
query. NAV itself stays out of every config file — it is read live each run
and never written to disk in either repo (ADR 0013), so portfolio.nav here
is permanently null, exactly as §20's own template has it.
"""
from __future__ import annotations

from pathlib import Path

from . import yaml_lite

TEMPLATE_PATH = Path(__file__).parent / "config.example.yaml"


def load_config(path) -> dict:
    """Load a config.yaml from an explicit path. No default or inferred
    path — Phase 0 found what an inferred lookup costs (the same lesson
    behind ADR 0013's NAV-account fix): silently reading the wrong file
    produces plausible-looking numbers that are all wrong.
    """
    return yaml_lite.load(Path(path).read_text())


def get(cfg: dict, dotted_key: str, default=None):
    """Read a nested value by dotted path, e.g.
    'sizing.caps_pct_of_nav.single_issuer'."""
    node = cfg
    for part in dotted_key.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node
