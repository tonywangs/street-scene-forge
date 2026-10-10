#!/usr/bin/env python3
"""Check the publishable working tree against this project's artifact ceilings."""
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
result=subprocess.run(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=root,check=True,capture_output=True)
names=sorted(set(result.stdout.decode().split('\0'))-{''})
files=[root/n for n in names if (root/n).exists()]
assert len(files)<=1000,f'{len(files)} files exceeds 1,000'
size=0
for p in files:
    assert not p.is_symlink(),f'unexpected symlink: {p}'
    assert p.is_file(),f'unexpected non-file: {p}'
    length=p.stat().st_size
    assert length<=10*1024*1024,f'file exceeds 10 MiB: {p}'
    assert p.suffix!='.log' or p==root/'results/tests.log',f'non-test log: {p}'
    size+=length
assert size<=32*1024*1024,f'tree exceeds 32 MiB: {size}'
print(f'PASS: {len(files)} publishable files, {size} bytes; each <=10 MiB, total <=32 MiB, no non-test logs.')
