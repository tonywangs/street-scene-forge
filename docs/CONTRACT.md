# Version 1 input/output contract

## Input grammar and omissions

Accept a local regular file containing UTF-8 OSM XML, root `<osm version="0.6">`.
Nodes, ways, and relations may be unordered. IDs are signed decimal integers of
at most 20 digits, normalized before duplicate detection. Duplicate IDs or tag
keys reject the file. Coordinate values must be finite and within longitude
±180°, latitude ±90°. Invisible nodes cannot resolve a way reference. Visible
nodes need coordinates even if unused.

Only top-level `node`, `way`, `relation`, `bounds`, `note`, and `meta` elements are
accepted. `tag`, `nd`, and `member` children are accepted in their corresponding
OSM contexts. XML declarations and predefined XML escapes are allowed. DTDs,
custom entities, external entities, processing instructions, deeper nesting,
namespaces, and other elements reject the input. XML comments and text do not
instruct the converter. No imported URL is dereferenced. Explicit CLI bounds,
not input `<bounds>`, control inclusion.

Every way either produces exactly one feature and one GLB mesh or one omission.
Every relation is reported as unsupported. Multipolygon/building-relation member
ways are also excluded, so a known courtyard outer ring cannot become a filled
building accidentally. Other relation types (for example routes) do not suppress
otherwise supported ways. Tagged nodes are counted as
`standalone_node_not_rendered`; ordinary footprint nodes are not omissions.

Omission diagnostics contain source ID and a stable reason, not a traceback.
Only the first applicable reason is emitted for each way. The aggregate counts
count diagnostic entries, including unsupported relations and tagged nodes;
they are **not** a claim to know the number of real-world buildings omitted.

Common reasons:

| Reason | Meaning |
| --- | --- |
| `unsupported_feature`, `unsupported_highway` | No supported building/road interpretation, excluded road class, or road area |
| `unsupported_relation`, `unsupported_relation_member` | Relation topology not implemented |
| `unsupported_building_part` | `building:part` tag present |
| `deleted_feature` | `visible=false` |
| `elevation_dependent_feature` | Bridge/tunnel, nonzero layer/base, `ele`/`incline`, or non-surface location |
| `missing_node_reference` | Referenced node missing or invisible |
| `outside_extent`, `road_ribbon_outside_extent` | Source or widened road does not entirely fit |
| `unclosed_building` | Building way lacks the same first/last node ID |
| `self_intersection`, `backtracking_edge` | Crossing, nonadjacent contact, or retraced polygon edge |
| `degenerate_geometry`, `degenerate_triangle`, `triangulation_failed` | Insufficient or unusable geometry |
| `invalid_dimension`, `dimension_out_of_range` | Explicit dimension cannot be interpreted safely |
| `float32_precision_loss` | A triangle collapses, reverses, or its normal changes by more than 1% when stored as float32 |

## Dimensions and projection

The bbox is `(west, south, east, north)` in decimal degrees. Both latitude bounds
must lie within ±85°, west < east, south < north. Geographic width and height are
bounded by 5,000 m using spherical radius R=6,371,008.8 m and the maximum cosine
within the latitude interval. Antimeridian-crossing boxes are unsupported.

With the bbox midpoint `(lon0, lat0)` as origin and angles in radians:

```
x = R * (lon - lon0) * cos(lat0)
z = -R * (lat - lat0)
y = extrusion height (or road display elevation)
```

This is a local spherical equirectangular approximation, **not a survey CRS**.
No geoid, datum transformation, ellipsoidal distance correction, or terrain is
modeled. Projection parameters and axis names appear in the manifest. GLB uses
a right-handed, Y-up coordinate system in metres. All source tags are untrusted
text; their presence does not certify accuracy or imply consent to contact URLs.

Building height precedence:

1. `height` in plain decimal metres, optionally followed by ` m`, 0.1–600 m.
2. `building:levels`, decimal 1–200, multiplied by an assumed 3 m per level.
3. Default 9 m.

Levels may be fractional. Scientific notation, commas, semicolon lists, imperial
units, signs, and unsupported unit suffixes are rejected. Surrounding whitespace
is removed. An invalid preferred dimension omits the feature; lower-priority
tags do not rescue it. A valid `height` takes precedence over `building:levels`.
Roof tags are retained but not modeled. Even a pyramidal roof becomes a flat
extrusion at the selected total height. Levels-derived height ignores roof
levels/height and must be understood as an explicitly labeled approximation.

The presence of `building:part`, `ele`, or `incline` excludes a feature. Values
other than the exact defaults `bridge=no`, `tunnel=no`, `layer=0`, `min_height=0`,
`building:min_level=0`, and `location=surface` exclude it too. This intentionally
conservative string contract can omit equivalent values such as `layer=0.0`.

Road width is metric `width`, 0.1–50 m, or:

