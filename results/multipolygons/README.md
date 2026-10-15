# Multipolygon validation evidence

Recorded on Linux with Python 3.12.3, Node v24.20.0, Shapely 2.1.2 / GEOS 3.13.1, NumPy 2.2.6, Playwright 1.64.0 and Chromium 156.0.8078.4. Khronos glTF Validator is pinned at 2.0.0-dev.3.10. Exact dependency and triangulator hashes are in `verification.json`.

43 unit tests passed, including 250 seeded valid multipolygon comparisons, 64 seeded invalid relations, 32 exact-boundary groups, and the retained 384 simple-building/road case groups. Relation tests cover fragmented/reversed/reordered members, concavity, two courtyards, disconnected outers, invalid contacts/nesting, missing/duplicate/shared references, resource limits, serialization failures, real SIGTERM, timeout, cancellation cleanup, output collisions and unchanged input bytes.

All ten installed-CLI workloads passed independent GLB readback, Khronos validation, byte-identical repeated output and offline Chromium checks. Existing four workload GLBs match their historical SHA-256 values exactly. The installed zipapp ran from a temporary working directory with a socket-denying audit hook. Browser networking was disabled and external attempts were blocked and recorded. The courtyard browser check was strengthened and rerun on an isolated installed output whose six artifact hashes matched the full-run report: selecting through the hole leaves selection empty, while clicking the roof selects the relation.

| Workload | Features | Vertices | Triangles | Wall seconds | Peak RSS KiB | GLB bytes | All output bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| bounded | 1000 | 8000 | 12000 | 0.829 | 38832 | 946512 | 3226456 |
| courtyard | 1 | 16 | 32 | 0.244 | 21396 | 1844 | 28640 |
| empty | 0 | 0 | 0 | 0.299 | 21244 | 112 | 18162 |
| real | 6 | 194 | 310 | 0.262 | 21572 | 12912 | 58958 |
| relations-bounded | 100 | 1600 | 3200 | 0.494 | 26868 | 144764 | 1005240 |
| synthetic | 5 | 40 | 50 | 0.239 | 21376 | 5228 | 37193 |
| upstream-mp_two_holes | 1 | 26 | 56 | 0.225 | 21176 | 2428 | 27736 |
| upstream-mp_two_holes_advanced | 1 | 26 | 56 | 0.397 | 21240 | 2428 | 28584 |
| upstream-mp_two_holes_outer_tagged | 0 | 0 | 0 | 0.291 | 21208 | 112 | 19448 |
| upstream-mp_two_holes_touching_inners | 0 | 0 | 0 | 0.278 | 21236 | 112 | 19850 |

These are single bounded observations, not performance distributions. Wall time includes process launch; peak RSS is GNU time’s converter-process measurement, not browser or total-run memory. Asset sizes/hashes and browser load measurements are preserved in JSON. The two upstream rejection fixtures intentionally export empty valid GLBs.

## Negative result and repair

Raw Earcut output is not sufficient for watertight solids. The aligned-hole case reproduced by `python3 scripts/triangulation_probe.py` returns one near-zero-area bridge triangle. The initial strict implementation therefore rejected valid inputs. Removing that face alone can leave T-junctions; the final cap repair splits edges at existing vertices without changing coordinates, then enforces directed-edge topology, positive triangles and area. The same case now exports successfully and the independent GEOS tests pass. `triangulation-probe.json` preserves the measured before/after counts. The vendored port also required explicit integer conversion in the greater-than-80-vertex z-order path; the 120-vertex test exercises that branch.

## Reproduce and interpret

After the setup documented in the root README, run:

```sh
PYTHONPATH=/tmp/forge-validation-deps python3 scripts/verify.py --results /tmp/forge-verification
python3 scripts/triangulation_probe.py
python3 scripts/check_tree.py
```

The fixture corpus consists of four pinned upstream handcrafted regression files, not representative OSM map coverage. GEOS expectations use independent source polygons and exported float32 triangles; mesh readback separately checks area, signed volume, bounds, directed-edge pairing, normals, winding and feature IDs. This is bounded evidence, not a proof for every OSM polygon. Touching/nested rings, old-style outer tag inheritance and complex building relations remain unsupported. Dimensions and terrain are approximate; there was no game-engine import, physical-world comparison, human usability study, screen-reader audit, non-Chromium browser or non-Linux validation.

Original results in the parent directory are unchanged. This directory contains reproducible validation evidence only.
