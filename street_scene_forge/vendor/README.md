# Vendored triangulator

`earcut.py` comes from [joshuaskelly/earcut-python](https://github.com/joshuaskelly/earcut-python),
revision `c0d27600d5423d06686eeeb5e24c5f43595c7c1d`, path `earcut/earcut.py`.
ISC license: `LICENSE.earcut` (included in installed zipapps).

Local change: explicitly convert the two z-order coordinates to `int`; Python
floor division of floating coordinates otherwise returns floats and bit shifts
fail above the 80-vertex hashing threshold. No other vendor algorithm edits.
Production `relations.py` validates inputs, repairs nonconforming caps without
moving vertices, and checks directed edges, area and float32 geometry separately.
The original simple-way triangulator remains unchanged.
