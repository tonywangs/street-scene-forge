# Existing work and primary sources

Reviewed 2026-10-10. No claim of novel map-to-3D conversion is made. No upstream
implementation was benchmarked, and no OSM2World code was copied.

- [OSM2World project](https://osm2world.org/) and
  [implementation repository](https://github.com/tordanik/OSM2World): established
  conversion with broader map semantics and multiple 3D output formats. This
  project chooses a much narrower offline input contract for auditable output.
- [OSM2World BuildingModule](https://github.com/tordanik/OSM2World/blob/master/core/src/main/java/org/osm2world/world/modules/building/BuildingModule.java):
  handles building multipolygon relations and avoids rendering their component
  areas independently. This reinforces the need to exclude unsupported relation
  members here, rather than pretending each outer way is a complete building.
- [OSM XML](https://wiki.openstreetmap.org/wiki/OSM_XML): nodes, references, ways,
  and relations; IDs/order/tags cannot be assumed from a tidy example alone.
  This tool deliberately accepts a bounded subset, not all historical formats.
- [OSM height](https://wiki.openstreetmap.org/wiki/Key:height),
  [levels](https://wiki.openstreetmap.org/wiki/Key:building:levels), and
  [width](https://wiki.openstreetmap.org/wiki/Key:width): metre defaults and tagging
  semantics. The 3 m-per-level conversion and per-road-class widths are **local
  project assumptions**, not claims that OSM defines those physical values.
- [glTF 2.0 specification](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html):
  GLB container/chunk layout, buffer views/accessors, indexed triangles, metre
  units, Y-up coordinates, materials, and accessor bounds.
- [Khronos glTF Validator](https://github.com/KhronosGroup/glTF-Validator): the
  independent format checker, pinned through npm and the lockfile. A valid GLB
  does not establish physical-world accuracy or correct OSM interpretation.
- [OSM copyright/attribution](https://www.openstreetmap.org/copyright) and
  [ODbL 1.0 terms](https://opendatacommons.org/licenses/odbl/1-0/): the real fixture
  retains OSM attribution and its separate data license. Acquisition is an
  explicit online helper; offline conversion never contacts these sources.

## Multipolygon review (2026-10-15)

- [OSM multipolygon specification](https://wiki.openstreetmap.org/wiki/Relation:multipolygon):
  relation-level tags describe the area; ways with `outer` and `inner` roles form
  rings and may be fragmented. OSM permits some touching inner configurations;
  this converter deliberately rejects all boundary contact. Legacy outer-way
  tag inheritance is also outside its conservative contract.
- [OSM2World ring assembly](https://github.com/tordanik/OSM2World/blob/f6518b35117cf7864e9c6f68c3b303a006e27b8f/core/src/main/java/org/osm2world/map_data/creation/MultipolygonAreaBuilder.java)
  handles closed and fragmented ways, multiple areas, and some touching holes.
  Its simple path can inherit outer tags. We instead require degree-two endpoint
  graphs, explicit roles and relation building tags, and reject ambiguity.
- [OSM2World Earcut integration](https://github.com/tordanik/OSM2World/blob/f6518b35117cf7864e9c6f68c3b303a006e27b8f/core/src/main/java/org/osm2world/math/algorithms/Earcut4JTriangulationUtil.java)
  flattens outer and hole vertices into an indexed triangulation. This informed
  the input layout; no Java implementation code was copied. Four MIT-licensed
  upstream test fixtures are now redistributed with their license and hashes.
- [Mapbox Earcut](https://github.com/mapbox/earcut) explicitly does not guarantee
  arbitrary-input correctness or conforming meshes. The
  [Python port](https://github.com/joshuaskelly/earcut-python/tree/c0d27600d5423d06686eeeb5e24c5f43595c7c1d)
  is vendored with ISC attribution, a documented integer-conversion fix, and
  exact upstream/local hashes. This avoids a converter runtime dependency.
- [Shapely 2.1.2](https://shapely.readthedocs.io/en/2.1.2/) supplies GEOS polygon
  union, difference and containment as a separate verification implementation.
  It is never imported by conversion or installed zipapps. The tests compare
  exported float32 triangles with the independently constructed source polygon,
  rather than merely trusting manifest area.

No claim of novel triangulation, representative OSM coverage, or superiority to
OSM2World follows from this bounded experiment.
