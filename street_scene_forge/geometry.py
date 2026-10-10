"""Small, bounded planar geometry. Coordinates are (east, south), in metres."""
import math
import struct

EPS = 1e-8


class GeometryError(ValueError):
    pass


def check_float32(vertices, triangles):
    """Reject geometry that collapses or materially changes at GLB precision."""
    stored = [struct.unpack('<3f', struct.pack('<3f', *v)) for v in vertices]
    def normal(points, tri):
        a, b, c = (points[i] for i in tri)
        u, v = [b[j]-a[j] for j in range(3)], [c[j]-a[j] for j in range(3)]
        return (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
    for tri in triangles:
        before, after = normal(vertices, tri), normal(stored, tri)
        if (math.hypot(*after) <= EPS or sum(a*b for a,b in zip(before,after)) <= 0 or
                math.dist(before, after) > .01*math.hypot(*before)):
            raise GeometryError('float32_precision_loss')


def cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])


def area(points):
    return sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(points, points[1:]+points[:1])) / 2


def on_segment(a, b, p):
    return (abs(cross(a, b, p)) <= EPS and
            min(a[0], b[0])-EPS <= p[0] <= max(a[0], b[0])+EPS and
            min(a[1], b[1])-EPS <= p[1] <= max(a[1], b[1])+EPS)


def intersects(a, b, c, d):
    x, y, z, w = cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b)
    return ((x > EPS and y < -EPS or x < -EPS and y > EPS) and
            (z > EPS and w < -EPS or z < -EPS and w > EPS) or
            on_segment(a, b, c) or on_segment(a, b, d) or
            on_segment(c, d, a) or on_segment(c, d, b))


def clean(points, closed=False):
    result = []
    for p in points:
        if not all(math.isfinite(x) for x in p):
            raise GeometryError('nonfinite_coordinate')
        p = tuple(p)
        if not result or math.dist(result[-1], p) > 1e-6:
            result.append(p)
    if closed and len(result) > 1 and math.dist(result[0], result[-1]) <= 1e-6:
        result.pop()
    if len(result) < (3 if closed else 2):
        raise GeometryError('degenerate_geometry')
    return result


def polygon(points):
    p = clean(points, True)
    n = len(p)
    # Nonadjacent contacts, repeated vertices and bow ties are all invalid.
    for i in range(n):
        for j in range(i+1, n):
            if j == i+1 or i == 0 and j == n-1:
                continue
            if intersects(p[i], p[(i+1) % n], p[j], p[(j+1) % n]):
                raise GeometryError('self_intersection')
    # Reject adjacent backtracking; remove forward collinear points.
    changed = True
    while changed and len(p) > 3:
        changed = False
        for i in range(len(p)):
            a, b, c = p[i-1], p[i], p[(i+1) % len(p)]
            if abs(cross(a, b, c)) <= EPS:
                if not on_segment(a, c, b):
                    raise GeometryError('backtracking_edge')
                p.pop(i)
                changed = True
                break
    a = area(p)
    if abs(a) < 1e-4:
        raise GeometryError('degenerate_geometry')
    if a < 0:
        p.reverse()
    # Canonical start and winding make reversed inputs produce identical meshes.
    start = min(range(len(p)), key=lambda i: p[i])
    p = p[start:] + p[:start]
    remaining = list(range(len(p)))
    triangles = []
    while len(remaining) > 3:
        for k, b in enumerate(remaining):
            a, c = remaining[k-1], remaining[(k+1) % len(remaining)]
            if cross(p[a], p[b], p[c]) <= EPS:
                continue
            if any(all(v >= -EPS for v in (cross(p[a], p[b], p[j]),
                   cross(p[b], p[c], p[j]), cross(p[c], p[a], p[j])))
                   for j in remaining if j not in (a, b, c)):
                continue
            triangles.append((a, b, c))
            remaining.pop(k)
            break
        else:
            raise GeometryError('triangulation_failed')
    if cross(*(p[i] for i in remaining)) <= EPS:
        raise GeometryError('degenerate_triangle')
    triangles.append(tuple(remaining))
    return p, triangles


def extrusion(points, height):
    p, cap = polygon(points)
    n = len(p)
    vertices = [(x, y, z) for y in (0.0, height) for x, z in p]
    # CCW in x,z points down in a right-handed x,y,z system.
    triangles = list(cap) + [(c+n, b+n, a+n) for a, b, c in cap]
    for i in range(n):
        j = (i+1) % n
        triangles.extend(((i, i+n, j+n), (i, j+n, j)))
    return vertices, triangles, area(p)


def ribbon(points, width):
    p = clean(points)
    # Butt-ended segment ribbons: no invented intersection or join topology.
    vertices, triangles = [], []
    for a, b in zip(p, p[1:]):
        dx, dz = b[0]-a[0], b[1]-a[1]
        length = math.hypot(dx, dz)
        nx, nz = -dz/length*width/2, dx/length*width/2
        base = len(vertices)
        vertices.extend((x, 0.02, z) for x, z in
                        ((a[0]+nx, a[1]+nz), (b[0]+nx, b[1]+nz),
                         (b[0]-nx, b[1]-nz), (a[0]-nx, a[1]-nz)))
        triangles.extend(((base, base+1, base+2), (base, base+2, base+3)))
    return vertices, triangles, sum(math.dist(a, b) for a, b in zip(p, p[1:]))
