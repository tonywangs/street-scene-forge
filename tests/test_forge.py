import hashlib
import json
import math
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from street_scene_forge.core import Limits, ForgeError, build, convert
from tests.independent import check, decode, normal, volume

ROOT = Path(__file__).resolve().parents[1]
BBOX = (-.01, -.01, .01, .01)
SCALE = 111195.0802335329


def xml(ways, extra=''):
    root = ET.Element('osm', version='0.6')
    counter = 0
    for ident, points, tags, closed in ways:
        refs = []
        for x,z in points:
            counter += 1
            refs.append(str(counter))
            ET.SubElement(root,'node',id=str(counter),lon=str(x/SCALE),lat=str(-z/SCALE))
        if closed and refs:
            refs.append(refs[0])
        way = ET.SubElement(root,'way',id=str(ident))
        for ref in refs:
            ET.SubElement(way,'nd',ref=ref)
        for k,v in tags.items():
            ET.SubElement(way,'tag',k=k,v=v)
    return ET.tostring(root)[:-6] + extra.encode() + b'</osm>'


def square(tags=None, points=None):
    return xml([(1,points or [(0,0),(10,0),(10,10),(0,10)],tags or {'building':'yes'},True)])


def contains(point, poly):
    # Independent even/odd ray crossing, used to test triangle interiors.
    x,z = point
    inside = False
    for a,b in zip(poly,poly[1:]+poly[:1]):
        if (a[1]>z) != (b[1]>z) and x < (b[0]-a[0])*(z-a[1])/(b[1]-a[1])+a[0]:
            inside = not inside
    return inside


