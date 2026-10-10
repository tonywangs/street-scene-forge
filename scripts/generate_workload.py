#!/usr/bin/env python3
"""Generate a deterministic, clearly synthetic bounded 1,000-building workload."""
import argparse
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring


def generate():
    root = Element('osm', version='0.6', generator='street-scene-forge SYNTHETIC workload')
    SubElement(root,'note').text = 'SYNTHETIC BENCHMARK. Invented 40 by 25 grid. CC0-1.0.'
    scale = 111195.0802335329
    nid = 0
    for i in range(1000):
        x,z = (i%40-20)*25,(i//40-12)*25
        refs=[]
        for dx,dz in [(0,0),(12,0),(12,12),(0,12)]:
            nid+=1
            refs.append(str(nid))
            SubElement(root,'node',id=str(nid),lon=str((x+dx)/scale),lat=str(-(z+dz)/scale))
        way=SubElement(root,'way',id=str(i+1))
        for ref in refs+refs[:1]:SubElement(way,'nd',ref=ref)
        SubElement(way,'tag',k='building',v='yes')
        SubElement(way,'tag',k='height',v=str(3+(i%17)*3))
    return tostring(root,encoding='utf-8',xml_declaration=True)+b'\n'


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    with args.output.open('xb') as handle:handle.write(generate())
