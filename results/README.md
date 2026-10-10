# Reproducible verification evidence

This directory contains actual test/validator/browser output, screenshots, and
measurements from `python3 scripts/verify.py` on 2026-10-10. Rerunning verification
replaces the machine evidence; use `--results /tmp/forge-verification` to preserve it.

## Coverage and observed results

- **27 test methods passed**, including 240 seeded concave building/narrow-road
  pairs (seed 20261010), 80 seeded self-intersection/missing-node pairs (71023),
  and 64 seeded exact-boundary/outside-boundary/road-width groups (88173).
- Independent GLB decoding checks finite coordinates, valid triangle indices,
  nondegenerate faces, normalized normals, matching accessor bounds, positive
  signed extrusion volume, outward cap winding, closed directed-edge pairing,
  footprint area, known seeded analytic areas, triangle-centroid containment,
  dimensions, and feature-to-mesh IDs/counts. The reader does not import the
  converter's geometry helpers.
- Contract/lifecycle cases include duplicate/collinear/reversed points, explicit
  dimension precedence, unsupported map structures, malformed XML and external
  entities, invalid coordinates, all major resource ceilings, output collisions,
  serialization/write faults, FIFO rejection, float32 collapse, actual SIGTERM,
  KeyboardInterrupt, deadline expiry during writing, and cleanup.
- All four saved Khronos reports have **0 errors, 0 warnings, 0 infos, 0 hints**.
  Full reports are retained; the verifier fails on errors and preserves warnings.
- Every artifact was byte-identical across two exports of each workload, and
  each input hash remained unchanged. Installed CLI collision checks returned
  exit code 2 and preserved the original output. The converter ran outside the
  checkout from the installed zipapp. A tested Python audit hook rejected socket
  creation; no socket operation was attempted during conversion.
- All four Chromium runs loaded directly through `file://` with browser offline
  mode enabled, service workers blocked, and external network requests aborted.
  Tests exercise loading, camera buttons/drag/wheel/keyboard controls, rendered
  pixel changes, feature selection, source details, keyboard table activation and
  tabbing, fingerprint display, and mobile layout. The synthetic test also
  exercises canvas roof picking, filtering, and hostile imported HTML text.
  **No page errors, external requests, or CSP violations were observed.**

## Bounded measurements

These are **single-run measurements, not a comparative benchmark**. CLI wall time
includes process launch; peak process RSS comes from GNU `/usr/bin/time` on Linux.
Browser load time is navigation through the first completed canvas render,
including local resource loading. Hardware/process contention was not controlled.

| Input | Features / triangles | CLI wall time (s) | Peak RSS (KiB) | GLB bytes | Browser load (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Synthetic fixture | 5 / 50 | 0.186 | 20,608 | 5,228 | 321.3 |
| Six real OSM ways | 6 / 310 | 0.223 | 20,788 | 12,912 | 337.0 |
| Synthetic grid | 1,000 / 12,000 | 0.745 | 37,208 | 946,512 | 1,016.6 |
| Empty OSM | 0 / 0 | 0.206 | 20,608 | 112 | 417.1 |

For unrounded values, each artifact's size/hash, input fingerprints, projection
readback discrepancies, and socket audit results, see
[`verification.json`](verification.json). Detailed load results and screenshots
are in `*-browser.json` and `*-browser.png`. GLB format reports are
`*-validator.json`. Unit output is [`tests.log`](tests.log).

The largest observed dimensional readback difference was approximately
**0.000008791 m** on the real fixture. This measures float32 storage roundoff
against this converter's own geometry, **not real-world map accuracy**.

Versions: Python 3.12.3, Node v24.20.0, glTF Validator 2.0.0-dev.3.10,
Playwright 1.64.0, Chromium 156.0.8078.4. Exact platform and npm lock hash are in
the machine report. Conversion/preview have no third-party runtime dependencies.

## Negative findings and limits of these checks

A very thin footprint, about 10 micrometres wide and 100 m long, located about
1 km from the origin, passed double-precision geometry construction but collapsed
in float32 GLB storage. Independent readback detected the degenerate geometry.
The converter now reports `float32_precision_loss` and omits it, with a regression
test. This is an intentional conservative omission, not repaired source geometry.

An initial area request exceeded the acquisition cap and was discarded. The real
fixture instead uses six explicit way/full requests; it makes no area-completeness
claim. One early test assertion demanded exact equality for a computed area and
failed on `100.00000000000004` versus `100`; the corrected assertion uses an
absolute numeric tolerance. Neither event is hidden as a successful trial.

These checks do not prove correctness for all polygons, OSM tag combinations,
platforms, or malicious local filesystem races. The 1,000-building input is
below the configured ceiling, not a worst-case resource test. The preview's
painter ordering may be inaccurate for intersecting surfaces. No game-engine,
physical-world, human-usability, formal accessibility, cross-platform byte
identity, or non-Chromium-browser validation was performed. No OSM2World accuracy
or performance comparison was run.
