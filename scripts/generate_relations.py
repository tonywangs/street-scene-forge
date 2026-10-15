#!/usr/bin/env python3
"""Bounded synthetic workload: 100 independent buildings with courtyards."""
import sys
from pathlib import Path
from xml.etree import ElementTree as ET


def generate():
    template=ET.fromstring((Path(__file__).resolve().parents[1]/'fixtures/courtyard.osm').read_bytes())
    root=ET.Element('osm',version='0.6')
    for index in range(100):
        for original in template:
            if original.tag=='relation' and original.get('id')=='901':continue
            element=ET.fromstring(ET.tostring(original))
            element.set('id',str(int(element.get('id'))+index*1000))
            if element.tag=='node':
                element.set('lon',str(float(element.get('lon'))+(index%10-4.5)*.001))
                element.set('lat',str(float(element.get('lat'))+(index//10-4.5)*.001))
            for child in element:
                if 'ref' in child.attrib:child.set('ref',str(int(child.get('ref'))+index*1000))
            root.append(element)
    return ET.tostring(root)


if __name__=='__main__':sys.stdout.buffer.write(generate())
