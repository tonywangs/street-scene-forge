"""Input contract, provenance, limits, and all-or-clean output lifecycle."""
import base64
from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import math
from pathlib import Path
import re
import shutil
import time
from xml.parsers import expat

from . import __version__
from .geometry import GeometryError, check_float32, extrusion, ribbon
from .glb import encode, json_bytes

RADIUS = 6371008.8
ROAD_WIDTHS = {'motorway': 12., 'trunk': 10., 'primary': 8., 'secondary': 7.,
               'tertiary': 6., 'residential': 6., 'unclassified': 6., 'service': 4.,
               'living_street': 4., 'pedestrian': 3., 'footway': 1.5,
               'path': 1., 'cycleway': 2., 'track': 3.}


class ForgeError(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    input_bytes: int = 8 * 1024 * 1024
    nodes: int = 50000
    ways: int = 5000
    relations: int = 5000
    refs_per_way: int = 256
    vertices: int = 100000
    triangles: int = 100000
    extent_m: float = 5000.
    seconds: float = 30.
    output_bytes: int = 24 * 1024 * 1024
    file_bytes: int = 10 * 1024 * 1024


class Budget:
    def __init__(self, limits):
        self.limits = limits
        self.end = time.monotonic() + limits.seconds

    def check(self):
        if time.monotonic() > self.end:
            raise ForgeError('runtime_limit')


def identifier(value):
    if not re.fullmatch(r'-?[0-9]{1,20}', value or ''):
        raise ForgeError('invalid_osm_id')
    return str(int(value))


def read_osm(raw, budget):
    """Expat with entity/DTD rejection, bounded nesting and element counts."""
    nodes, ways, relations, diagnostics = {}, {}, {}, []
    stack = []
    current = None
    counts = Counter()
    parser = expat.ParserCreate('UTF-8')

    def forbidden(*args):
        raise ForgeError('forbidden_xml_dtd_or_entity')

    def start(name, attrs):
        nonlocal current
        budget.check()
        if len(stack) >= 3:
            raise ForgeError('xml_depth_limit')
        if len(attrs) > 32 or any(len(k) > 128 or len(v) > 2048 for k, v in attrs.items()):
            raise ForgeError('xml_attribute_limit')
        if not stack:
            if name != 'osm' or attrs.get('version') != '0.6':
                raise ForgeError('expected_osm_0.6')
        elif len(stack) == 1:
            if name not in ('node', 'way', 'relation', 'bounds', 'note', 'meta'):
                raise ForgeError('unsupported_xml_element:' + name[:80])
            if name in ('node', 'way', 'relation'):
                counts[name] += 1
                if counts[name] > getattr(budget.limits, name+'s'):
                    raise ForgeError(name+'_limit')
                ident = identifier(attrs.get('id'))
                target = {'node': nodes, 'way': ways, 'relation': relations}[name]
                if ident in target:
                    raise ForgeError('duplicate_'+name+'_id')
                current = {'id': ident, 'tags': {}, 'refs': [], 'members': [],
                           'visible': attrs.get('visible', 'true') != 'false'}
                if name == 'node':
                    try:
                        lat, lon = float(attrs['lat']), float(attrs['lon'])
                    except (KeyError, ValueError):
                        raise ForgeError('invalid_node_coordinate') from None
                    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                        raise ForgeError('invalid_node_coordinate')
                    current['coord'] = (lon, lat)
                target[ident] = current
        else:
            if stack[-1] not in ('node', 'way', 'relation'):
                raise ForgeError('unexpected_xml_child')
            if name == 'tag':
                if set(attrs) != {'k', 'v'} or attrs['k'] in current['tags']:
                    raise ForgeError('invalid_or_duplicate_tag')
                current['tags'][attrs['k']] = attrs['v']
                if len(current['tags']) > 128:
                    raise ForgeError('tag_limit')
            elif name == 'nd' and stack[-1] == 'way':
                current['refs'].append(identifier(attrs.get('ref')))
                if len(current['refs']) > budget.limits.refs_per_way:
                    raise ForgeError('way_vertex_limit')
            elif name == 'member' and stack[-1] == 'relation':
                if len(current['members']) >= 1000:
                    raise ForgeError('relation_member_limit')
                current['members'].append((attrs.get('type'), identifier(attrs.get('ref'))))
            else:
                raise ForgeError('unexpected_xml_child')
        stack.append(name)

    parser.StartElementHandler = start
    parser.EndElementHandler = lambda name: stack.pop()
    parser.StartDoctypeDeclHandler = forbidden
    parser.EntityDeclHandler = forbidden
    parser.ExternalEntityRefHandler = forbidden
    parser.ProcessingInstructionHandler = forbidden
    try:
        for offset in range(0, len(raw), 65536):
            parser.Parse(raw[offset:offset+65536], False)
        parser.Parse(b'', True)
    except expat.ExpatError as exc:
        raise ForgeError('malformed_xml:' + str(exc)) from None
    for ident, node in sorted(nodes.items(), key=lambda x: int(x[0])):
        if node['tags']:
            diagnostics.append({'id': 'node/'+ident, 'reason': 'standalone_node_not_rendered'})
    return nodes, ways, relations, diagnostics, dict(counts)


def extent(bbox, limits):
    if len(bbox) != 4 or not all(math.isfinite(v) for v in bbox):
        raise ForgeError('invalid_bbox')
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180 and -85 <= south < north <= 85):
        raise ForgeError('invalid_bbox_no_antimeridian_or_poles')
    lon0, lat0 = (west+east)/2, (south+north)/2
    scale = RADIUS * math.pi / 180
    # Bound longitude extent using the largest cosine within the latitude interval.
    near_equator = 0 if south <= 0 <= north else min(abs(south), abs(north))
    if max((east-west)*scale*math.cos(math.radians(near_equator)), (north-south)*scale) > limits.extent_m:
        raise ForgeError('geographic_extent_limit')
    def project(lon, lat):
        return ((lon-lon0)*scale*math.cos(math.radians(lat0)), -(lat-lat0)*scale)
    return project, {'name': 'local_equirectangular', 'radius_m': RADIUS, 'origin_lon': lon0,
                     'origin_lat': lat0, 'axes': {'x': 'east', 'y': 'up', 'z': 'south'}, 'units': 'metres'}


