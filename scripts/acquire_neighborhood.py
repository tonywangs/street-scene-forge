#!/usr/bin/env python3
"""Optionally acquire one small public OSM neighborhood; normal demo runs are offline."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

BBOX = [13.4030, 52.5190, 13.4075, 52.5220]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new directory')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output already exists')
    west, south, east, north = BBOX
    query = f'[out:xml][timeout:60];(node({south},{west},{north},{east});way({south},{west},{north},{east});relation["type"="multipolygon"]({south},{west},{north},{east}););(._;>>;);out meta;'
    url = 'https://overpass-api.de/api/interpreter'
    request = Request(url, data=urlencode({'data': query}).encode(), headers={'User-Agent': 'StreetSceneForge/0.3 small-offline-neighborhood-demo'})
    with urlopen(request, timeout=90) as response:
        raw = response.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError('extract exceeds 8 MiB')
    root = ET.fromstring(raw)
    if root.tag != 'osm' or root.find('remark') is not None:
        raise ValueError('incomplete Overpass response')
    for element in root:
        for key in ('user', 'uid', 'changeset'):
            element.attrib.pop(key, None)
    ET.indent(root)
    extract = ET.tostring(root, encoding='utf-8', xml_declaration=True) + b'\n'
    meta = {'fixture': 'berlin-neighborhood.osm', 'kind': 'real bounded OSM neighborhood snapshot',
            'acquired_utc': datetime.now(timezone.utc).isoformat(), 'url': url, 'query': query,
            'response_sha256': hashlib.sha256(raw).hexdigest(), 'sha256': hashlib.sha256(extract).hexdigest(),
            'bytes': len(extract), 'bbox': BBOX, 'attribution': '© OpenStreetMap contributors',
            'license': 'ODbL-1.0', 'license_url': 'https://opendatacommons.org/licenses/odbl/1-0/',
            'copyright_url': 'https://www.openstreetmap.org/copyright',
            'transformation': 'Removed user, uid, changeset attributes; reformatted XML. Geometry, IDs, timestamps and tags retained. Recursive dependencies may extend beyond bbox; converter omits whole features outside bbox.'}
    args.output.mkdir()
    (args.output / meta['fixture']).write_bytes(extract)
    (args.output / 'berlin-neighborhood.provenance.json').write_text(json.dumps(meta, indent=2)+'\n')
    print(json.dumps(meta, indent=2))

if __name__ == '__main__':
    main()
