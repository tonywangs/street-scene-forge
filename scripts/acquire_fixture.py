#!/usr/bin/env python3
"""OPTIONAL ONLINE acquisition, deliberately separate from the offline CLI.

Downloads six explicit full ways, strips contributor account metadata, and
writes a small ODbL extract plus exact response and extract hashes. Upstream
ways can change: a new acquisition is a new snapshot, not a byte replay.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

IDS = [23853131, 23853133, 234463917, 51912365, 113595955, 16873017]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', required=True, type=Path, help='new directory (not overwritten)')
args = parser.parse_args()
if args.output.exists():
    parser.error('output already exists')
elements, responses = {}, []
for ident in IDS:
    url = f'https://api.openstreetmap.org/api/0.6/way/{ident}/full'
    request = Request(url, headers={'User-Agent': 'StreetSceneForge/0.1 reproducible-small-fixture'})
    with urlopen(request, timeout=30) as handle:
        raw = handle.read(500001)
    if len(raw) > 500000:
        raise ValueError('acquisition byte cap exceeded')
    responses.append({'url': url, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
    for e in ET.fromstring(raw):
        if e.tag not in ('node', 'way'):
            continue
        e.attrib = {k: v for k, v in e.attrib.items() if k in ('id', 'version', 'timestamp', 'visible', 'lat', 'lon')}
        key = e.tag, e.get('id')
        if key in elements and ET.tostring(elements[key]) != ET.tostring(e):
            raise ValueError('inconsistent repeated element; acquire again')
        elements[key] = e
root = ET.Element('osm', version='0.6', generator='street-scene-forge explicit-way snapshot')
ET.SubElement(root, 'note').text = 'REAL OpenStreetMap data. © OpenStreetMap contributors. ODbL 1.0. Six selected ways, not a complete area extract.'
for key in sorted(elements, key=lambda k: (k[0], int(k[1]))):
    root.append(elements[key])
ET.indent(root)
raw = ET.tostring(root, encoding='utf-8', xml_declaration=True)+b'\n'
coords = [(float(e.get('lon')), float(e.get('lat'))) for e in elements.values() if e.tag == 'node']
bbox = [min(p[0] for p in coords)-.00015, min(p[1] for p in coords)-.00015,
        max(p[0] for p in coords)+.00015, max(p[1] for p in coords)+.00015]
meta = {'fixture': 'berlin-six-ways.osm', 'kind': 'real OSM snapshot; selected ways only',
        'acquired_utc': datetime.now(timezone.utc).isoformat(), 'way_ids': IDS,
        'responses': responses, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'bbox': bbox,
        'attribution': '© OpenStreetMap contributors', 'license': 'ODbL-1.0',
        'license_url': 'https://opendatacommons.org/licenses/odbl/1-0/',
        'copyright_url': 'https://www.openstreetmap.org/copyright',
        'transformation': 'Union of six /way/{id}/full responses. Removed user, uid and changeset attributes; retained IDs, versions, timestamps, coordinates, references and tags. No geometry changes.'}
args.output.mkdir()
(args.output/'berlin-six-ways.osm').write_bytes(raw)
(args.output/'berlin-six-ways.provenance.json').write_text(json.dumps(meta, indent=2)+'\n')
print(json.dumps({'bytes': len(raw), 'bbox': bbox, 'sha256': meta['sha256']}))
