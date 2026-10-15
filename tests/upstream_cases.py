"""Frozen regression corpus and explicit building-tag adaptation; no network."""
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]/'fixtures/multipolygons'


def adapt(raw, legacy=False):
    root=ET.fromstring(raw)
    targets=root.findall('way') if legacy else root.findall('relation')
    for target in targets:
        if not legacy or target.find("tag[@k='highway']") is not None:
            ET.SubElement(target,'tag',k='building',v='yes')
            ET.SubElement(target,'tag',k='height',v='7')
    return ET.tostring(root)


def corpus():
    meta=json.loads((ROOT/'provenance.json').read_text())
    for item in meta['fixtures']:
        raw=(ROOT/item['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==item['sha256']
        yield item,adapt(raw,item['adaptation']=='legacy_outer_building'),item['bbox']