| Highway | Default metres |
| --- | ---: |
| motorway | 12 |
| trunk | 10 |
| primary | 8 |
| secondary | 7 |
| tertiary, residential, unclassified | 6 |
| service, living_street | 4 |
| pedestrian, track | 3 |
| cycleway | 2 |
| footway | 1.5 |
| path | 1 |

Other values, including link/steps/construction classes, are unsupported.
`area=yes` excludes a road. If a way has both an enabled `building` and a
`highway` tag, building interpretation takes precedence. Lane counts are not
used. Road centerline lengths are planar. A 2 cm display elevation avoids
coincident ground drawing; it is not a measured surface elevation.

## Geometry algorithm and numeric policy

Consecutive points separated by at most 1 micrometre are deduplicated. Buildings
remove the repeated closing coordinate and forward collinear vertices; they
reject nonadjacent touching, self-crossing, adjacent backtracking, and areas
below 0.0001 m². Geometric cross-product/contact tolerance is 1e-8 m² (coordinate
interval tolerance is 1e-8 m). These are implementation tolerances, not accuracy
claims. Ear clipping triangulates the simple polygon. Winding is canonicalized
in the XZ plane, starting at its lexicographically lowest point.

Bottom caps face −Y, top caps face +Y, and walls face outward. Closed extrusions
include the bottom. A road segment generates four vertices and two upward-facing
triangles. Each segment has a separate pair of butt ends; bent/self-crossing
roads can overlap or have gaps. They are not unioned, clipped, or stitched.
Normals in GLB are averaged across building corners, so downstream renderers may
show smooth edges. No UVs, images, textures, or external buffers are emitted.

Before export, each feature is checked for triangle collapse/reversal or greater
than 1% normal-vector change after float32 conversion; failing features are
omitted. This avoids accepting subprecision slivers far from the local origin.
Manifest measurements use the pre-storage double-precision geometry. Stored
GLB bounds reflect actual float32 coordinates. Small discrepancies are expected
and independently measured by verification.

## Output and reproducibility

Manifest schema version is `1`; incompatible interpretation changes require a
version change. `features[]` gives `id`, `kind`, integer `mesh`, original source
`tags`, ordered `source_node_ids`, `dimensions` with explicit source/inferred
flags, bounds in metres, vertex/triangle counts, and assumptions. `input` records
SHA-256 of **exact input bytes**, byte length, and element counts. `bbox`,
`projection`, and `limits` preserve conversion settings. `assets.scene.glb`
records the GLB SHA-256 and byte length. `diagnostics`, `omission_counts`, and
`totals` cover omissions and exported geometry.

Ways and relations are ordered by normalized numeric ID. JSON keys are sorted;
no current time, absolute path, random ID, or environment-specific metadata is
embedded. GLB arrays and chunk padding are deterministic. Vertex positions and
normals are little-endian float32; indices are unsigned 32-bit. There is one node
per mesh and one primitive per mesh. All buffer data is embedded. Empty inputs
export a valid empty scene and a usable empty inspector.

The preview embeds the same GLB as base64 and the manifest as serialized data.
It neither executes imported script nor inserts imported text through innerHTML.
Content Security Policy blocks network connections and remote scripts/images.
This is a local inspector, not a server or deployed website.

## Hard limits and lifecycle

| Resource | Default ceiling |
| --- | ---: |
| Input bytes | 8 MiB |
| Nodes | 50,000 |
| Ways / relations | 5,000 each |
| Node references per way (including closure) | 256 |
| Members per relation | 1,000 |
| Tags per element | 128 |
| Attributes per XML element | 32 |
| Attribute key / value length | 128 / 2,048 characters |
| XML nesting | 3 element levels |
| Total exported vertices / triangles | 100,000 each |
| Geographic extent | 5,000 m per side |
| Wall-clock budget | 30 s |
| Each output file | 10 MiB |
| Sum of output files | 24 MiB |

CLI limits are fixed. The Python API exposes `Limits` for trusted callers and
low-cap tests. Any global limit error rejects the conversion rather than
silently truncating features. This bounds ordinary workloads, but the process
has no independent RSS limit. Input memory, parse objects, geometry, and serialized
buffers can coexist. Runtime checks occur during parsing, feature processing,
and writing. Unix CLI SIGALRM also covers long native/file operations; other
Python API calls use cooperative deadlines, not a hard preemption guarantee.

All serialization/size checks happen before output creation. The output directory
is reserved with exclusive mkdir. Existing files/directories and dangling
symlinks are never overwritten. After reservation, any handled exception,
KeyboardInterrupt, or CLI SIGTERM removes the owned partial directory. Success
leaves exactly the six output files. The directory is visible while writing;
this is not an atomic directory publication. A parent that does not exist is an
error. Exit codes: 0 success (including an empty scene), 2 input/output/runtime
error, 130 cancellation. SIGKILL/power failure are not recoverable; inspect and
remove an abandoned new output directory before retrying. Do not concurrently
modify another process's output directory.
