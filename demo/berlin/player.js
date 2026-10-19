'use strict';
// Ground-plane disc collisions use the bottom caps of the exported GLB. Holes
// stay empty. Continuous segment/triangle distance prevents thin-wall tunneling.
(function(root) {
  const radius = .45, speed = 5;
  const cross = (a,b,p) => (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]);
  function inside(p,t) {
    const s = t.map((a,i) => cross(a,t[(i+1)%3],p));
    return s.every(v=>v>=-1e-9) || s.every(v=>v<=1e-9);
  }
  function pointSegment(p,a,b) {
    const dx=b[0]-a[0], dz=b[1]-a[1], d=dx*dx+dz*dz;
    const u=d ? Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dz)/d)) : 0;
    return Math.hypot(p[0]-a[0]-u*dx,p[1]-a[1]-u*dz);
  }
  function segmentDistance(a,b,c,d) {
    if (cross(a,b,c)*cross(a,b,d)<0 && cross(c,d,a)*cross(c,d,b)<0) return 0;
    return Math.min(pointSegment(a,c,d),pointSegment(b,c,d),pointSegment(c,a,b),pointSegment(d,a,b));
  }
  function create(meshes,features,bounds) {
    const triangles=[];
    meshes.forEach((mesh,i)=> {
      if(features[i].kind!=='building') return;
      for(let j=0;j<mesh.indices.length;j+=3) {
        const v=mesh.indices.slice(j,j+3).map(k=>mesh.vertices[k]);
        if(v.every(p=>Math.abs(p[1])<1e-6)) {
          const t=v.map(p=>[p[0],p[2]]);
          triangles.push({t,id:features[i].id,min:[Math.min(...t.map(p=>p[0])),Math.min(...t.map(p=>p[1]))],max:[Math.max(...t.map(p=>p[0])),Math.max(...t.map(p=>p[1]))]});
        }
      }
    });
    function blocked(a,b=a) {
      if(![...a,...b].every(Number.isFinite)) return 'invalid position';
      if(b[0]<bounds[0]+radius || b[0]>bounds[2]-radius || b[1]<bounds[1]+radius || b[1]>bounds[3]-radius) return 'map boundary';
      for(const {t,id,min,max} of triangles) {
        if(Math.max(a[0],b[0])+radius<min[0] || Math.min(a[0],b[0])-radius>max[0] || Math.max(a[1],b[1])+radius<min[1] || Math.min(a[1],b[1])-radius>max[1]) continue;
        if(inside(a,t)||inside(b,t)||t.some((p,i)=>segmentDistance(a,b,p,t[(i+1)%3])<=radius)) return id;
      }
      return null;
    }
    // Select the longest unobstructed road segment as a reproducible walk route.
    let route=null;
    meshes.forEach((mesh,i)=> {
      if(features[i].kind!=='road') return;
      for(let j=0;j<mesh.vertices.length;j+=4) {
        const v=mesh.vertices.slice(j,j+4);
        const a=[(v[0][0]+v[3][0])/2,(v[0][2]+v[3][2])/2];
        const b=[(v[1][0]+v[2][0])/2,(v[1][2]+v[2][2])/2];
        const length=Math.hypot(b[0]-a[0],b[1]-a[1]);
        if(length<8) continue;
        const start=a.map((n,k)=>n+(b[k]-n)*.1), end=a.map((n,k)=>n+(b[k]-n)*.9);
        if(!blocked(start,end) && (!route||length>route.length)) route={start,end,length,id:features[i].id,name:features[i].tags.name||features[i].id};
      }
    });
    let spawn=route?.start;
    if(!spawn) {
      // Bounded search, not a promise that every free pocket can be found.
      for(let row=0;row<41 && !spawn;row++) for(let col=0;col<41 && !spawn;col++) {
        const p=[bounds[0]+radius+(bounds[2]-bounds[0]-2*radius)*col/40,bounds[1]+radius+(bounds[3]-bounds[1]-2*radius)*row/40];
        if(!blocked(p)) spawn=p;
      }
    }
    let position=spawn?.slice()||null, distance=0, hits=0, lastBlock=null, reached=false;
    function reset() {position=spawn?.slice()||null;distance=0;hits=0;lastBlock=null;reached=false;}
    function move(dx,dz) {
      if(!position || !Number.isFinite(dx) || !Number.isFinite(dz)) return;
      const steps=Math.max(1,Math.ceil(Math.hypot(dx,dz)/.2));
      if(steps>10000) throw new Error('movement budget exceeded');
      for(let i=0;i<steps;i++) {
        const old=position.slice(), target=[position[0]+dx/steps,position[1]+dz/steps];
        const hit=blocked(position,target);
        if(!hit) position=target;
        else {
          hits++;lastBlock=hit;
          const x=[target[0],position[1]];
          if(!blocked(position,x)) position=x;
          const z=[position[0],target[1]];
          if(!blocked(position,z)) position=z;
        }
        distance+=Math.hypot(position[0]-old[0],position[1]-old[1]);
        if(route&&Math.hypot(position[0]-route.end[0],position[1]-route.end[1])<2) reached=true;
      }
    }
    return {blocked,move,reset,route,bounds,radius,speed,get state(){return {position:position?.slice()||null,distance,hits,lastBlock,reached};}};
  }
  const api={create,radius,speed};
  if(typeof module!=='undefined'&&module.exports) module.exports=api;
  else root.ForgePlayer=api;
})(globalThis);
