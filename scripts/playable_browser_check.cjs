'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');
(async()=>{
  const [directory,resultDirectory]=process.argv.slice(2);
  if(!directory||!resultDirectory) throw Error('usage: scene-directory result-directory');
  fs.mkdirSync(resultDirectory,{recursive:true});
  const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
  const errors=[],requests=[];
  try {
    const context=await browser.newContext({viewport:{width:1440,height:1050},offline:true,serviceWorkers:'block'});
    await context.route('**/*',route=>{if(/^https?:/.test(route.request().url())){requests.push(route.request().url());return route.abort();}return route.continue();});
    const page=await context.newPage();page.on('pageerror',e=>errors.push(String(e)));
    await page.addInitScript(()=>{window.walkTrace=[];function sample(){if(window.FORGE_WALK?.walking)window.walkTrace.push(window.FORGE_WALK.state.position);requestAnimationFrame(sample);}requestAnimationFrame(sample);window.violations=[];document.addEventListener('securitypolicyviolation',e=>window.violations.push(e.violatedDirective));});
    await page.goto(pathToFileURL(path.resolve(directory,'index.html')).href+'?walk=1');
    await page.waitForFunction(()=>window.FORGE_WALK?.walking);
    const state=()=>page.evaluate(()=>window.FORGE_WALK.state);
    const route=await page.evaluate(()=>window.FORGE_WALK.route);
    assert(route,'real scene must offer a free route');
    assert(route.length>50);
    const start=await state();
    assert.match(await page.locator('#source-record').textContent(),/2026-10-19/);
    assert.match(await page.locator('#attribution').textContent(),/OpenStreetMap contributors/);
    await page.screenshot({path:path.join(resultDirectory,'berlin-start.png')});
    // Steer solely through the visible canvas pointer and keyboard interfaces.
    async function faceRight(target) {
      const p=(await state()).position;
      const desired=Math.atan2(-(target[1]-p[1]),target[0]-p[0]);
      const current=await page.evaluate(()=>window.FORGE_WALK.yaw);
      let delta=desired-current;delta=Math.atan2(Math.sin(delta),Math.cos(delta));
      const box=await page.locator('#scene').boundingBox();
      await page.mouse.move(box.x+box.width/2,box.y+box.height/2);
      await page.mouse.down();await page.mouse.move(box.x+box.width/2+delta/.008,box.y+box.height/2,{steps:5});await page.mouse.up();
      await page.locator('#scene').focus();
    }
    await faceRight(route.end);await page.keyboard.down('d');
    await page.waitForFunction(()=>window.FORGE_WALK.state.reached,{},{timeout:35000});
    await page.keyboard.up('d');
    const finish=await state();assert(finish.distance>50);assert.equal(finish.hits,0);
    assert.match(await page.locator('#walk-status').textContent(),/Route complete/);
    await page.screenshot({path:path.join(resultDirectory,'berlin-finish.png')});
    // Focus loss must stop held movement, even without receiving keyup on canvas.
    await page.keyboard.down('w');await page.waitForTimeout(150);
    await page.locator('#filter').focus();const blurStart=await state();await page.waitForTimeout(250);await page.keyboard.up('w');
    assert.deepEqual((await state()).position,blurStart.position);
    await page.getByRole('button',{name:'Restart walk',exact:true}).click();
    assert.equal((await state()).distance,0);
    // Aim at the nearest building's GLB bottom-cap centroid, not its bounding box.
    const target=await page.evaluate(()=>{
      const raw=Uint8Array.from(atob(FORGE_DATA.glb),c=>c.charCodeAt(0)),v=new DataView(raw.buffer),n=v.getUint32(12,true),doc=JSON.parse(new TextDecoder().decode(raw.slice(20,20+n))),base=28+n;
      const acc=i=>{const a=doc.accessors[i],b=doc.bufferViews[a.bufferView],off=base+(b.byteOffset||0)+(a.byteOffset||0);return Array.from({length:a.count*(a.type==='VEC3'?3:1)},(_,j)=>a.componentType===5126?v.getFloat32(off+j*4,true):v.getUint32(off+j*4,true));};
      const p=FORGE_WALK.state.position,candidates=[];
      FORGE_DATA.manifest.features.forEach((f,i)=>{if(f.kind!=='building')return;const pr=doc.meshes[i].primitives[0],pos=acc(pr.attributes.POSITION),ids=acc(pr.indices);for(let j=0;j<ids.length;j+=3){const tri=ids.slice(j,j+3).map(k=>pos.slice(k*3,k*3+3));if(tri.every(a=>Math.abs(a[1])<1e-6)){const c=[tri.reduce((s,a)=>s+a[0],0)/3,tri.reduce((s,a)=>s+a[2],0)/3];candidates.push({point:c,id:f.id,distance:Math.hypot(c[0]-p[0],c[1]-p[1])});}}});
      return candidates.sort((a,b)=>a.distance-b.distance)[0];
    });
    assert(target);
    await faceRight(target.point);await page.keyboard.down('d');
    await page.waitForFunction(()=>window.FORGE_WALK.state.hits>0,{},{timeout:35000});
    await page.waitForTimeout(500);
    await page.keyboard.up('d');
    const collision=await state();assert.match(collision.lastBlock,/^(way|relation)\//);
    assert(collision.distance<target.distance);
    await page.screenshot({path:path.join(resultDirectory,'berlin-collision.png')});
    await page.keyboard.press('Escape');assert.equal(await page.evaluate(()=>FORGE_WALK.walking),false);
    await page.getByRole('button',{name:'Reset view',exact:true}).click();
    await page.screenshot({path:path.join(resultDirectory,'berlin-overview.png')});
    assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);assert.deepEqual(await page.evaluate(()=>window.violations),[]);
    fs.writeFileSync(path.join(resultDirectory,'trajectory.json'),JSON.stringify(await page.evaluate(()=>window.walkTrace))+'\n');
    const report={browser:browser.version(),route,start,finish,collision,collisionTarget:target,checks:['offline file launch, no network or CSP errors','real extract attribution and acquisition displayed','keyboard route >50 m with zero collisions','building collision via keyboard','focus loss clears movement','restart and Escape','four visible screenshots'],errors,requests};
    fs.writeFileSync(path.join(resultDirectory,'browser.json'),JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify(report,null,2));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
