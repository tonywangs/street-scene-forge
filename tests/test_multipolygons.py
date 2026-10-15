import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from street_scene_forge.core import build, convert, Limits, ForgeError
from tests.independent import check, decode, normal, volume
from tests.multipolygon_cases import relation_xml, generated, demo, BBOX, SCALE

# Mandatory independent oracle: never silently skip these checks.
from shapely.geometry import Polygon, Point
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]


def expected_geometry(rings):
    outers = [Polygon(p) for role,p in rings if role == 'outer']
    holes = [Polygon(p) for role,p in rings if role == 'inner']
    return unary_union(outers).difference(unary_union(holes))


def oracle(glb, manifest, expected):
    check(glb, manifest)
    assert expected.is_valid
    assert len(manifest['features']) == 1, manifest['diagnostics']
    feature = manifest['features'][0]
    assert feature['id'] == 'relation/900'
    assert feature['dimensions']['height_m'] == 7
    vertices, triangles, _ = decode(glb)[1][0]
    roofs = []
    for tri in triangles:
        p = [vertices[i] for i in tri]
        if all(v[1] == 7 for v in p):
            roofs.append(Polygon([(v[0],v[2]) for v in p]))
        elif len({v[1] for v in p}) > 1:
            n = normal(*p)
            length = math.hypot(n[0],n[2])
            center = [sum(v[j] for v in p)/3 for j in (0,2)]
            outward = Point(center[0]+.002*n[0]/length, center[1]+.002*n[2]/length)
            inward = Point(center[0]-.002*n[0]/length, center[1]-.002*n[2]/length)
            assert not expected.contains(outward) and expected.contains(inward), 'wall winding'
    union = unary_union(roofs)
    assert union.symmetric_difference(expected).area < max(.01,expected.area*2e-6)
    assert abs(sum(p.area for p in roofs)-union.area) < .001, 'roof overlap'
    assert math.isclose(volume(vertices,triangles), expected.area*7, rel_tol=2e-5)
    assert math.isclose(feature['dimensions']['footprint_area_m2'],expected.area,rel_tol=1e-10)


