import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from street_scene_forge.core import convert, ForgeError

ROOT = Path(__file__).resolve().parents[1]

class ProvenanceTests(unittest.TestCase):
    def test_bound_source_and_portable_assets(self):
        source = ROOT / 'fixtures/synthetic.osm'
        bbox = [-.0009,-.0009,.0009,.0009]
        meta = dict(sha256=hashlib.sha256(source.read_bytes()).hexdigest(), bbox=bbox,
                    acquired_utc='2026-10-19T00:00:00Z', attribution='Synthetic test', license='CC0-1.0', url='https://example.org/<script>')
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            record = tmp / 'source.json'
            record.write_text(json.dumps(meta))
            manifest = convert(source,tmp/'scene',bbox,provenance_path=record)
            self.assertEqual(manifest['source'],meta)
            self.assertEqual(json.loads((tmp/'scene/source.provenance.json').read_text()),meta)
            self.assertTrue((tmp/'scene/player.js').is_file())
            self.assertEqual((tmp/'scene/source.osm').read_bytes(),source.read_bytes())
            self.assertNotIn('<script>',(tmp/'scene/data.js').read_text())
            for key,value in [('sha256','bad'),('bbox',[0,0,1,1]),('url','')]:
                record.write_text(json.dumps(dict(meta,**{key:value})))
                with self.assertRaises(ForgeError):
                    convert(source,tmp/'bad',bbox,provenance_path=record)
                self.assertFalse((tmp/'bad').exists())