def dimension(text, maximum, minimum=0.1, metric=True):
    pattern = r'([0-9]+(?:\.[0-9]+)?)(?: m)?' if metric else r'([0-9]+(?:\.[0-9]+)?)'
    match = re.fullmatch(pattern, text.strip())
    if not match:
        raise GeometryError('invalid_dimension')
    value = float(match[1])
    if not minimum <= value <= maximum:
        raise GeometryError('dimension_out_of_range')
    return value


def build(raw, bbox, limits=Limits(), budget=None):
    budget = budget or Budget(limits)
    if len(raw) > limits.input_bytes:
        raise ForgeError('input_byte_limit')
    project, projection = extent(bbox, limits)
    nodes, ways, relations, diagnostics, counts = read_osm(raw, budget)
    blocked_members = set()
    for ident, relation in sorted(relations.items(), key=lambda x: int(x[0])):
        diagnostics.append({'id': 'relation/'+ident, 'reason': 'unsupported_relation'})
        if relation['tags'].get('type') in ('multipolygon', 'building') or 'building' in relation['tags']:
            blocked_members.update(ref for typ, ref in relation['members'] if typ == 'way')
    meshes, features = [], []
    nv = nt = 0
    west, south, east, north = bbox
    lower = project(west, north)
    upper = project(east, south)
    for ident, way in sorted(ways.items(), key=lambda x: int(x[0])):
        budget.check()
        osm_id = 'way/'+ident
        tags = way['tags']
        def reject(reason):
            diagnostics.append({'id': osm_id, 'reason': reason})
        if not way['visible']:
            reject('deleted_feature')
            continue
        kind = 'building' if tags.get('building') not in (None, 'no') else 'road' if 'highway' in tags else None
        if 'building:part' in tags:
            reject('unsupported_building_part')
            continue
        if not kind:
            reject('unsupported_feature')
            continue
        if ident in blocked_members:
            reject('unsupported_relation_member')
            continue
        if any(tags.get(k, default) != default for k, default in
               (('bridge', 'no'), ('tunnel', 'no'), ('layer', '0'), ('min_height', '0'),
                ('building:min_level', '0'), ('location', 'surface'))) or 'ele' in tags or 'incline' in tags:
            reject('elevation_dependent_feature')
            continue
        if any(ref not in nodes or not nodes[ref]['visible'] for ref in way['refs']):
            reject('missing_node_reference')
            continue
        coords = [nodes[ref]['coord'] for ref in way['refs']]
        if any(not (west <= lon <= east and south <= lat <= north) for lon, lat in coords):
            reject('outside_extent')
            continue
        points = [project(*coord) for coord in coords]
        assumptions = []
        try:
            if kind == 'building':
                if len(way['refs']) < 4 or way['refs'][0] != way['refs'][-1]:
                    raise GeometryError('unclosed_building')
                if 'height' in tags:
                    value, source = dimension(tags['height'], 600), 'height'
                elif 'building:levels' in tags:
                    value, source = 3*dimension(tags['building:levels'], 200, 1, False), 'building:levels * 3 m'
                else:
                    value, source = 9., 'default 9 m'
                if source != 'height':
                    assumptions.append('height inferred; roof included in flat extrusion')
                assumptions.append('flat roof and ground; no facade detail')
                vertices, triangles, measure = extrusion(points, value)
                dims = {'height_m': value, 'height_source': source, 'height_inferred': source != 'height',
                        'footprint_area_m2': measure, 'volume_m3': measure*value}
            else:
                if tags['highway'] not in ROAD_WIDTHS or tags.get('area') == 'yes':
                    raise GeometryError('unsupported_highway')
                value = dimension(tags['width'], 50, 0.1) if 'width' in tags else ROAD_WIDTHS[tags['highway']]
                source = 'width' if 'width' in tags else 'default for '+tags['highway']
                vertices, triangles, measure = ribbon(points, value)
                if any(not (lower[0]-1e-7 <= x <= upper[0]+1e-7 and lower[1]-1e-7 <= z <= upper[1]+1e-7) for x, _, z in vertices):
                    raise GeometryError('road_ribbon_outside_extent')
                assumptions.append('independent butt-ended segments; bends and junctions may overlap or have gaps')
                dims = {'width_m': value, 'width_source': source, 'width_inferred': source != 'width', 'centerline_length_m': measure}
            check_float32(vertices, triangles)
        except GeometryError as exc:
            reject(str(exc))
            continue
        nv += len(vertices)
        nt += len(triangles)
        if nv > limits.vertices or nt > limits.triangles:
            raise ForgeError('mesh_resource_limit')
        bounds = {'min': [min(p[i] for p in vertices) for i in range(3)], 'max': [max(p[i] for p in vertices) for i in range(3)]}
        features.append({'id': osm_id, 'mesh': len(meshes), 'kind': kind, 'tags': tags,
                         'source_node_ids': way['refs'], 'dimensions': dims, 'bounds_m': bounds,
                         'vertex_count': len(vertices), 'triangle_count': len(triangles), 'assumptions': assumptions})
        meshes.append({'id': osm_id, 'kind': kind, 'vertices': vertices, 'triangles': triangles})
    budget.check()
    manifest = {'schema_version': 1, 'generator': 'street-scene-forge '+__version__,
                'input': {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'element_counts': counts},
                'bbox': list(bbox), 'projection': projection, 'limits': asdict(limits),
                'attribution': 'Map data © OpenStreetMap contributors, ODbL 1.0 when sourced from OSM. Synthetic fixtures are labeled separately.',
                'limitations': ['Approximate dimensions, not surveying accuracy.', 'Flat terrain; incomplete map structures.',
                                'Whole-feature boundary omission; no clipping.', 'No game-engine, physical-world, or human-usability validation.'],
                'features': features, 'diagnostics': diagnostics,
                'omission_counts': dict(sorted(Counter(d['reason'] for d in diagnostics).items())),
                'totals': {'features': len(features), 'vertices': nv, 'triangles': nt}}
    glb = encode(meshes)
    manifest['assets'] = {'scene.glb': {'sha256': hashlib.sha256(glb).hexdigest(), 'bytes': len(glb)}}
    return glb, manifest


