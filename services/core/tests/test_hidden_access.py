"""3.18: product source must never access the simulator's answer key."""

import os
import re
from pathlib import Path


def test_services_and_workflows_do_not_read_hidden_ground_truth():
    root = Path(__file__).resolve().parents[3]
    source_extensions = {".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".json", ".sql", ".sh", ".yaml", ".yml"}
    excluded = {".venv", "venv", "node_modules", "dist", "build", "__pycache__", ".git", "tests", "e2e", "runtime", ".pytest_cache"}
    violations = []
    for area in ("services", "n8n"):
        for directory, folders, files in os.walk(root / area):
            folders[:] = [folder for folder in folders if folder not in excluded]
            for name in files:
                path = Path(directory) / name
                if path.suffix not in source_extensions or name.endswith("lock.json"):
                    continue
                source = path.read_text(encoding="utf-8")
                # Both literal paths and Python path joins (base / "hidden" / filename).
                forbidden = re.search(r"\bhidden[/\\]", source)
                if path.suffix == ".py":
                    forbidden = forbidden or re.search(r"['\"]hidden['\"]", source)
                if forbidden:
                    violations.append(str(path.relative_to(root)))
    assert not violations, f"Product source references hidden ground truth: {violations}"
