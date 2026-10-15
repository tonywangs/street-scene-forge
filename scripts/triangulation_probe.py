#!/usr/bin/env python3
"""Reproduce the aligned-courtyard negative result before cap repair."""
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.multipolygon_cases import generated, relation_xml, BBOX
from street_scene_forge.core import Budget, Limits, read_osm, extent, build
from street_scene_forge.geometry import EPS, cross
from street_scene_forge.relations import assemble, conform_cap
from street_scene_forge.vendor.earcut import earcut


def probe():
    raw=relation_xml(generated(3),3,fragmented=False)
    budget=Budget(Limits())
    nodes,ways,relations,*_=read_osm(raw,budget)
    project,_=extent(BBOX,Limits())
    rings=assemble(relations['900'],ways,nodes,project,BBOX,budget)
    outer=next(r for r in rings if r['role']=='outer')
    loops=[outer['points']]+[r['points'][::-1] for r in rings if r.get('outer_index')==0]
    points,holes=[],[]
    for loop in loops:
        if points:holes.append(len(points))
        points.extend(loop)
    indices=earcut([x for p in points for x in p],holes,2)
    cap=[tuple(indices[i:i+3]) for i in range(0,len(indices),3)]
    repaired=conform_cap(points,cap,budget)
    bad=lambda tris:sum(abs(cross(*(points[i] for i in t)))<=EPS for t in tris)
    result={'case':3,'seed':981726,'input_sha256':hashlib.sha256(raw).hexdigest(),
            'raw_triangles':len(cap),'raw_degenerate_triangles':bad(cap),
            'repaired_triangles':len(repaired),'repaired_degenerate_triangles':bad(repaired),
            'exported_features':build(raw,BBOX)[1]['totals']['features'],
            'interpretation':'Earcut output alone is insufficient for a closed solid; remove zero-area bridge faces and repair T-junctions, then enforce area and directed-edge topology.'}
    assert result['raw_degenerate_triangles']>0
    assert result['repaired_degenerate_triangles']==0 and result['exported_features']==1
    return result


if __name__=='__main__':print(json.dumps(probe(),indent=2,sort_keys=True))
