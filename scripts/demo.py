#!/usr/bin/env python3
"""Generate the pinned real Berlin neighborhood and launch it on loopback only."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from street_scene_forge.core import convert


def generate(output):
    provenance = ROOT / 'fixtures/berlin-neighborhood.provenance.json'
    meta = json.loads(provenance.read_text())
    return convert(ROOT / 'fixtures' / meta['fixture'], output, meta['bbox'], provenance_path=provenance)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', type=Path, help='generate a portable directory and exit (must not exist)')
    parser.add_argument('--port', type=int, default=0, help='loopback port; default chooses an available port')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if args.export:
        generate(args.export)
        print(f'Offline demo: {args.export.resolve() / "index.html"}?walk=1')
        return
    with tempfile.TemporaryDirectory(prefix='street-scene-demo-') as temp:
        output = Path(temp) / 'berlin'
        manifest = generate(output)
        handler = partial(SimpleHTTPRequestHandler, directory=str(output))
        with ThreadingHTTPServer(('127.0.0.1', args.port), handler) as server:
            url = f'http://127.0.0.1:{server.server_port}/index.html?walk=1'
            print(f'{manifest["totals"]["features"]} real map features. Open {url}\nWASD / arrows to walk; drag to orbit; Escape to inspect. Ctrl+C stops.', flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass

if __name__ == '__main__':
    main()
