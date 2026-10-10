#!/usr/bin/env python3
"""Regenerate the labeled synthetic fixture; no network or real-map coordinates."""
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring, indent

root = Element('osm', version='0.6', generator='street-scene-forge synthetic fixture')
SubElement(root, 'note').text = 'SYNTHETIC DATA. Invented geometry near 0,0. CC0-1.0.'
points = {}

def way(ident, coords, tags, closed=False):
    refs = []
    for x, y in coords:
        point = (x, y)
        if point not in points:
            nid = str(len(points)+1)
            points[point] = nid
            SubElement(root, 'node', id=nid, lon=f'{x / 111195.0802335329:.10f}', lat=f'{y / 111195.0802335329:.10f}')
        refs.append(points[point])
    if closed:
        refs.append(refs[0])
    w = SubElement(root, 'way', id=str(ident))
    for ref in refs:
        SubElement(w, 'nd', ref=ref)
    for k, v in tags.items():
        SubElement(w, 'tag', k=k, v=v)
    return w

way(101, [(-55, -20), (-20, -20), (-20, 15), (-35, 15), (-35, -5), (-55, -5)], {'building':'yes', 'name':'Corner workshop', 'height':'12 m'}, True)
way(102, [(5, -20), (35, -20), (35, 5), (5, 5)], {'building':'apartments', 'name':'Sample apartments', 'building:levels':'5'}, True)
way(103, [(5, 30), (20, 30), (20, 45), (5, 45)], {'building':'yes', 'name':'</script><img src=https://invalid.example/x onerror="window.HOSTILE=1"> & "quoted"', '__proto__':'inert source tag'}, True)
way(201, [(-75, 20), (0, 20), (75, 20)], {'highway':'residential', 'name':'Invented street'})
way(202, [(45, -55), (45, 55)], {'highway':'footway', 'width':'0.4', 'name':'Narrow path'})
way(301, [(-65, 40), (-50, 55), (-65, 55), (-50, 40)], {'building':'yes'}, True)
w = way(302, [], {'building':'yes'})
for ref in ['99998','99999','99997','99998']:
    SubElement(w, 'nd', ref=ref)
way(303, [(-30, -50), (-10, -50)], {'highway':'service', 'bridge':'yes'})
way(304, [(90, -50), (120, -50), (120, -30), (90, -30)], {'building':'yes'}, True)
way(305, [(-60, -60), (-40, -60), (-40, -40)], {'building':'yes'})
r = SubElement(root, 'relation', id='401')
SubElement(r, 'tag', k='type', v='multipolygon')
SubElement(r, 'tag', k='building', v='yes')
indent(root)
Path(__file__).resolve().parents[1].joinpath('fixtures/synthetic.osm').write_bytes(tostring(root, encoding='utf-8', xml_declaration=True)+b'\n')
