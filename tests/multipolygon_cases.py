"""Synthetic inputs in metres, independent of production ring assembly."""
import math
import random
from xml.etree import ElementTree as ET

SCALE = 111195.0802335329
BBOX = (-.01, -.01, .01, .01)


def relation_xml(rings, seed=0, fragmented=True, tags=None):
    rng = random.Random(seed)
    root = ET.Element('osm', version='0.6')
    members, node_id, way_id = [], 0, 0
    for role, points in rings:
        refs = []
        for x, z in points:
            node_id += 1
            refs.append(str(node_id))
            ET.SubElement(root, 'node', id=str(node_id), lon=str(x/SCALE), lat=str(-z/SCALE))
        refs.append(refs[0])
        chunks = [[a,b] for a,b in zip(refs,refs[1:])] if fragmented else [refs]
        for chunk in chunks:
            way_id += 1
            if rng.randrange(2): chunk = chunk[::-1]
            way = ET.SubElement(root, 'way', id=str(way_id))
            for ref in chunk: ET.SubElement(way, 'nd', ref=ref)
            # Conflicting tags must not override relation tags or duplicate buildings.
            ET.SubElement(way, 'tag', k='building', v='yes')
            ET.SubElement(way, 'tag', k='height', v='99')
            members.append(dict(type='way', ref=str(way_id), role=role))
    rel = ET.SubElement(root, 'relation', id='900')
    rng.shuffle(members)
    for member in members: ET.SubElement(rel, 'member', **member)
    for k,v in (tags or {'type':'multipolygon','building':'yes','height':'7'}).items():
        ET.SubElement(rel, 'tag', k=k, v=v)
    return ET.tostring(root)


def generated(case):
    rng = random.Random(981723 + case)
    w,h = rng.uniform(30,90),rng.uniform(30,90)
    rings = [('outer', [(0,0),(w,0),(w,h*.55),(w*.55,h*.55),(w*.55,h),(0,h)]),
             ('inner', [(w*.1,h*.1),(w*.3,h*.1),(w*.3,h*.35),(w*.1,h*.35)])]
    if case % 2:
        rings.append(('inner',[(w*.65,h*.1),(w*.85,h*.1),(w*.85,h*.35),(w*.65,h*.35)]))
    if case % 3 == 0:
        rings.append(('outer', [(w+10,0),(w+30,0),(w+30,20),(w+10,20)]))
    theta,tx,tz = rng.uniform(-3,3),rng.uniform(-400,400),rng.uniform(-400,400)
    return [(role, [(x*math.cos(theta)-z*math.sin(theta)+tx,x*math.sin(theta)+z*math.cos(theta)+tz) for x,z in points]) for role,points in rings]


def demo():
    rings = [('outer',[(-50,-40),(50,-40),(50,40),(-50,40)]),
             ('inner',[(-30,-20),(30,-20),(30,20),(-30,20)])]
    raw = relation_xml(rings, 71, tags={'type':'multipolygon','building':'yes','height':'7',
                         'name':'Courtyard </script><img src=x onerror="window.HOSTILE=1">'})
    root = ET.fromstring(raw)
    # Unsupported source is intentionally visible in diagnostics.
    rel = ET.SubElement(root,'relation',id='901')
    ET.SubElement(rel,'tag',k='type',v='route')
    return ET.tostring(root)
