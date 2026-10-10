#!/usr/bin/env python3
"""Install a self-contained executable zipapp, without pip or network access."""
import argparse
from pathlib import Path
import shutil
import tempfile
import zipapp

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--prefix', required=True, type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
exe = args.prefix / 'bin' / 'street-scene-forge'
exe.parent.mkdir(parents=True, exist_ok=True)
if exe.exists():
    parser.error('refusing to overwrite existing executable')
with tempfile.TemporaryDirectory() as temp:
    shutil.copytree(root / 'street_scene_forge', Path(temp) / 'street_scene_forge', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    (Path(temp) / '__main__.py').write_text('from street_scene_forge.__main__ import main\nraise SystemExit(main())\n')
    zipapp.create_archive(temp, exe, interpreter='/usr/bin/env python3')
exe.chmod(0o755)
print(exe)
