'use strict';
const assert=require('node:assert/strict');
const {create}=require('../street_scene_forge/player.js');
function mesh(rects){const vertices=[],indices=[];for(const [x,z,w,h] of rects){const n=vertices.length;vertices.push([x,0,z],[x+w,0,z],[x+w,0,z+h],[x,0,z+h]);indices.push(n,n+1,n+2,n,n+2,n+3);}return {vertices,indices};}
const f=[{kind:'building',id:'wall',tags:{}},{kind:'road',id:'road',tags:{}}];
const road={vertices:[[-10,.02,-1],[-2,.02,-1],[-2,.02,1],[-10,.02,1]],indices:[0,1,2,0,2,3]};
const p=create([mesh([[0,-10,.001,20]]),road],f,[-20,-20,20,20]);
assert(p.state.position[0]<0);
p.move(15,0);
assert(p.state.position[0]<-.45,'thin wall must stop large movement');
assert.equal(p.state.lastBlock,'wall');
assert.equal(p.blocked([-5,0],[5,0]),'wall');
assert.equal(p.blocked([0,0]),'wall');
assert.equal(p.blocked([-1,0]),null);
assert.equal(p.blocked([20,0]),'map boundary');
assert.equal(p.blocked([NaN,0]),'invalid position');
p.reset();p.move(0,4);assert(Math.abs(p.state.distance-4)<1e-8);
// A courtyard frame: the hole is walkable, but a swept segment out crosses a wall.
const c=create([mesh([[-5,-5,10,1],[-5,4,10,1],[-5,-4,1,8],[4,-4,1,8]])],[f[0]],[-20,-20,20,20]);
assert.equal(c.blocked([0,0]),null);
assert.equal(c.blocked([3.5,0]),null);
assert.equal(c.blocked([3.6,0]),'wall');
assert.equal(c.blocked([0,0],[9,0]),'wall');
assert.equal(c.blocked([0,0],[0,3]),null);
// Concave L notch stays open; a bounding-box collider would incorrectly fill it.
const l=create([mesh([[0,0,1,6],[1,5,5,1]])],[f[0]],[-20,-20,20,20]);
assert.equal(l.blocked([3,3]),null);assert.equal(l.blocked([.5,3]),'wall');
const filled=create([mesh([[-20,-20,40,40]])],[f[0]],[-20,-20,20,20]);
assert.equal(filled.state.position,null);filled.move(1,1);
console.log('PASS: swept thin walls, radius clearance, boundaries, courtyard holes, concave notch, free movement, reset, no-spawn handling');
