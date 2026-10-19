#!/usr/bin/env python3
"""Reproduce the real extract -> portable playable demo -> browser evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.demo import generate
from tests.independent import decode


def run(args, env, output=None):
    result = subprocess.run(args,cwd=ROOT,env=env,check=True,capture_output=True,text=True)
    if output:
        output.write_text(result.stdout+result.stderr)
    print(result.stdout.strip(), flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,default=Path('/tmp/forge-playable-results'))
    args=parser.parse_args()
    results=args.results.resolve();results.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ)
    if 'PLAYWRIGHT_BROWSERS_PATH' not in env and Path('/tmp/street-forge-browsers').exists():
        env['PLAYWRIGHT_BROWSERS_PATH']='/tmp/street-forge-browsers'
    run(['node','scripts/player_check.cjs'],env,results/'collision-tests.txt')
    run([sys.executable,'-m','unittest','tests.test_provenance','-v'],env,results/'provenance-tests.txt')
    with tempfile.TemporaryDirectory(prefix='forge-playable-verify-') as temp:
        scene=Path(temp)/'scene'
        manifest=generate(scene)
        assert manifest['totals']['features']==146
        assert sum(f['kind']=='building' for f in manifest['features'])==12
        source=scene/'source.osm'
        assert hashlib.sha256(source.read_bytes()).hexdigest()==manifest['source']['sha256']
        assert json.loads((scene/'source.provenance.json').read_text())==manifest['source']
        assert {p.name for p in scene.iterdir()}=={p.name for p in (ROOT/'demo/berlin').iterdir()}
        for file in scene.iterdir():
            assert file.read_bytes()==(ROOT/'demo/berlin'/file.name).read_bytes(), f'stale packaged demo: {file.name}'
        run(['node','scripts/validate_glb.cjs',str(scene/'scene.glb'),str(results/'validator.json')],env)
        run(['node','scripts/playable_browser_check.cjs',str(scene),str(results)],env)
        # Independent GEOS distance check over decoded GLB bottom caps. It does
        # not call the JavaScript collision implementation or trust hit counters.
        from shapely.geometry import Polygon, Point
        from shapely.ops import unary_union
        doc, meshes=decode((scene/'scene.glb').read_bytes())
        polygons=[]
        for feature, mesh in zip(manifest['features'],meshes):
            if feature['kind']!='building':
                continue
            vertices, triangles, _normals=mesh
            for triangle in triangles:
                points=[vertices[i] for i in triangle]
                if all(abs(p[1])<1e-6 for p in points):
                    polygons.append(Polygon([(p[0],p[2]) for p in points]))
        solid=unary_union(polygons)
        trace=json.loads((results/'trajectory.json').read_text())
        assert len(trace)>100
        clearance=min(Point(p).distance(solid) for p in trace)
        assert clearance>=.45-1e-6, clearance
        report=json.loads((results/'browser.json').read_text())
        assert Point(report['collisionTarget']['point']).distance(solid)<1e-7
        assert .45-1e-6<=Point(report['collision']['position']).distance(solid)<.8
        evidence={'source_sha256':manifest['source']['sha256'],'features':146,'buildings':12,
                  'triangles':manifest['totals']['triangles'],'packaged_demo_byte_identical':True,
                  'sampled_player_positions':len(trace),'minimum_building_clearance_m':clearance}
        (results/'geometry.json').write_text(json.dumps(evidence,indent=2)+'\n')
    # Exercise the actual one-command launcher and its loopback HTTP response.
    process=subprocess.Popen([sys.executable,'scripts/demo.py','--no-browser'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        line=process.stdout.readline()
        match=re.search(r'http://127\.0\.0\.1:\d+/index.html\?walk=1',line)
        assert match,line
        with urlopen(match[0],timeout=10) as response:
            assert response.status==200
            assert b'Walk neighborhood' in response.read()
        base=match[0].split('/index.html')[0]
        with urlopen(base+'/source.provenance.json',timeout=10) as response:
            assert json.load(response)['sha256']==manifest['source']['sha256']
        evidence['one_command_loopback_launch']=True
        (results/'geometry.json').write_text(json.dumps(evidence,indent=2)+'\n')
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill();process.wait()
    print('PASS: real snapshot, packaged demo, GLB, keyboard route/collision, independent clearance, loopback launch')

if __name__=='__main__':
    main()