class GeometryCases(unittest.TestCase):
    def test_240_seeded_concave_extrusions_and_narrow_roads(self):
        rng = random.Random(20261010)
        for case in range(240):
            with self.subTest(case=case):
                w,h = rng.uniform(5,80),rng.uniform(5,80)
                cutx,cutz = w*rng.uniform(.2,.8),h*rng.uniform(.2,.8)
                p = [(0,0),(w,0),(w,cutz),(cutx,cutz),(cutx,h),(0,h)]
                theta,tx,tz = rng.uniform(-math.pi,math.pi),rng.uniform(-300,300),rng.uniform(-300,300)
                p = [(x*math.cos(theta)-z*math.sin(theta)+tx,x*math.sin(theta)+z*math.cos(theta)+tz) for x,z in p]
                original = p[:]
                if case%2: p.reverse()
                if case%3 == 0: p.insert(2,p[2])
                height,width = rng.uniform(.1,100),rng.uniform(.1,1)
                raw = xml([(1,p,{'building':'yes','height':str(height)},True),
                           (2,[(-400,-400),(-350,-360)],{'highway':'footway','width':str(width)},False)])
                glb,manifest = build(raw,BBOX)
                self.assertEqual(len(manifest['features']),2)
                check(glb,manifest)
                vertices,triangles,_ = decode(glb)[1][0]
                expected = w*cutz + cutx*(h-cutz)
                self.assertAlmostEqual(manifest['features'][0]['dimensions']['footprint_area_m2'],expected,places=7)
                self.assertTrue(math.isclose(volume(vertices,triangles),expected*height,rel_tol=2e-5))
                for tri in triangles:
                    if all(vertices[i][1] > 0 for i in tri):
                        centroid = tuple(sum(vertices[i][j] for i in tri)/3 for j in (0,2))
                        self.assertTrue(contains(centroid,original))
                self.assertEqual(build(raw,BBOX)[0],glb)

    def test_80_seeded_invalid_intersections_and_missing_nodes(self):
        rng = random.Random(71023)
        for case in range(80):
            x,z = rng.uniform(-50,50),rng.uniform(-50,50)
            w,h = rng.uniform(2,40),rng.uniform(2,40)
            raw = square(points=[(x,z),(x+w,z+h),(x,z+h),(x+w,z)])
            glb,m = build(raw,BBOX)
            self.assertEqual(m['omission_counts'],{'self_intersection':1})
            check(glb,m)
            missing = raw.replace(b'ref="1"', b'ref="9999"')
            self.assertEqual(build(missing,BBOX)[1]['omission_counts'],{'missing_node_reference':1})

    def test_reversed_winding_identical_glb(self):
        p = [(0,0),(20,0),(20,5),(5,5),(5,20),(0,20)]
        self.assertEqual(build(square(points=p),BBOX)[0],build(square(points=p[::-1]),BBOX)[0])

    def test_64_seeded_boundary_cases(self):
        rng=random.Random(88173)
        for case in range(64):
            with self.subTest(case=case):
                x,z=rng.uniform(-100,100),rng.uniform(-100,100)
                w,h=rng.uniform(10,50),rng.uniform(10,50)
                raw=square(points=[(x,z),(x+w,z),(x+w,z+h),(x,z+h)])
                coords=[(float(n.get('lon')),float(n.get('lat'))) for n in ET.fromstring(raw).findall('node')]
                box=(min(p[0] for p in coords),min(p[1] for p in coords),max(p[0] for p in coords),max(p[1] for p in coords))
                glb,m=build(raw,box)
                self.assertEqual(m['totals']['features'],1)
                check(glb,m)
                narrowed=(box[0],box[1],box[2]-1e-8,box[3])
                self.assertEqual(build(raw,narrowed)[1]['omission_counts'],{'outside_extent':1})
                road=xml([(1,[(x,z),(x+w,z)],{'highway':'footway','width':str(rng.uniform(.1,2))},False)])
                self.assertEqual(build(road,box)[1]['omission_counts'],{'road_ribbon_outside_extent':1})

    def test_forward_collinear_and_duplicates(self):
        raw = square(points=[(0,0),(5,0),(10,0),(10,0),(10,10),(0,10)])
        glb,m=build(raw,BBOX)
        self.assertAlmostEqual(m['features'][0]['dimensions']['footprint_area_m2'],100,places=8)
        check(glb,m)

    def test_degenerate_backtrack_and_touching(self):
        for points in [[(0,0),(10,0),(5,0),(5,10),(0,10)],[(0,0),(10,0),(10,10),(0,0),(0,10)],[(0,0)]*4,[(0,0),(1,0),(2,0)]]:
            with self.subTest(points=points):
                self.assertEqual(build(square(points=points),BBOX)[1]['totals']['features'],0)

    def test_boundary_inclusive_and_outside(self):
        # Exactly on a building boundary is supported; road width must also fit.
        bbox = (0.,0.,.001,.001)
        raw=b'<osm version="0.6"><node id="1" lon="0" lat="0"/><node id="2" lon=".001" lat="0"/><node id="3" lon=".001" lat=".001"/><node id="4" lon="0" lat=".001"/><way id="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/><tag k="building" v="yes"/></way></osm>'
        check(*build(raw,bbox))
        self.assertEqual(build(raw,bbox)[1]['totals']['features'],1)
        self.assertEqual(build(raw,(0,0,.0009,.001))[1]['omission_counts'],{'outside_extent':1})
        road=raw.replace(b'<nd ref="3"/><nd ref="4"/><nd ref="1"/>',b'').replace(b'building" v="yes',b'highway" v="service')
        self.assertEqual(build(road,bbox)[1]['omission_counts'],{'road_ribbon_outside_extent':1})

    def test_road_duplicate_points(self):
        raw=xml([(1,[(0,0),(0,0),(10,0),(10,10)],{'highway':'path','width':'0.1'},False)])
        glb,m=build(raw,BBOX)
        check(glb,m)
        self.assertEqual(m['features'][0]['triangle_count'],4)

    def test_float32_collapse_is_explicitly_omitted(self):
        raw=square(points=[(1000,900),(1000.00001,900),(1000.00001,1000),(1000,1000)])
        glb,m=build(raw,BBOX)
        self.assertEqual(m['omission_counts'],{'float32_precision_loss':1})
        check(glb,m)


