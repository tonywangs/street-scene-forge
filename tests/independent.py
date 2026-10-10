"""Read back GLB bytes without importing any exporter geometry helpers."""
import hashlib
import json
import math
import struct
from collections import Counter


def decode(raw):
    magic, version, length = struct.unpack_from('<4sII', raw)
    assert magic == b'glTF' and version == 2 and length == len(raw)
    size, kind = struct.unpack_from('<I4s', raw, 12)
    assert kind == b'JSON' and size % 4 == 0
    doc = json.loads(raw[20:20+size])
    binary = b''
    if 20+size < len(raw):
        count, kind = struct.unpack_from('<I4s', raw, 20+size)
        assert kind == b'BIN\0'
        binary = raw[28+size:]
        assert count == len(binary)
    def read(index):
        accessor = doc['accessors'][index]
        view = doc['bufferViews'][accessor['bufferView']]
        assert view['buffer'] == 0
        arity = {'VEC3': 3, 'SCALAR': 1}[accessor['type']]
        fmt = {5126: 'f', 5125: 'I'}[accessor['componentType']]
        offset = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
        size = arity * 4 * accessor['count']
        assert offset % 4 == 0 and offset+size <= len(binary)
        assert size <= view['byteLength']
        flat = struct.unpack_from('<'+fmt*(arity*accessor['count']), binary, offset)
        return [tuple(flat[i:i+arity]) for i in range(0, len(flat), arity)] if arity > 1 else list(flat)
    meshes = []
    for mesh in doc.get('meshes', []):
        primitive, = mesh['primitives']
        vertices = read(primitive['attributes']['POSITION'])
        normals = read(primitive['attributes']['NORMAL'])
        flat = read(primitive['indices'])
        assert len(flat) % 3 == 0
        meshes.append((vertices, [tuple(flat[i:i+3]) for i in range(0,len(flat),3)], normals))
    return doc, meshes


def normal(a, b, c):
    u, v = [b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)]
    return (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])


def volume(vertices, triangles):
    return sum(sum(vertices[a][j]*normal((0,0,0),vertices[b],vertices[c])[j] for j in range(3))/6 for a,b,c in triangles)


def check(raw, manifest):
    assert manifest['assets']['scene.glb']['sha256'] == hashlib.sha256(raw).hexdigest()
    doc, meshes = decode(raw)
    assert len(meshes) == len(manifest['features']) == manifest['totals']['features']
    assert len(doc.get('nodes', [])) == len(meshes)
    max_bound_error = max_dimension_error = 0.
    for i, (feature, (vertices, triangles, normals)) in enumerate(zip(manifest['features'], meshes)):
        assert feature['mesh'] == i
        assert doc['nodes'][i]['mesh'] == i and doc['nodes'][i]['extras']['osm_id'] == feature['id']
        assert doc['meshes'][i]['name'] == feature['id']
        assert len(vertices) == feature['vertex_count'] and len(triangles) == feature['triangle_count']
        assert all(math.isfinite(v) for p in vertices for v in p)
        assert all(0 <= j < len(vertices) for t in triangles for j in t)
        assert all(abs(math.hypot(*n)-1) < 1e-5 for n in normals)
        bounds = {'min': [min(p[j] for p in vertices) for j in range(3)], 'max': [max(p[j] for p in vertices) for j in range(3)]}
        accessor = doc['accessors'][doc['meshes'][i]['primitives'][0]['attributes']['POSITION']]
        assert accessor['min'] == bounds['min'] and accessor['max'] == bounds['max']
        error = max(abs(bounds[k][j]-feature['bounds_m'][k][j]) for k in bounds for j in range(3))
        max_bound_error = max(error, max_bound_error)
        assert error < .001, error
        assert all(math.hypot(*normal(*(vertices[j] for j in tri))) > 1e-8 for tri in triangles)
        if feature['kind'] == 'building':
            edges = Counter((a,b) for tri in triangles for a,b in zip(tri, tri[1:]+tri[:1]))
            assert all(count == 1 and edges[b,a] == 1 for (a,b),count in edges.items())
            height = bounds['max'][1]-bounds['min'][1]
            err = abs(height-feature['dimensions']['height_m'])
            max_dimension_error = max(err,max_dimension_error)
            assert err < .001
            vol = volume(vertices,triangles)
            expected = feature['dimensions']['volume_m3']
            assert vol > 0 and math.isclose(vol, expected, rel_tol=2e-5, abs_tol=.005), (vol,expected)
            top_area = 0.
            for a,b,c in triangles:
                n = normal(vertices[a],vertices[b],vertices[c])
                if all(vertices[j][1] == bounds['max'][1] for j in (a,b,c)):
                    assert n[1] > 0
                    top_area += n[1]/2
                if all(vertices[j][1] == bounds['min'][1] for j in (a,b,c)):
                    assert n[1] < 0
            assert math.isclose(top_area, feature['dimensions']['footprint_area_m2'], rel_tol=2e-5, abs_tol=.001)
        else:
            for triangle in triangles:
                assert normal(*(vertices[j] for j in triangle))[1] > 0
            for k in range(0,len(vertices),4):
                width = math.dist(vertices[k],vertices[k+3])
                error = abs(width-feature['dimensions']['width_m'])
                max_dimension_error = max(error,max_dimension_error)
                assert error < .001
    assert sum(len(m[0]) for m in meshes) == manifest['totals']['vertices']
    assert sum(len(m[1]) for m in meshes) == manifest['totals']['triangles']
    return {'meshes':len(meshes), 'max_bounds_float32_error_m':max_bound_error, 'max_dimension_float32_error_m':max_dimension_error}
