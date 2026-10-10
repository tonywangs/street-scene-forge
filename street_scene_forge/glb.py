"""Deterministic glTF 2.0 binary writer. One indexed primitive per feature."""
import json
import math
import struct


def json_bytes(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def encode(meshes):
    blob = bytearray()
    doc = {'asset': {'version': '2.0', 'generator': 'street-scene-forge 0.1.0'},
           'scene': 0, 'scenes': [{'nodes': list(range(len(meshes)))}]}
    if not meshes:
        doc['scenes'] = [{}]
    else:
        doc.update(nodes=[], meshes=[], accessors=[], bufferViews=[], materials=[
            {'name': 'building', 'pbrMetallicRoughness': {'baseColorFactor': [0.65, 0.77, 0.68, 1], 'metallicFactor': 0, 'roughnessFactor': 1}},
            {'name': 'road', 'doubleSided': True, 'pbrMetallicRoughness': {'baseColorFactor': [0.27, 0.34, 0.39, 1], 'metallicFactor': 0, 'roughnessFactor': 1}}])
    for mi, mesh in enumerate(meshes):
        positions = mesh['vertices']
        indices = [i for tri in mesh['triangles'] for i in tri]
        # Averaged vertex normals; hard-edge architecture shading is not modeled.
        normals = [[0., 0., 0.] for _ in positions]
        for a, b, c in mesh['triangles']:
            u = [positions[b][j]-positions[a][j] for j in range(3)]
            v = [positions[c][j]-positions[a][j] for j in range(3)]
            normal = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
            for i in (a, b, c):
                for j in range(3):
                    normals[i][j] += normal[j]
        normals = [[v / math.hypot(*n) for v in n] for n in normals]
        attributes = {}
        for name, values, kind, component, fmt in (
            ('POSITION', positions, 'VEC3', 5126, 'f'),
            ('NORMAL', normals, 'VEC3', 5126, 'f'),
            ('indices', indices, 'SCALAR', 5125, 'I')):
            offset = len(blob)
            flat = values if kind == 'SCALAR' else [v for row in values for v in row]
            raw = struct.pack('<' + fmt*len(flat), *flat)
            blob.extend(raw)
            view = len(doc['bufferViews'])
            doc['bufferViews'].append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(raw),
                                      'target': 34963 if name == 'indices' else 34962})
            accessor = {'bufferView': view, 'componentType': component, 'count': len(values), 'type': kind}
            if name == 'POSITION':
                # Bounds must describe the stored float32 values, not double inputs.
                stored = list(struct.unpack('<'+'f'*len(flat), raw))
                accessor['min'] = [min(stored[j::3]) for j in range(3)]
                accessor['max'] = [max(stored[j::3]) for j in range(3)]
            attributes[name] = len(doc['accessors'])
            doc['accessors'].append(accessor)
        doc['meshes'].append({'name': mesh['id'], 'primitives': [{'attributes': {k: attributes[k] for k in ('POSITION', 'NORMAL')},
                              'indices': attributes['indices'], 'material': 0 if mesh['kind'] == 'building' else 1}]})
        doc['nodes'].append({'mesh': mi, 'name': mesh['id'], 'extras': {'osm_id': mesh['id']}})
    if blob:
        doc['buffers'] = [{'byteLength': len(blob)}]
    data = json_bytes(doc)
    data += b' ' * (-len(data) % 4)
    chunks = struct.pack('<I4s', len(data), b'JSON') + data
    if blob:
        blob.extend(b'\0' * (-len(blob) % 4))
        chunks += struct.pack('<I4s', len(blob), b'BIN\0') + blob
    return struct.pack('<4sII', b'glTF', 2, 12+len(chunks)) + chunks