class ContractTests(unittest.TestCase):
    def test_height_precedence(self):
        for tags,height,source in [({'height':'14 m','building:levels':'2'},14,'height'),({'building:levels':'2'},6,'building:levels * 3 m'),({},9,'default 9 m')]:
            tags['building']='yes'
            glb,m=build(square(tags),BBOX)
            d=m['features'][0]['dimensions']
            self.assertEqual((d['height_m'],d['height_source']),(height,source))
            check(glb,m)

    def test_invalid_dimensions_not_silently_defaulted(self):
        for value in ['NaN','Infinity','-2','0','601','4 ft','10;12','1e2']:
            with self.subTest(value=value):
                self.assertEqual(build(square({'building':'yes','height':value}),BBOX)[1]['totals']['features'],0)

    def test_width_defaults_and_unsupported_highways(self):
        raw=xml([(1,[(0,0),(10,0)],{'highway':'residential'},False)])
        self.assertEqual(build(raw,BBOX)[1]['features'][0]['dimensions']['width_m'],6)
        for tags in ({'highway':'construction'},{'highway':'pedestrian','area':'yes'}):
            self.assertEqual(build(xml([(1,[(0,0),(10,0)],tags,False)]),BBOX)[1]['omission_counts'],{'unsupported_highway':1})

    def test_elevation_and_parts_excluded(self):
        for k,v in [('bridge','yes'),('tunnel','yes'),('layer','1'),('min_height','2'),('building:min_level','1'),('ele','0'),('incline','0'),('location','underground'),('building:part','yes')]:
            m=build(square({'building':'yes',k:v}),BBOX)[1]
            self.assertEqual(m['totals']['features'],0,(k,m))
        self.assertEqual(build(square({'building':'yes','bridge':'no','layer':'0'}),BBOX)[1]['totals']['features'],1)

    def test_relations_prevent_hole_filling(self):
        raw=square().replace(b'</osm>',b'<relation id="9"><member type="way" ref="1" role="outer"/><tag k="type" v="multipolygon"/></relation></osm>')
        m=build(raw,BBOX)[1]
        self.assertEqual(m['omission_counts'],{'unsupported_relation':1,'unsupported_relation_member':1})

    def test_deleted_and_unclosed(self):
        self.assertEqual(build(square().replace(b'<way id="1"',b'<way visible="false" id="1"'),BBOX)[1]['omission_counts'],{'deleted_feature':1})
        raw=xml([(1,[(0,0),(10,0),(10,10)],{'building':'yes'},False)])
        self.assertEqual(build(raw,BBOX)[1]['omission_counts'],{'unclosed_building':1})

    def test_empty_and_unsupported(self):
        glb,m=build(b'<osm version="0.6"/>',BBOX)
        check(glb,m)
        raw=xml([(1,[(0,0),(10,0)],{'railway':'rail'},False)])
        self.assertEqual(build(raw,BBOX)[1]['omission_counts'],{'unsupported_feature':1})

    def test_invalid_xml_and_entities(self):
        cases=[b'<osm>',b'<osm version="0.6"><node></osm>',b'<osm version="0.6">\xff</osm>',
               b'<!DOCTYPE osm [<!ENTITY x SYSTEM "file:///etc/passwd">]><osm version="0.6">&x;</osm>',
               b'<!DOCTYPE osm [<!ENTITY x "ha">]><osm version="0.6">&x;</osm>',
               b'<!DOCTYPE osm SYSTEM "https://invalid.example/x"><osm version="0.6"/>',
               b'<osm version="0.6"><?thing x?></osm>',b'<osm version="0.6"><foo/></osm>',
               b'<osm version="0.6"><node id="1" lon="NaN" lat="0"/></osm>',
               b'<osm version="0.6"><node id="1" lon="0" lat="91"/></osm>',
               b'<osm version="0.6"><node id="1" lon="0" lat="0"/><node id="01" lon="0" lat="0"/></osm>',
               b'<osm version="0.6"><way id="1"><tag k="x" v="1"/><tag k="x" v="2"/></way></osm>',
               b'<osm version="0.6"><way id="1"><tag k="x" v="1"><x/></tag></way></osm>']
        for raw in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(ForgeError): build(raw,BBOX)

    def test_geographic_and_resource_limits(self):
        for bbox in [(0,0,1,1),(179,0,-179,1),(0,86,.001,86.001),(0,0,float('nan'),.001),(0,0,0,0)]:
            with self.subTest(bbox=bbox), self.assertRaises(ForgeError): build(square(),bbox)
        for limits in [Limits(input_bytes=10),Limits(nodes=2),Limits(ways=0),Limits(refs_per_way=3),Limits(vertices=1),Limits(triangles=1),Limits(seconds=-1)]:
            with self.subTest(limits=limits), self.assertRaises(ForgeError): build(square(),BBOX,limits)
        with self.assertRaises(ForgeError): build(b'<osm version="0.6"><relation id="1"/></osm>',BBOX,Limits(relations=0))
        with self.assertRaises(ForgeError): build(b'<osm version="0.6"><node id="1" lon="0" lat="0"><tag k="x" v="'+b'a'*2049+b'"/></node></osm>',BBOX)

    def test_input_order_does_not_change_mesh(self):
        raw=square()
        root=ET.fromstring(raw)
        root[:]=list(reversed(root))
        self.assertEqual(build(raw,BBOX)[0],build(ET.tostring(root),BBOX)[0])


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.input=self.base/'input.osm'
        self.input.write_bytes(square())
        self.output=self.base/'out'

    def test_repeat_byte_identity_and_unchanged_input(self):
        digest=hashlib.sha256(self.input.read_bytes()).hexdigest()
        convert(self.input,self.output,BBOX)
        other=self.base/'other'
        convert(self.input,other,BBOX)
        self.assertEqual({f.name:f.read_bytes() for f in self.output.iterdir()},{f.name:f.read_bytes() for f in other.iterdir()})
        self.assertEqual(hashlib.sha256(self.input.read_bytes()).hexdigest(),digest)

    def test_collision_preserves_existing_and_symlink(self):
        self.output.mkdir()
        (self.output/'keep').write_text('untouched')
        with self.assertRaises(ForgeError):convert(self.input,self.output,BBOX)
        self.assertEqual((self.output/'keep').read_text(),'untouched')
        link=self.base/'link'
        link.symlink_to(self.base/'missing')
        with self.assertRaises(ForgeError):convert(self.input,link,BBOX)
        self.assertTrue(link.is_symlink())

    def test_fifo_rejected_without_blocking(self):
        fifo=self.base/'fifo'
        os.mkfifo(fifo)
        with self.assertRaisesRegex(ForgeError,'regular_file'):convert(fifo,self.output,BBOX)

    def test_serialization_failure_no_output(self):
        with patch('street_scene_forge.core.json_bytes',side_effect=ValueError('injected serialization error')):
            with self.assertRaises(ValueError):convert(self.input,self.output,BBOX)
        self.assertFalse(self.output.exists())

    def test_write_failure_and_keyboard_interrupt_cleanup(self):
        original=Path.open
        for exception in [OSError('injected disk failure'),KeyboardInterrupt()]:
            def fail(path,*args,**kwargs):
                if path.name=='data.js':raise exception
                return original(path,*args,**kwargs)
            with patch.object(Path,'open',fail):
                with self.assertRaises(type(exception)):convert(self.input,self.output,BBOX)
            self.assertFalse(self.output.exists())
            self.assertEqual(self.input.read_bytes(),square())

    def test_output_limits_cleanup(self):
        for limits in [Limits(file_bytes=1),Limits(output_bytes=1)]:
            with self.assertRaisesRegex(ForgeError,'output_byte_limit'):convert(self.input,self.output,BBOX,limits)
            self.assertFalse(self.output.exists())

    def test_real_sigterm_during_write(self):
        code='''from pathlib import Path
import time
from street_scene_forge.__main__ import main
original=Path.open
def stall(path,*args,**kwargs):
 if path.name=='data.js':
  print('READY',flush=True)
  time.sleep(20)
 return original(path,*args,**kwargs)
Path.open=stall
raise SystemExit(main())
'''
        process=subprocess.Popen([sys.executable,'-c',code,str(self.input),'--output',str(self.output),'--bbox',*map(str,BBOX)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(),'READY')
            process.send_signal(signal.SIGTERM)
            out,err=process.communicate(timeout=5)
            self.assertEqual(process.returncode,130,err)
            self.assertFalse(self.output.exists())
        finally:
            if process.poll() is None:process.kill();process.wait()
            process.stdout.close();process.stderr.close()

    def test_cli_wall_clock_timeout_during_write(self):
        code='''from pathlib import Path
import time
import street_scene_forge.__main__ as cli
from street_scene_forge.core import Limits
cli.Limits=lambda: Limits(seconds=.1)
original=Path.open
def stall(path,*args,**kwargs):
 if path.name=='data.js': time.sleep(2)
 return original(path,*args,**kwargs)
Path.open=stall
raise SystemExit(cli.main())
'''
        p=subprocess.run([sys.executable,'-c',code,str(self.input),'--output',str(self.output),'--bbox',*map(str,BBOX)],capture_output=True,text=True,timeout=5)
        self.assertEqual(p.returncode,2,p.stderr)
        self.assertIn('runtime_limit',p.stderr)
        self.assertFalse(self.output.exists())


if __name__=='__main__':unittest.main()
