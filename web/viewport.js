// Browser-only renderer. The fallback canvas still works without CDN access.
const SENSOR_ANGLES={front:0,front_left:Math.PI/4,left:Math.PI/2,front_right:-Math.PI/4,right:-Math.PI/2};
export class Viewport {
  constructor(canvas,label){this.canvas=canvas;this.label=label;this.sceneData=null;this.state=null;this.mode='perspective';this.trail=[];this.lastT=-1;this.THREE=null;this.drag=null;this.phi=.72;this.theta=-.55;this.distance=2.0;this.target=[0,0];
    this.canvas.addEventListener('pointerdown',e=>{this.drag={x:e.clientX,y:e.clientY};this.canvas.setPointerCapture(e.pointerId)});
    this.canvas.addEventListener('pointermove',e=>{if(!this.drag || this.mode==='top')return;this.theta+=(e.clientX-this.drag.x)*.008;this.phi=Math.max(.18,Math.min(1.44,this.phi-(e.clientY-this.drag.y)*.008));this.drag={x:e.clientX,y:e.clientY}});
    this.canvas.addEventListener('pointerup',()=>this.drag=null);
    this.canvas.addEventListener('wheel',e=>{e.preventDefault();this.distance=Math.max(.4,Math.min(5,this.distance*Math.exp(e.deltaY*.001)))},{passive:false});
    new ResizeObserver(()=>this.resize()).observe(canvas.parentElement);
    this.initialize();
  }
  async initialize(){
    try {
      const THREE=await import('https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.js');
      this.THREE=THREE;this.label.textContent='WEBGL / THREE.JS';
      this.renderer=new THREE.WebGLRenderer({canvas:this.canvas,antialias:true,alpha:false,powerPreference:'high-performance'});
      this.renderer.setPixelRatio(Math.min(devicePixelRatio,2));
      this.renderer.setClearColor(0x0a1720);
      this.threeScene=new THREE.Scene();this.threeScene.background=new THREE.Color(0x0b1721);
      this.threeScene.fog=new THREE.FogExp2(0x0b1721,.29);
      this.camera=new THREE.PerspectiveCamera(48,1,.01,60);
      this.threeScene.add(new THREE.HemisphereLight(0xaac6e6,0x19352a,2.25));
      const light=new THREE.DirectionalLight(0xffffff,2.2);light.position.set(-1,3,1);this.threeScene.add(light);
      const grid=new THREE.GridHelper(6,60,0x315060,0x1a303d);grid.position.y=-.002;this.threeScene.add(grid);
      const floor=new THREE.Mesh(new THREE.PlaneGeometry(7,7),new THREE.MeshStandardMaterial({color:0x152935,roughness:.98,metalness:0}));
      floor.rotation.x=-Math.PI/2;floor.position.y=-.006;this.threeScene.add(floor);
      this.wallsGroup=new THREE.Group();this.threeScene.add(this.wallsGroup);
      this.trailGroup=new THREE.Group();this.threeScene.add(this.trailGroup);
      this.raysGroup=new THREE.Group();this.threeScene.add(this.raysGroup);
      this.robot=new THREE.Group();this.threeScene.add(this.robot);
      this.resize();this.rebuild();
    }catch(err){console.warn('Three.js unavailable; switching to canvas fallback',err);this.label.textContent='2D FALLBACK · 3D CDN OFFLINE';this.THREE=null;this.ctx=this.canvas.getContext('2d');this.resize();}
  }
  update(scene,state){
    if(scene&&(!this.sceneData||JSON.stringify(scene)!==JSON.stringify(this.sceneData))){this.sceneData=scene;this.trail=[];this.lastT=-1;this.rebuild();}
    if(state){if(state.t<this.lastT){this.trail=[];}this.state=state;if(state.t!==this.lastT){this.lastT=state.t;this.trail.push([state.x,state.y]);if(this.trail.length>3000)this.trail.shift();}}
  }
  showReplayFrame(state, frames, index){
    // Replace the travelled path, so seeking backward removes future positions.
    const stride=Math.max(1,Math.floor(index/1800));
    this.trail=[];
    for(let i=0;i<=index;i+=stride){const s=frames[i].state;this.trail.push([s.x,s.y]);}
    if(index%stride){const s=frames[index].state;this.trail.push([s.x,s.y]);}
    this.state=state;
    this.lastT=state.t;
  }
  cameraMode(mode){this.mode=mode}
  resize(){
    const rect=this.canvas.parentElement.getBoundingClientRect();this.w=Math.max(10,Math.round(rect.width));this.h=Math.max(10,Math.round(rect.height));
    if(this.renderer){this.renderer.setSize(this.w,this.h,false);this.camera.aspect=this.w/this.h;this.camera.updateProjectionMatrix();}
    else{this.canvas.width=Math.round(this.w*Math.min(devicePixelRatio,2));this.canvas.height=Math.round(this.h*Math.min(devicePixelRatio,2));}
  }
  rebuild(){
    if(!this.THREE || !this.sceneData)return;
    const T=this.THREE;const clear=group=>{while(group.children.length){const a=group.children[0];group.remove(a);a.geometry?.dispose();a.material?.dispose();}};
    clear(this.wallsGroup);clear(this.robot);clear(this.trailGroup);clear(this.raysGroup);
    const wallMat=new T.MeshStandardMaterial({color:0xdde6e4,roughness:.73});
    const topMat=new T.MeshStandardMaterial({color:0xad5b4b,roughness:.76});
    for(const [x,y,hx,hy] of this.sceneData.walls){
      let w=new T.Mesh(new T.BoxGeometry(hx*2,.055,hy*2),wallMat);w.position.set(x,.0275,y);this.wallsGroup.add(w);
      let top=new T.Mesh(new T.BoxGeometry(hx*2,.004,hy*2),topMat);top.position.set(x,.057,y);this.wallsGroup.add(top);
    }
    const bodyMat=new T.MeshStandardMaterial({color:0x2991ad,metalness:.35,roughness:.36});
    const body=new T.Mesh(new T.BoxGeometry(.067,.019,.050),bodyMat);body.position.y=.021;this.robot.add(body);
    const nose=new T.Mesh(new T.ConeGeometry(.008,.022,3),new T.MeshStandardMaterial({color:0xf0d28c}));nose.rotation.z=-Math.PI/2;nose.position.set(.039,.033,0);this.robot.add(nose);
    const PCB=new T.Mesh(new T.BoxGeometry(.039,.004,.038),new T.MeshStandardMaterial({color:0x114e57,roughness:.6}));PCB.position.y=.033;this.robot.add(PCB);
    const wheelMat=new T.MeshStandardMaterial({color:0x111b24,roughness:.96});
    const r=this.sceneData.robot.wheel_radius_m;
    for(const side of [-1,1]){
      const wheel=new T.Mesh(new T.CylinderGeometry(r,r,.008,24),wheelMat);
      wheel.rotation.x=Math.PI/2;wheel.position.set(0,r,side*(this.sceneData.robot.track_m/2));this.robot.add(wheel);
      const hub=new T.Mesh(new T.CylinderGeometry(r*.45,r*.45,.009,20),new T.MeshStandardMaterial({color:0x8ba4b3,metalness:.4,roughness:.45}));
      hub.rotation.x=Math.PI/2;hub.position.copy(wheel.position);this.robot.add(hub);
    }
    const fan=new T.Mesh(new T.CylinderGeometry(.012,.012,.009,24),new T.MeshStandardMaterial({color:0x0d2639,metalness:.35,roughness:.4}));fan.position.set(-.009,.038,0);this.robot.add(fan);
    const route=this.sceneData.route.map(([x,y])=>new T.Vector3(x,.002,y));
    if(route.length>1){const guide=new T.Line(new T.BufferGeometry().setFromPoints(route),new T.LineDashedMaterial({color:0xd7b66b,dashSize:.025,gapSize:.013,transparent:true,opacity:.65}));guide.computeLineDistances();this.wallsGroup.add(guide);}
  }
  draw(){
    if(!this.THREE){this.draw2D();return}
    if(!this.state||!this.sceneData)return;
    const T=this.THREE,s=this.state;
    this.robot.position.set(s.x,0,s.y);this.robot.rotation.y=-s.yaw;
    const clear=group=>{while(group.children.length){const a=group.children[0];group.remove(a);a.geometry.dispose();a.material.dispose();}};
    clear(this.trailGroup);
    if(this.trail.length>1){const pts=this.trail.filter((_,i)=>i%3===0).map(([x,y])=>new T.Vector3(x,.004,y));const line=new T.Line(new T.BufferGeometry().setFromPoints(pts),new T.LineBasicMaterial({color:0x64d5bc,transparent:true,opacity:.82}));this.trailGroup.add(line)}
    clear(this.raysGroup);
    for(const [name,ang] of Object.entries(SENSOR_ANGLES)){
      const mm=s.tof_mm?.[name];if(mm==null)continue;
      const angle=s.yaw+ang,dist=mm/1000;
      let a=new T.Vector3(s.x+.018*Math.cos(s.yaw),.027,s.y+.018*Math.sin(s.yaw));
      let b=new T.Vector3(a.x+dist*Math.cos(angle),.027,a.z+dist*Math.sin(angle));
      this.raysGroup.add(new T.Line(new T.BufferGeometry().setFromPoints([a,b]),new T.LineBasicMaterial({color:name==='front'?0xe6d16e:0x4babb6,transparent:true,opacity:.64})));
    }
    let targetX=0,targetZ=0;
    if(this.mode==='follow'){targetX=s.x;targetZ=s.y}
    const d=this.distance;
    if(this.mode==='top'){this.camera.position.set(targetX+.001,d*1.6,targetZ+.001);this.camera.up.set(1,0,0)}
    else{this.camera.up.set(0,1,0);const th=this.mode==='follow'?-s.yaw+Math.PI/2:this.theta;this.camera.position.set(targetX+d*Math.sin(this.phi)*Math.cos(th),d*Math.cos(this.phi),targetZ+d*Math.sin(this.phi)*Math.sin(th));}
    this.camera.lookAt(targetX,0,targetZ);
    this.renderer.render(this.threeScene,this.camera);
  }
  draw2D(){
    if(!this.ctx||!this.sceneData)return;
    const ctx=this.ctx,scale=Math.min(this.w/2.5,this.h/1.6),px=d=>d*scale,dpr=this.canvas.width/this.w;
    ctx.setTransform(dpr,0,0,dpr,0,0);ctx.fillStyle='#10232e';ctx.fillRect(0,0,this.w,this.h);ctx.save();ctx.translate(this.w/2,this.h/2);
    ctx.strokeStyle='#263d49';ctx.lineWidth=1;for(let i=-12;i<=12;i++){ctx.beginPath();ctx.moveTo(px(i*.1),-this.h);ctx.lineTo(px(i*.1),this.h);ctx.stroke();ctx.beginPath();ctx.moveTo(-this.w,px(i*.1));ctx.lineTo(this.w,px(i*.1));ctx.stroke()}
    for(const [x,y,hx,hy] of this.sceneData.walls){ctx.fillStyle='#dbe3de';ctx.fillRect(px(x-hx),px(y-hy),px(hx*2),px(hy*2))}
    ctx.strokeStyle='#bd9863';ctx.lineWidth=2;ctx.setLineDash([5,5]);ctx.beginPath();this.sceneData.route.forEach(([x,y],i)=>i?ctx.lineTo(px(x),px(y)):ctx.moveTo(px(x),px(y)));ctx.stroke();ctx.setLineDash([]);
    ctx.strokeStyle='#59d8bb';ctx.beginPath();this.trail.forEach(([x,y],i)=>i?ctx.lineTo(px(x),px(y)):ctx.moveTo(px(x),px(y)));ctx.stroke();
    if(this.state){const s=this.state;ctx.save();ctx.translate(px(s.x),px(s.y));ctx.rotate(s.yaw);ctx.fillStyle='#218dad';ctx.fillRect(px(-.034),px(-.025),px(.068),px(.05));ctx.fillStyle='#d6ecf2';ctx.fillRect(px(-.011),px(-.039),px(.024),px(.008));ctx.fillRect(px(-.011),px(.031),px(.024),px(.008));ctx.fillStyle='#edcf8d';ctx.beginPath();ctx.moveTo(px(.043),0);ctx.lineTo(px(.027),px(-.012));ctx.lineTo(px(.027),px(.012));ctx.fill();ctx.restore();}
    ctx.restore();
  }
}
