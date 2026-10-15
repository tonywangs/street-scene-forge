'use strict';
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

(async () => {
  const [directory, reportFile, mode = 'synthetic'] = process.argv.slice(2);
  if (!directory || !reportFile) throw new Error('usage: node scripts/browser_check.cjs scene-directory report.json [synthetic|real|empty|bounded]');
  const browser = await chromium.launch({headless: true, args: ['--no-sandbox'], ...(process.env.FORGE_CHROMIUM ? {executablePath: process.env.FORGE_CHROMIUM} : {})});
  const errors = [], externalAttempts = [], checks = [], violations = [];
  try {
    const context = await browser.newContext({viewport: {width: 1280, height: 960}, offline: true, serviceWorkers: 'block'});
    await context.route('**/*', route => {
      const url = route.request().url();
      if (/^https?:|^wss?:/i.test(url)) {externalAttempts.push(url); return route.abort('internetdisconnected');}
      return route.continue();
    });
    await context.addInitScript(() => {
      window.CSP_VIOLATIONS = [];
      document.addEventListener('securitypolicyviolation', e => window.CSP_VIOLATIONS.push(e.violatedDirective));
    });
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(String(e)));
    page.on('request', request => {if (/^https?:|^wss?:/i.test(request.url())) externalAttempts.push(request.url());});
    const start = performance.now();
    await page.goto(pathToFileURL(path.join(path.resolve(directory), 'index.html')).href);
    await page.locator('#scene[data-rendered="true"]').waitFor();
    const loadMs = performance.now() - start;
    const manifest = JSON.parse(fs.readFileSync(path.join(directory, 'manifest.json'), 'utf8'));
    assert.equal(await page.locator('#features tr').count(), manifest.features.length);
    assert.equal(Number(await page.locator('#scene').getAttribute('data-triangles')), manifest.totals.triangles);
    checks.push('file:// load with browser offline and external requests blocked', 'GLB triangle count and accessible table correspondence');
    const initialCamera = await page.locator('#camera').textContent();
    const initialImage = await page.locator('#scene').screenshot();
    await page.getByRole('button', {name: 'Rotate right', exact: true}).click();
    assert.notEqual(await page.locator('#camera').textContent(), initialCamera);
    assert.notDeepEqual(await page.locator('#scene').screenshot(), initialImage);
    await page.getByRole('button', {name: 'Zoom in', exact: true}).click();
    assert.match(await page.locator('#camera').textContent(), /1\.20/);
    await page.getByRole('button', {name: 'Reset view', exact: true}).click();
    assert.equal(await page.locator('#camera').textContent(), initialCamera);
    checks.push('camera controls change rendered pixels and reset');
    const canvas = page.locator('#scene');
    await canvas.focus();
    await page.keyboard.press('ArrowLeft'); await page.keyboard.press('PageUp'); await page.keyboard.press('+');
    assert.notEqual(await page.locator('#camera').textContent(), initialCamera);
    await page.keyboard.press('Home');
    assert.equal(await page.locator('#camera').textContent(), initialCamera);
    const box = await canvas.boundingBox();
    await page.mouse.move(box.x+box.width/2, box.y+box.height/2);
    await page.mouse.down(); await page.mouse.move(box.x+box.width/2+60, box.y+box.height/2+20, {steps: 5}); await page.mouse.up();
    assert.notEqual(await page.locator('#camera').textContent(), initialCamera);
    await page.mouse.wheel(0, -100);
    await page.getByRole('button', {name: 'Reset view', exact: true}).click();
    checks.push('keyboard orbit, tilt, zoom, reset; pointer drag and wheel');
    if (manifest.features.length) {
      await canvas.focus(); await page.keyboard.press(']');
      assert.match(await page.locator('#selection').textContent(), new RegExp(manifest.features[0].id));
      await page.keyboard.press(']');
      const second = manifest.features[Math.min(1, manifest.features.length-1)];
      assert.match(await page.locator('#selection').textContent(), new RegExp(second.id));
      const firstButton = page.getByRole('button', {name: manifest.features[0].id, exact: true});
      await firstButton.focus(); await page.keyboard.press('Enter');
      assert.match(await page.locator('#details').textContent(), /source_node_ids/);
      assert.equal(await firstButton.getAttribute('aria-pressed'), 'true');
      await page.keyboard.press('Tab');
      if (manifest.features.length > 1) assert.equal(await page.evaluate(() => document.activeElement.textContent), manifest.features[1].id);
      checks.push('keyboard feature cycling, table Enter selection and Tab navigation');
    }
    if (mode === 'synthetic') {
      await page.getByRole('button', {name: 'way/103', exact: true}).click();
      assert.match(await page.locator('#details').textContent(), /<\/script><img/);
      assert.match(await page.locator('#details').textContent(), /"__proto__": "inert source tag"/);
      assert.equal(await page.locator('img').count(), 0);
      assert.equal(await page.evaluate(() => window.HOSTILE), undefined);
      await page.locator('#filter').fill('workshop');
      assert.equal(await page.locator('#features tr:visible').count(), 1);
      await page.locator('#filter').fill('');
      // Click the center of the tallest roof using the documented projection.
      const f = manifest.features.find(f => f.id === 'way/102');
      const bounds = manifest.features.map(f => f.bounds_m);
      const min = [0,1,2].map(i => Math.min(...bounds.map(b => b.min[i])));
      const max = [0,1,2].map(i => Math.max(...bounds.map(b => b.max[i])));
      const center = min.map((v,i) => (v+max[i])/2), extent = Math.max(...max.map((v,i)=>v-min[i]),10);
      const p = [(f.bounds_m.min[0]+f.bounds_m.max[0])/2, f.bounds_m.max[1], (f.bounds_m.min[2]+f.bounds_m.max[2])/2];
      const x=p[0]-center[0], y=p[1]-center[1], z=p[2]-center[2], yaw=-.55, tilt=.70;
      const scale=Math.min(box.width,box.height)*.7/extent;
      await canvas.scrollIntoViewIfNeeded();
      await canvas.click({position: {x:box.width/2+(x*Math.cos(yaw)-z*Math.sin(yaw))*scale,y:box.height/2+((x*Math.sin(yaw)+z*Math.cos(yaw))*Math.sin(tilt)-y*Math.cos(tilt))*scale}});
      assert.match(await page.locator('#selection').textContent(), /way\/102/);
      checks.push('hostile imported HTML displayed only as text', 'table filter', 'canvas triangle picking selects roof feature');
    }
    if (mode === 'courtyard') {
      await page.getByRole('button', {name: 'relation/900', exact: true}).click();
      const details = await page.locator('#details').textContent();
      assert.match(details, /source_members/); assert.match(details, /member_way_ids/);
      assert.match(details, /"role": "inner"/); assert.match(details, /<\/script><img/);
      assert.equal(await page.locator('img').count(), 0);
      assert.equal(await page.evaluate(() => window.HOSTILE), undefined);
      await page.locator('#tilt').evaluate(e => {e.value='85';e.dispatchEvent(new Event('input'));});
      // Screen samples follow the documented projection of the explicit synthetic
      // roof (-40,7,0) and courtyard floor (0,0,0), independently of triangles.
      const samples = await canvas.evaluate(c => {
        const scale=Math.min(c.clientWidth,c.clientHeight)*.7/100;
        const yaw=-.55, tilt=85*Math.PI/180;
        const project=(x,y,z)=>[c.clientWidth/2+(x*Math.cos(yaw)-z*Math.sin(yaw))*scale,
          c.clientHeight/2+((x*Math.sin(yaw)+z*Math.cos(yaw))*Math.sin(tilt)-(y-3.5)*Math.cos(tilt))*scale];
        const roof=project(-40,7,0),hole=project(0,0,0);
        const pixel=p=>Array.from(c.getContext('2d').getImageData(Math.round(p[0]*c.width/c.clientWidth),Math.round(p[1]*c.height/c.clientHeight),1,1).data).slice(0,3);
        return {roof,hole,roofPixel:pixel(roof),holePixel:pixel(hole)};
      });
      assert.deepEqual(samples.roofPixel,[237,183,91]);
      assert.notDeepEqual(samples.holePixel,[237,183,91]);
      assert.ok([[212,223,220],[182,199,193]].some(c=>c.every((v,i)=>Math.abs(v-samples.holePixel[i])<=3)), JSON.stringify(samples));
      // Reset selection so both hit and miss checks can actually fail.
      await page.reload(); await page.locator('#scene[data-rendered="true"]').waitFor();
      await page.locator('#tilt').evaluate(e => {e.value='85';e.dispatchEvent(new Event('input'));});
      await canvas.click({position:{x:samples.hole[0],y:samples.hole[1]}});
      assert.match(await page.locator('#selection').textContent(), /Choose a feature/);
      await canvas.click({position:{x:samples.roof[0],y:samples.roof[1]}});
      assert.match(await page.locator('#selection').textContent(), /relation\/900/);
      await page.locator('#omission-summary').focus(); await page.keyboard.press('Enter');
      assert.equal(await page.locator('#omissions').isVisible(), true);
      assert.match(await page.locator('#omissions').textContent(), /unsupported_relation/);
      assert.match(await page.locator('#omissions').textContent(), /consumed_relation_member/);
      checks.push('courtyard ground pixels remain visible through roof and bottom', 'canvas relation picking and courtyard miss from empty selection',
        'relation and member provenance; consumed-member and unsupported diagnostics', 'hostile relation text remains inert');
    }
    await page.getByText('Input fingerprint, projection & limits', {exact:true}).click();
    assert.match(await page.locator('#provenance').textContent(), new RegExp(manifest.input.sha256));
    checks.push('source fingerprint and dimensions visible');
    await page.screenshot({path: reportFile.replace(/\.json$/, '.png'), fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    checks.push('mobile viewport has no page overflow');
    violations.push(...await page.evaluate(() => window.CSP_VIOLATIONS));
    assert.deepEqual(errors, []); assert.deepEqual(externalAttempts, []); assert.deepEqual(violations, []);
    const report={browser: await browser.version(),playwright:require('playwright/package.json').version,mode,load_ms:loadMs,features:manifest.features.length,triangles:manifest.totals.triangles,external_attempts:externalAttempts,page_errors:errors,csp_violations:violations,checks};
    fs.writeFileSync(reportFile, JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify(report));
  } finally {await browser.close();}
})().catch(error => {console.error(error);process.exitCode=1;});
