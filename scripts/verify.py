#!/usr/bin/env python3
"""One offline verification command, after optional tool setup documented in README."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.independent import check
from scripts.generate_workload import generate


def sha(raw):return hashlib.sha256(raw).hexdigest()


def run(argv,**kwargs):
    result=subprocess.run(list(map(str,argv)),text=True,capture_output=True,**kwargs)
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}): {argv}\n{result.stdout}\n{result.stderr}')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,default=ROOT/'results/multipolygons')
    args=parser.parse_args()
    results=args.results.resolve()
    results.mkdir(parents=True,exist_ok=True)
    if not (ROOT/'node_modules/gltf-validator').is_dir() or not (ROOT/'node_modules/playwright').is_dir():
        parser.error('validation dependencies missing; run npm ci --ignore-scripts first (see README)')
    env=os.environ.copy()
    # The documented explicit cache is also convenient in restricted containers.
    if 'PLAYWRIGHT_BROWSERS_PATH' not in env and Path('/tmp/street-forge-browsers').is_dir():
        env['PLAYWRIGHT_BROWSERS_PATH']='/tmp/street-forge-browsers'
    import shapely, numpy
    assert shapely.__version__ == '2.1.2' and numpy.__version__ == '2.2.6', 'install requirements-verification.txt'
    tests=subprocess.run([sys.executable,'-m','unittest','discover','-v'],cwd=ROOT,text=True,capture_output=True,env=env)
    (results/'tests.txt').write_text(tests.stdout+tests.stderr)
    if tests.returncode:
        raise RuntimeError('Unit/seeded checks failed; see results/tests.txt')
    meta=json.loads((ROOT/'fixtures/berlin-six-ways.provenance.json').read_text())
    assert sha((ROOT/'fixtures/berlin-six-ways.osm').read_bytes())==meta['sha256']
    report={'schema_version':1,'python':platform.python_version(),'node':run(['node','--version']).stdout.strip(),
            'independent_geometry':{'shapely':shapely.__version__,'geos':shapely.geos_version_string,'numpy':numpy.__version__},
            'platform':platform.platform(),'method':'Installed zipapp, isolated working directory, Python socket operations denied by tested audit hook. Browser offline=true plus aborting external HTTP/WebSocket requests. No acquisition in verification.',
            'seeds':{'valid_geometry':20261010,'invalid_geometry':71023,'boundary':88173,'multipolygon':981723,'invalid_relation':139717},
            'seeded_cases':{'valid_building_and_road':240,'invalid_intersection_and_missing_reference':80,'boundary':64,'multipolygon_geos':250,'multipolygon_boundary':32,'invalid_relation':64},
            'triangulator':json.loads((ROOT/'street_scene_forge/vendor/provenance.json').read_text()),
            'fixture_corpus_sha256':sha((ROOT/'fixtures/multipolygons/provenance.json').read_bytes()),
            'package_lock_sha256':sha((ROOT/'package-lock.json').read_bytes()),'workloads':{}}
    with tempfile.TemporaryDirectory(prefix='forge-verify-') as tmp:
        base=Path(tmp)
        run([sys.executable,ROOT/'scripts/install.py','--prefix',base/'installed'],cwd=base)
        exe=base/'installed/bin/street-scene-forge'
        report['installed_zipapp_bytes']=exe.stat().st_size
        guard=base/'guard'
        guard.mkdir()
        (guard/'sitecustomize.py').write_text('''import atexit, json, os, socket, sys
from pathlib import Path
events=[]
def guard(event,args):
 if event.startswith('socket.'):
  events.append(event)
  raise PermissionError('offline verification: sockets disabled')
sys.addaudithook(guard)
try: socket.socket()
except PermissionError: probe=True
else: raise RuntimeError('network guard did not block socket')
events.clear()
atexit.register(lambda: Path(os.environ['FORGE_AUDIT_REPORT']).write_text(json.dumps({'guard_probe_blocked':probe,'socket_attempts':events})))
''')
        cli_env=env | {'PYTHONPATH':str(guard),'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1','FORGE_AUDIT_REPORT':str(base/'audit.json')}
        workloads=[('synthetic',(ROOT/'fixtures/synthetic.osm').read_bytes(),[-.0009,-.0009,.0009,.0009]),
                   ('real',(ROOT/'fixtures/berlin-six-ways.osm').read_bytes(),meta['bbox']),
                   ('bounded',generate(),[-.006,-.006,.006,.006]),
                   ('empty',b'<osm version="0.6"/>',[-.001,-.001,.001,.001])]
        from tests.upstream_cases import corpus
        from scripts.generate_relations import generate as generate_relations
        workloads += [('courtyard',(ROOT/'fixtures/courtyard.osm').read_bytes(),[-.001,-.001,.001,.001]),
                      ('relations-bounded',generate_relations(),[-.006,-.006,.006,.006])]
        workloads += [('upstream-'+item['file'].removesuffix('.osm'),raw,bbox) for item,raw,bbox in corpus()]
        for name,raw,bbox in workloads:
            source=base/(name+'.osm')
            source.write_bytes(raw)
            out=base/name
            timing=base/'timing.txt'
            cmd=[str(exe),str(source),'--bbox',*map(str,bbox),'--output',str(out)]
            start=time.perf_counter()
            result=run(['/usr/bin/time','-f','%e %M','-o',timing,*cmd],cwd=base,env=cli_env,timeout=40)
            elapsed=time.perf_counter()-start
            time_sec,rss_kib=map(float,timing.read_text().split())
            audit=json.loads((base/'audit.json').read_text())
            assert audit=={'guard_probe_blocked':True,'socket_attempts':[]},audit
            assert sha(source.read_bytes())==sha(raw)
            repeat=base/(name+'-repeat')
            run([*cmd[:-1],repeat],cwd=base,env=cli_env,timeout=40)
            assert json.loads((base/'audit.json').read_text())==audit
            contents={p.name:p.read_bytes() for p in out.iterdir()}
            assert contents=={p.name:p.read_bytes() for p in repeat.iterdir()},'non-deterministic export'
            collision=subprocess.run(cmd,cwd=base,env=cli_env,text=True,capture_output=True,timeout=40)
            assert collision.returncode==2 and 'output_exists' in collision.stderr,collision
            assert contents=={p.name:p.read_bytes() for p in out.iterdir()},'collision changed existing output'
            manifest=json.loads(contents['manifest.json'])
            independent=check(contents['scene.glb'],manifest)
            if name in ('synthetic','real','bounded','empty'):
                baseline=json.loads((ROOT/'results/verification.json').read_text())
                assert sha(contents['scene.glb']) == baseline['workloads'][name]['artifacts']['scene.glb']['sha256'], 'historical GLB regression'
                independent['historical_glb_byte_identical']=True
            validation=run(['node',ROOT/'scripts/validate_glb.cjs',out/'scene.glb',results/(name+'-validator.json')],cwd=ROOT,env=env,timeout=30)
            browser=run(['node',ROOT/'scripts/browser_check.cjs',out,results/(name+'-browser.json'),name],cwd=ROOT,env=env,timeout=90)
            workload={'input_sha256':sha(raw),'input_bytes':len(raw),'input_unchanged':True,'byte_identical_repeated_exports':True,
                      'wall_seconds':elapsed,'gnu_time_elapsed_seconds':time_sec,'peak_process_rss_kib':int(rss_kib),
                      'totals':manifest['totals'],'omission_counts':manifest['omission_counts'],'network_audit':audit,'installed_collision_exit_code':collision.returncode,
                      'independent_readback':independent,'artifacts':{k:{'bytes':len(v),'sha256':sha(v)} for k,v in sorted(contents.items())},
                      'cli_stdout':result.stdout.strip()}
            # Temporary absolute output paths add no useful measurement evidence.
            workload.pop('cli_stdout')
            report['workloads'][name]=workload
            print(f'{name}: {manifest["totals"]["features"]} features; {elapsed:.3f}s; peak RSS {int(rss_kib)} KiB; validator + browser passed',flush=True)
    (results/'verification.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print('PASS: unit/seeded checks, isolated installed CLI, deterministic artifacts, independent GLB readback, Khronos validation, offline Chromium.')


if __name__=='__main__':main()
