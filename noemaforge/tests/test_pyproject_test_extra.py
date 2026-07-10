#!/usr/bin/env python3
from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_test_extra_declares_collection_dependencies() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    test_extra = {
        requirement.split(">", 1)[0].split("=", 1)[0].lower()
        for requirement in pyproject["project"]["optional-dependencies"]["test"]
    }
    assert {"pytest", "pyyaml", "jsonschema"} <= test_extra