def artifacts(glb, manifest):
    import importlib.resources
    package = importlib.resources.files('street_scene_forge')
    files = {'scene.glb': glb, 'manifest.json': json_bytes(manifest)+b'\n'}
    # JavaScript data is serialized, never interpolated into HTML or evaluated.
    payload = {'manifest': manifest, 'glb': base64.b64encode(glb).decode('ascii')}
    # JSON.parse preserves keys such as "__proto__" as ordinary own properties;
    # embedding an object literal would give that key special JS semantics.
    literal = json_bytes(json_bytes(payload).decode('utf-8'))
    files['data.js'] = b'"use strict";\nconst FORGE_DATA = JSON.parse(' + literal.replace(b'<', b'\\u003c').replace(b'>', b'\\u003e').replace(b'&', b'\\u0026') + b');\n'
    for name in ('index.html', 'preview.js', 'style.css'):
        files[name] = package.joinpath(name).read_bytes()
    return files


def convert(input_path, output_path, bbox, limits=Limits()):
    budget = Budget(limits)
    source, output = Path(input_path), Path(output_path)
    if output.exists() or output.is_symlink():
        raise ForgeError('output_exists')
    # Regular files only, avoiding FIFO/device blocking and reading at most the cap + 1.
    import os
    import stat
    descriptor = os.open(source, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ForgeError('input_must_be_regular_file')
        raw = handle.read(limits.input_bytes+1)
    glb, manifest = build(raw, bbox, limits, budget)
    files = artifacts(glb, manifest)
    if sum(map(len, files.values())) > limits.output_bytes or any(len(v) > limits.file_bytes for v in files.values()):
        raise ForgeError('output_byte_limit')
    budget.check()
    created = False
    try:
        output.mkdir()  # Exclusive reservation; never replace an existing directory.
        created = True
        for name, content in files.items():
            budget.check()
            with (output/name).open('xb') as handle:
                handle.write(content)
        budget.check()
    except BaseException:
        if created:
            shutil.rmtree(output)
        raise
    return manifest
