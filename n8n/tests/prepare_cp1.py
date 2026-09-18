"""Start the pulled core with a visible-only demo mount and replay up to CP1.

No reset or source-file edits; uses A's migrations and idempotent replay command.
"""
from pathlib import Path
import json
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    visible = ROOT / 'data/demo/visible'
    if not (visible / 'transactions.csv').is_file():
        raise SystemExit('Generate the visible demo first: python tasks.py generate --only demo')
    override = {'services': {'core': {'environment': {'HISAAB_DATA_DIR': '/data'},
        'volumes': [{'type': 'bind', 'source': str(visible), 'target': '/data/demo/visible', 'read_only': True}]}}}
    with tempfile.TemporaryDirectory(prefix='hisaab-cp1-') as folder:
        filename = Path(folder, 'compose.json')
        filename.write_text(json.dumps(override), encoding='utf-8')
        command = ['docker', 'compose', '-f', str(ROOT / 'docker-compose.yml')]
        local = ROOT / 'docker-compose.override.yml'
        if local.exists():
            command.extend(['-f', str(local)])
        command.extend(['-f', str(filename), 'up', '-d', '--no-deps', '--wait', 'core'])
        subprocess.run(command, cwd=ROOT, check=True)
    subprocess.run([sys.executable, 'tasks.py', 'replay', '--split', 'demo', '--until',
                    '2026-03-10T02:00:00+05:30'], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