class Multipolygons(unittest.TestCase):
    def test_250_seeded_geos_oracle(self):
        for case in range(250):
            with self.subTest(case=case):
                rings = generated(case)
                raw = relation_xml(rings,case,fragmented=case%2==0)
                glb,m = build(raw,BBOX)
                oracle(glb,m,expected_geometry(rings))
                self.assertEqual(build(raw,BBOX)[0],glb)
                reordered = relation_xml(rings,case+1001,fragmented=case%2==0)
                self.assertEqual(build(reordered,BBOX)[0],glb)
                self.assertEqual(len(m['features'][0]['source_members']),m['omission_counts']['consumed_relation_member'])
                self.assertEqual(m['input']['sha256'],hashlib.sha256(raw).hexdigest())

    def test_64_seeded_invalid_relations(self):
        import random
        rng=random.Random(139717)
        for case in range(64):
            x,z=rng.uniform(-300,300),rng.uniform(-300,300)
            w,h=rng.uniform(10,80),rng.uniform(10,80)
            if case%2:
                points=[(x,z),(x+w,z+h),(x,z+h),(x+w,z)]
                self.assertFalse(Polygon(points).is_valid)
                rings=[('outer',points)];reason='self_intersection'
            else:
                outer=[(x,z),(x+w,z),(x+w,z+h),(x,z+h)]
                hole=[(x+w*.8,z+h*.2),(x+w*1.2,z+h*.2),(x+w*1.2,z+h*.7),(x+w*.8,z+h*.7)]
                self.assertFalse(Polygon(outer,[hole]).is_valid)
                rings=[('outer',outer),('inner',hole)];reason='touching_or_intersecting_rings'
            glb,m=build(relation_xml(rings,case),BBOX)
            self.assertEqual(m['totals']['features'],0)
            self.assertIn(reason,m['omission_counts'])
            check(glb,m)

    def test_32_exact_boundaries_and_crossings(self):
        for case in range(32):
            raw=relation_xml(generated(case),case)
            nodes=ET.fromstring(raw).findall('node')
            lon=[float(n.get('lon')) for n in nodes]; lat=[float(n.get('lat')) for n in nodes]
            bbox=(min(lon),min(lat),max(lon),max(lat))
            glb,m=build(raw,bbox)
            self.assertEqual(m['totals']['features'],1)
            check(glb,m)
            m=build(raw,(bbox[0],bbox[1],bbox[2]-1e-10,bbox[3]))[1]
            self.assertIn({'id':'relation/900','reason':'outside_extent'},m['diagnostics'])
            self.assertEqual(m['totals']['features'],0)

    def test_many_vertices_hashing_branch(self):
        rings=[('outer',[(100*math.cos(i*math.tau/100),100*math.sin(i*math.tau/100)) for i in range(100)]),
               ('inner',[(10*math.cos(i*math.tau/20),10*math.sin(i*math.tau/20)) for i in range(20)])]
        raw=relation_xml(rings,fragmented=False)
        oracle(*build(raw,BBOX),expected_geometry(rings))

    def test_invalid_geometry_and_members(self):
        outer=[(0,0),(20,0),(20,20),(0,20)]
        cases=[([('outer',outer),('inner',[(0,2),(4,2),(4,4),(0,4)])],'touching_or_intersecting_rings'),
               ([('outer',outer),('inner',[(18,2),(24,2),(24,4),(18,4)])],'touching_or_intersecting_rings'),
               ([('outer',outer),('outer',outer)],'touching_or_intersecting_rings'),
               ([('outer',outer),('outer',[(2,2),(8,2),(8,8),(2,8)])],'nested_rings_unsupported'),
               ([('outer',outer),('inner',[(2,2),(8,2),(8,8),(2,8)]),('inner',[(3,3),(4,3),(4,4),(3,4)])],'nested_rings_unsupported'),
               ([('inner',outer)],'missing_outer_ring'),
               ([('outer',outer),('inner',[(25,2),(28,2),(28,8),(25,8)])],'inner_not_contained'),
               ([('outer',[(0,0),(20,20),(0,20),(20,0)])],'self_intersection')]
        for rings,reason in cases:
            m=build(relation_xml(rings),BBOX)[1]
            self.assertIn({'id':'relation/900','reason':reason},m['diagnostics'])
            self.assertEqual(m['totals']['features'],0)
        raw=relation_xml([('outer',outer)])
        mutations=[(b'role="outer"',b'role=""','unsupported_member_role'),
                   (b'type="way"',b'type="relation"','unsupported_relation_member_type'),
                   (b'<nd ref="1"',b'<nd ref="999"','missing_node_reference')]
        for a,b,reason in mutations:
            self.assertIn({'id':'relation/900','reason':reason},build(raw.replace(a,b),BBOX)[1]['diagnostics'])
        for mutation,reason in [('missing','missing_way_reference'),('duplicate','duplicate_relation_member'),('open','ambiguous_or_unclosed_ring'),('branch','ambiguous_or_unclosed_ring'),('nested','nested_relation_unsupported'),('shared','shared_relation_member')]:
            root=ET.fromstring(raw); rel=root.find('relation')
            if mutation=='missing': root.remove(root.find('way'))
            if mutation=='duplicate': rel.append(ET.fromstring(ET.tostring(rel.find('member'))))
            if mutation=='open': rel.remove(rel.find('member'))
            if mutation=='branch':
                w=ET.SubElement(root,'way',id='99');ET.SubElement(w,'nd',ref='1');ET.SubElement(w,'nd',ref='3')
                ET.SubElement(rel,'member',type='way',ref='99',role='outer')
            if mutation=='nested':
                parent=ET.SubElement(root,'relation',id='901');ET.SubElement(parent,'member',type='relation',ref='900',role='outer')
            if mutation=='shared':
                other=ET.fromstring(ET.tostring(rel));other.set('id','901');root.append(other)
            m=build(ET.tostring(root),BBOX)[1]
            self.assertIn({'id':'relation/900','reason':reason},m['diagnostics'])
            self.assertEqual(m['totals']['features'],0)

    def test_provenance_and_hard_limits(self):
        vendor=ROOT/'street_scene_forge/vendor'
        meta=json.loads((vendor/'provenance.json').read_text())
        self.assertEqual(hashlib.sha256((vendor/'earcut.py').read_bytes()).hexdigest(),meta['vendored_sha256'])
        self.assertEqual(hashlib.sha256((vendor/'LICENSE.earcut').read_bytes()).hexdigest(),meta['license_sha256'])
        rings=[('outer',[(i*5,0),(i*5+2,0),(i*5+2,2),(i*5,2)]) for i in range(33)]
        self.assertIn('relation_geometry_limit',build(relation_xml(rings,fragmented=False),BBOX)[1]['omission_counts'])
        root=ET.fromstring(demo());rel=root.find('relation')
        for _ in range(1001):ET.SubElement(rel,'member',type='way',ref='1',role='outer')
        with self.assertRaisesRegex(ForgeError,'relation_member_limit'):build(ET.tostring(root),BBOX)
        root=ET.fromstring(demo());root.find('relation/member').attrib.pop('ref')
        with self.assertRaisesRegex(ForgeError,'invalid_osm_id'):build(ET.tostring(root),BBOX)
        m=build(demo(),BBOX)[1]
        self.assertEqual(m['schema_version'],2)
        self.assertEqual([r['id'] for r in m['source_relations']],['relation/900','relation/901'])
        self.assertEqual(len(m['source_relations'][0]['members']),8)

    def test_limits_tags_and_lifecycle(self):
        raw=demo()
        self.assertIn({'id':'relation/900','reason':'relation_geometry_limit'},build(raw,BBOX,Limits(relation_refs=3))[1]['diagnostics'])
        with self.assertRaisesRegex(ForgeError,'mesh_resource_limit'):build(raw,BBOX,Limits(vertices=2))
        with self.assertRaisesRegex(ForgeError,'runtime_limit'):build(raw,BBOX,Limits(seconds=-1))
        self.assertEqual(build(raw.replace(b'v="7"',b'v="bad"'),BBOX)[1]['totals']['features'],0)
        for key,value,expected in [('height','12',12),('building:levels','4',12)]:
            root=ET.fromstring(raw);rel=root.find('relation');rel.remove(rel.find("tag[@k='height']"))
            ET.SubElement(rel,'tag',k=key,v=value)
            self.assertEqual(build(ET.tostring(root),BBOX)[1]['features'][0]['dimensions']['height_m'],expected)
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'input.osm';source.write_bytes(raw);out=Path(tmp)/'scene'
            with patch('street_scene_forge.core.json_bytes',side_effect=ValueError('serialization')):
                with self.assertRaises(ValueError):convert(source,out,BBOX)
            self.assertFalse(out.exists())
            with patch('street_scene_forge.core.Path.open',side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):convert(source,out,BBOX)
            self.assertFalse(out.exists());self.assertEqual(source.read_bytes(),raw)
            convert(source,out,BBOX)
            with self.assertRaisesRegex(ForgeError,'output_exists'):convert(source,out,BBOX)

    def test_upstream_corpus(self):
        from tests.upstream_cases import corpus
        for item,raw,bbox in corpus():
            with self.subTest(name=item['file']):
                glb,m=build(raw,bbox)
                self.assertEqual(m['totals']['features'],item['expected_features'])
                if item.get('expected_reason'):
                    self.assertIn(item['expected_reason'],m['omission_counts'])
                check(glb,m)
                if item['expected_features']:
                    f=m['features'][0]
                    self.assertEqual(len(f['rings']),item['expected_rings'])
                    self.assertAlmostEqual(f['dimensions']['footprint_area_m2'],item['expected_area_m2'],places=6)


from tests.test_forge import LifecycleTests as _LifecycleTests


class RelationLifecycle(_LifecycleTests):
    """Run the established failure/signal matrix against courtyard conversion."""
    def setUp(self):
        super().setUp()
        self.input.write_bytes(demo())

    # Parent checks deliberately compare against its own square fixture.
    def test_write_failure_and_keyboard_interrupt_cleanup(self):
        original=Path.open
        for exception in [OSError('injected disk failure'),KeyboardInterrupt()]:
            def fail(path,*args,**kwargs):
                if path.name=='data.js':raise exception
                return original(path,*args,**kwargs)
            with patch.object(Path,'open',fail):
                with self.assertRaises(type(exception)):convert(self.input,self.output,BBOX)
            self.assertFalse(self.output.exists())
            self.assertEqual(self.input.read_bytes(),demo())


del _LifecycleTests
