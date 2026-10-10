'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const {manifest, glb} = FORGE_DATA;
  const canvas = $('scene'), ctx = canvas.getContext('2d');
  // Decode the exported GLB, not an independently generated preview mesh.
  const bytes = Uint8Array.from(atob(glb), c => c.charCodeAt(0));
  const data = new DataView(bytes.buffer);
  if (data.getUint32(0, true) !== 0x46546c67) throw new Error('Invalid GLB');
  const jsonLength = data.getUint32(12, true);
  const doc = JSON.parse(new TextDecoder().decode(bytes.slice(20, 20 + jsonLength)));
  const binaryStart = 28 + jsonLength;
  function accessor(index) {
    const a = doc.accessors[index], v = doc.bufferViews[a.bufferView];
    const offset = binaryStart + (v.byteOffset || 0) + (a.byteOffset || 0);
    const count = a.count * (a.type === 'VEC3' ? 3 : 1);
    return Array.from({length: count}, (_, i) => a.componentType === 5126 ? data.getFloat32(offset + i * 4, true) : data.getUint32(offset + i * 4, true));
  }
  const meshes = (doc.meshes || []).map(mesh => {
    const primitive = mesh.primitives[0], flat = accessor(primitive.attributes.POSITION);
    return {vertices: Array.from({length: flat.length / 3}, (_, i) => flat.slice(i * 3, i * 3 + 3)), indices: accessor(primitive.indices)};
  });
  const all = meshes.flatMap(m => m.vertices);
  let min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
  for (const p of all) for (let j = 0; j < 3; j++) {min[j] = Math.min(min[j], p[j]); max[j] = Math.max(max[j], p[j]);}
  if (!all.length) {min = [-10, 0, -10]; max = [10, 1, 10];}
  const center = min.map((v, i) => (v + max[i]) / 2);
  const extent = Math.max(...max.map((v, i) => v - min[i]), 10);
  let yaw = -.55, tilt = .70, zoom = 1, selected = -1, painted = [];
  const rows = [];
  function select(index) {
    if (!manifest.features.length) return;
    selected = (index + manifest.features.length) % manifest.features.length;
    const f = manifest.features[selected];
    $('selection').textContent = `${f.id} · ${f.kind}${f.tags.name ? ' · ' + f.tags.name : ''}`;
    $('details').textContent = JSON.stringify({id: f.id, dimensions: f.dimensions, assumptions: f.assumptions, source_tags: f.tags, source_node_ids: f.source_node_ids, bounds_m: f.bounds_m}, null, 2);
    rows.forEach((r, i) => r.button.setAttribute('aria-pressed', String(i === selected)));
    draw();
  }
  manifest.features.forEach((f, i) => {
    const tr = document.createElement('tr'), td = document.createElement('td'), button = document.createElement('button');
    button.textContent = f.id; button.setAttribute('aria-pressed', 'false');
    button.addEventListener('click', () => select(i)); td.append(button); tr.append(td);
    const d = f.dimensions;
    for (const text of [f.tags.name || '—', f.kind, f.kind === 'building' ? `${d.height_m} m high` : `${d.width_m} m wide`, d.height_source || d.width_source]) {
      const cell = document.createElement('td'); cell.textContent = text; tr.append(cell);
    }
    $('features').append(tr); rows.push({tr, button, text: `${f.id} ${f.tags.name || ''} ${f.kind}`.toLowerCase()});
  });
  $('filter').addEventListener('input', () => rows.forEach(r => {r.tr.hidden = !r.text.includes($('filter').value.toLowerCase());}));
  $('summary').textContent = `${meshes.length} features / ${manifest.totals.triangles.toLocaleString()} triangles`;
  $('attribution').textContent = manifest.attribution;
  $('provenance').textContent = JSON.stringify({input: manifest.input, projection: manifest.projection, bbox: manifest.bbox, limits: manifest.limits, assets: manifest.assets}, null, 2);
  $('omission-summary').textContent = `${manifest.diagnostics.length} omitted source features`;
  $('omissions').textContent = JSON.stringify({counts: manifest.omission_counts, diagnostics: manifest.diagnostics}, null, 2);
  function draw() {
    const width = canvas.clientWidth, height = canvas.clientHeight, ratio = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.fillStyle = '#d4dfdc'; ctx.fillRect(0, 0, width, height);
    const scale = Math.min(width, height) * .7 / extent * zoom;
    const cy = Math.cos(yaw), sy = Math.sin(yaw), ct = Math.cos(tilt), st = Math.sin(tilt);
    function project(p) {
      const x = p[0] - center[0], y = p[1] - center[1], z = p[2] - center[2];
      const u = x * cy - z * sy, v = x * sy + z * cy;
      return [width / 2 + u * scale, height / 2 + (v * st - y * ct) * scale, v * ct + y * st];
    }
    ctx.strokeStyle = '#b6c7c1'; ctx.lineWidth = 1;
    for (let i = -5; i <= 5; i++) {
      for (const pair of [[[center[0] + i * extent / 5, 0, center[2] - extent], [center[0] + i * extent / 5, 0, center[2] + extent]], [[center[0] - extent, 0, center[2] + i * extent / 5], [center[0] + extent, 0, center[2] + i * extent / 5]]]) {
        const [a, b] = pair.map(project); ctx.beginPath(); ctx.moveTo(...a.slice(0,2)); ctx.lineTo(...b.slice(0,2)); ctx.stroke();
      }
    }
    painted = [];
    meshes.forEach((mesh, mi) => {
      const projected = mesh.vertices.map(project);
      for (let j = 0; j < mesh.indices.length; j += 3) {
        const p = mesh.indices.slice(j,j+3).map(i => projected[i]);
        painted.push({p, mi, depth: p.reduce((a, v) => a + v[2], 0) / 3});
      }
    });
    painted.sort((a, b) => a.depth - b.depth);
    for (const {p, mi} of painted) {
      ctx.beginPath(); ctx.moveTo(p[0][0],p[0][1]); ctx.lineTo(p[1][0],p[1][1]); ctx.lineTo(p[2][0],p[2][1]); ctx.closePath();
      const road = manifest.features[mi].kind === 'road';
      ctx.fillStyle = mi === selected ? '#edb75b' : road ? '#53666c' : '#8daa94';
      ctx.fill(); ctx.strokeStyle = mi === selected ? '#956922' : road ? '#53666c' : '#617d69'; ctx.lineWidth = .45; ctx.stroke();
    }
    ctx.fillStyle = '#273e38'; ctx.font = '12px system-ui';
    ctx.fillText(all.length ? 'Y up · metric scene · flat terrain' : 'No supported features in this extent', 16, 24);
    const north = project([center[0], center[1], center[2] - extent / 5]);
    const origin = project(center);
    // A fixed-size compass follows the camera even for kilometre-wide scenes.
    const northLength = Math.hypot(north[0]-origin[0], north[1]-origin[1]);
    const nx = (north[0]-origin[0]) / northLength, ny = (north[1]-origin[1]) / northLength;
    ctx.beginPath(); ctx.moveTo(38, height - 36); ctx.lineTo(38 + nx*22, height - 36 + ny*22); ctx.strokeStyle = '#273e38'; ctx.lineWidth = 2; ctx.stroke();
    ctx.fillText('N', 34 + nx*30, height - 32 + ny*30);
    $('camera').textContent = `Orbit ${Math.round(yaw * 180 / Math.PI)}° · elevation ${Math.round(tilt * 180 / Math.PI)}° · zoom ${zoom.toFixed(2)}×`;
    canvas.dataset.rendered = 'true'; canvas.dataset.triangles = String(painted.length);
  }
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  function move(dyaw = 0, dz = 1, dt = 0) {yaw += dyaw; zoom = clamp(zoom * dz, .2, 10); tilt = clamp(tilt + dt, .26, 1.48); $('tilt').value = String(Math.round(tilt * 180 / Math.PI)); draw();}
  function reset() {yaw = -.55; tilt = .70; zoom = 1; move();}
  $('left').onclick = () => move(-.2); $('right').onclick = () => move(.2);
  $('in').onclick = () => move(0, 1.2); $('out').onclick = () => move(0, 1/1.2); $('reset').onclick = reset;
  $('tilt').oninput = () => {tilt = Number($('tilt').value) * Math.PI / 180; draw();};
  canvas.addEventListener('keydown', e => {
    const actions = {ArrowLeft: () => move(-.15), ArrowRight: () => move(.15), ArrowUp: () => move(0,1,.08), ArrowDown: () => move(0,1,-.08), PageUp: () => move(0,1,.08), PageDown: () => move(0,1,-.08), '+': () => move(0,1.2), '=': () => move(0,1.2), '-': () => move(0,1/1.2), Home: reset, ']': () => select(selected+1), '[': () => select(selected-1)};
    if (actions[e.key]) {e.preventDefault(); actions[e.key]();}
  });
  canvas.addEventListener('wheel', e => {e.preventDefault(); move(0, Math.exp(-e.deltaY * .001));}, {passive: false});
  let drag = null;
  canvas.addEventListener('pointerdown', e => {canvas.focus(); canvas.setPointerCapture(e.pointerId); drag = {x:e.clientX, y:e.clientY, moved:false};});
  canvas.addEventListener('pointermove', e => {if (!drag) return; const dx = e.clientX-drag.x, dy = e.clientY-drag.y; if (Math.abs(dx)+Math.abs(dy)>2) drag.moved=true; if (drag.moved) move(dx*.008,1,dy*.006); drag.x=e.clientX; drag.y=e.clientY;});
  canvas.addEventListener('pointercancel', () => {drag = null;});
  canvas.addEventListener('pointerup', e => {
    if (drag && !drag.moved) {
      const box = canvas.getBoundingClientRect(), x = e.clientX-box.left, y = e.clientY-box.top;
      for (let i = painted.length-1; i >= 0; i--) {
        const {p, mi} = painted[i];
        const signs = p.map((a, j) => {const b=p[(j+1)%3]; return (b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0]);});
        if (signs.every(v => v>=0) || signs.every(v => v<=0)) {select(mi); break;}
      }
    }
    drag=null;
  });
  new ResizeObserver(draw).observe(canvas); draw();
})();
