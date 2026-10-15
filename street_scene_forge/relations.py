"""Conservative, bounded OSM member assembly and polygon-with-holes extrusion."""
from collections import Counter, defaultdict
import math

from .geometry import GeometryError, EPS, area, cross, intersects, on_segment, polygon
from .vendor.earcut import earcut


def assemble(relation, ways, nodes, project, bbox, budget):
    members = relation['members']
    if not members:
        raise GeometryError('empty_relation')
    if any(t != 'way' for t, _, _ in members):
        raise GeometryError('unsupported_relation_member_type')
    if any(role not in ('outer', 'inner') for _, _, role in members):
        raise GeometryError('unsupported_member_role')
    ids = [ref for _, ref, _ in members]
    if len(set(ids)) != len(ids):
        raise GeometryError('duplicate_relation_member')
    if any(ref not in ways or not ways[ref]['visible'] for ref in ids):
        raise GeometryError('missing_way_reference')
    if sum(len(ways[ref]['refs']) for ref in ids) > budget.limits.relation_refs:
        raise GeometryError('relation_geometry_limit')
    west, south, east, north = bbox
    groups = defaultdict(dict)
    for _, ref, role in members:
        budget.check()
        refs = ways[ref]['refs']
        if len(refs) < 2:
            raise GeometryError('unclosed_relation_ring')
        if any(r not in nodes or not nodes[r]['visible'] for r in refs):
            raise GeometryError('missing_node_reference')
        if any(not (west <= nodes[r]['coord'][0] <= east and south <= nodes[r]['coord'][1] <= north) for r in refs):
            raise GeometryError('outside_extent')
        groups[role][ref] = refs
    rings = []
    for role in ('outer', 'inner'):
        pending = groups[role].copy()
        endpoints = Counter(r for refs in pending.values() if refs[0] != refs[-1] for r in (refs[0], refs[-1]))
        if any(n != 2 for n in endpoints.values()):
            raise GeometryError('ambiguous_or_unclosed_ring')
        while pending:
            budget.check()
            start = min(pending, key=int)
            refs = list(pending.pop(start))
            used = [start]
            while refs[-1] != refs[0]:
                matches = [k for k, v in pending.items() if refs[-1] in (v[0], v[-1])]
                if len(matches) != 1:
                    raise GeometryError('ambiguous_or_unclosed_ring')
                key = matches[0]
                more = pending.pop(key)
                refs.extend((more if more[0] == refs[-1] else more[::-1])[1:])
                used.append(key)
            p, _ = polygon([project(*nodes[r]['coord']) for r in refs])
            rings.append({'role': role, 'points': p, 'source_node_ids': refs,
                          'member_way_ids': sorted(used, key=int)})
    if len(rings) > 32:
        raise GeometryError('relation_geometry_limit')
    rings.sort(key=lambda r: (r['role'] != 'outer', r['points']))
    # Pairwise boundary disjointness must precede any containment decision.
    for i, a in enumerate(rings):
        for b in rings[i+1:]:
            budget.check()
            if any(intersects(p, q, r, s) for p, q in edges(a['points']) for r, s in edges(b['points'])):
                raise GeometryError('touching_or_intersecting_rings')
    outers = [r for r in rings if r['role'] == 'outer']
    inners = [r for r in rings if r['role'] == 'inner']
    if not outers:
        raise GeometryError('missing_outer_ring')
    for group in (outers, inners):
        if any(inside(a['points'][0], b['points']) or inside(b['points'][0], a['points'])
               for i, a in enumerate(group) for b in group[i+1:]):
            raise GeometryError('nested_rings_unsupported')
    for hole in inners:
        owners = [i for i, outer in enumerate(outers) if inside(hole['points'][0], outer['points'])]
        if len(owners) != 1:
            raise GeometryError('inner_not_contained')
        hole['outer_index'] = owners[0]
    return rings


def edges(points):
    return zip(points, points[1:]+points[:1])


def inside(p, ring):
    # Strict after boundary-disjointness validation.
    x, y = p
    result = False
    for a, b in edges(ring):
        if (a[1] > y) != (b[1] > y) and x < a[0]+(y-a[1])*(b[0]-a[0])/(b[1]-a[1]):
            result = not result
    return result


def extrude(rings, height, budget):
    vertices, triangles, measure = [], [], 0.
    outers = [r for r in rings if r['role'] == 'outer']
    for index, outer in enumerate(outers):
        budget.check()
        loops = [outer['points']] + [r['points'][::-1] for r in rings if r.get('outer_index') == index]
        points, holes, boundary = [], [], []
        for loop in loops:
            offset = len(points)
            if offset:
                holes.append(offset)
            boundary.extend((offset+i, offset+(i+1) % len(loop)) for i in range(len(loop)))
            points.extend(loop)
        try:
            flat = earcut([v for p in points for v in p], holes, 2)
        except (RecursionError, ZeroDivisionError):
            raise GeometryError('triangulation_failed') from None
        cap = [tuple(flat[i:i+3]) for i in range(0, len(flat), 3)]
        cap = conform_cap(points, cap, budget)
        expected = sum(area(loop) for loop in loops)
        if not cap or any(cross(*(points[i] for i in tri)) <= EPS for tri in cap):
            raise GeometryError('degenerate_triangle')
        actual = sum(cross(*(points[i] for i in t))/2 for t in cap)
        if not math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-6):
            raise GeometryError('triangulation_area_mismatch')
        # No missing boundaries, duplicate triangles, or nonconforming T-junctions.
        directed = Counter((a, b) for tri in cap for a, b in edges(list(tri)))
        boundary_set = set(boundary)
        if any(directed[a,b] != 1 or directed[b,a] for a,b in boundary) or any(
                count != 1 or ((a,b) not in boundary_set and directed[b,a] != 1)
                for (a,b), count in directed.items()):
            raise GeometryError('triangulation_topology_mismatch')
        base, n = len(vertices), len(points)
        vertices.extend((x, y, z) for y in (0., height) for x, z in points)
        local = cap + [(c+n, b+n, a+n) for a,b,c in cap]
        for a,b in boundary:
            local.extend(((a,a+n,b+n),(a,b+n,b)))
        triangles.extend(tuple(base+i for i in t) for t in local)
        measure += expected
    return vertices, triangles, measure


def conform_cap(points, cap, budget):
    """Remove zero-area bridge faces and split T-junctions without moving vertices.

    Earcut's documented nonconforming output is unsuitable for closed solids.
    Every resulting cap is subsequently checked against the exact boundary graph.
    """
    pending = [t for t in cap if abs(cross(*(points[i] for i in t))) > EPS]
    result = []
    splits = 0
    while pending:
        budget.check()
        tri = pending.pop()
        for k in range(3):
            a,b,c = tri[k],tri[(k+1)%3],tri[(k+2)%3]
            candidates = [i for i,p in enumerate(points) if i not in tri
                          and on_segment(points[a],points[b],p)
                          and math.dist(p,points[a]) > 1e-6 and math.dist(p,points[b]) > 1e-6]
            if candidates:
                i = min(candidates, key=lambda j: (math.dist(points[a],points[j]),j))
                pending.extend(((a,i,c),(i,b,c)))
                splits += 1
                if splits > len(points)*4:
                    raise GeometryError('triangulation_failed')
                break
        else:
            result.append(tri)
    return result
