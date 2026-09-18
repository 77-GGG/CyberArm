import {useEffect,useRef} from 'react';
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {TransformControls} from 'three/addons/controls/TransformControls.js';
import {api} from './api';
import type {State,Model,Plan} from './types';
export function SceneView({state,model,plan,points,drag,target,onTarget,onDragging,trialStatus,view,onLoad,referenceAxis}:{state:State;model:Model;plan:Plan|null;points:number[][];drag:boolean;target:number[];onTarget:(p:number[])=>void;onDragging:(v:boolean)=>void;trialStatus:string;view:string;onLoad:(message:string)=>void;referenceAxis?:{origin:number[];direction:number[]}}){
 const host=useRef<HTMLDivElement>(null);const live=useRef({state,plan,points,drag,target,onTarget,onDragging,trialStatus});live.current={state,plan,points,drag,target,onTarget,onDragging,trialStatus};
 const system=useRef<{camera:THREE.PerspectiveCamera;controls:OrbitControls}|null>(null);
 useEffect(()=>{
  const element=host.current!;const scene=new THREE.Scene();scene.background=new THREE.Color('#edf1f5');scene.fog=new THREE.Fog('#edf1f5',1.3,3.8);
  const camera=new THREE.PerspectiveCamera(40,element.clientWidth/element.clientHeight,.001,10);camera.up.set(0,0,1);camera.position.set(.50,-.63,.38);
  const renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));renderer.setSize(element.clientWidth,element.clientHeight);renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.35;element.appendChild(renderer.domElement);
  const controls=new OrbitControls(camera,renderer.domElement);controls.target.set(.12,0,.115);controls.enableDamping=true;controls.minDistance=.15;controls.maxDistance=1.8;system.current={camera,controls};
  scene.add(new THREE.HemisphereLight('#d4e6ff','#738295',2));const light=new THREE.DirectionalLight('#fff4df',3.1);light.position.set(.4,-.35,.85);light.castShadow=true;light.shadow.mapSize.set(2048,2048);Object.assign(light.shadow.camera,{left:-.5,right:.5,top:.5,bottom:-.5,near:.01,far:2});light.shadow.bias=-.00015;scene.add(light);
  const fill=new THREE.DirectionalLight('#8dcfff',1.5);fill.position.set(-.4,.5,.3);scene.add(fill);
  const floor=Math.min(...model.meshes.map(m=>m.bounds[0][2]))-.002;
  const ground=new THREE.Mesh(new THREE.PlaneGeometry(4,4),new THREE.MeshStandardMaterial({color:'#e4e9ef',roughness:.95}));ground.position.z=floor;ground.receiveShadow=true;scene.add(ground);
  const grid=new THREE.GridHelper(2,80,'#bac6d3','#d2dbe4');grid.rotation.x=Math.PI/2;grid.position.z=floor+.0001;scene.add(grid);
  const baseAxes=new THREE.AxesHelper(.065);baseAxes.position.z=floor+.001;scene.add(baseAxes);
  if(referenceAxis){
   const arrow=new THREE.ArrowHelper(new THREE.Vector3(...referenceAxis.direction as [number,number,number]).normalize(),new THREE.Vector3(...referenceAxis.origin as [number,number,number]),.075,0x2563eb,.015,.009);
   // Reference axes must remain visible even when the shaft is inside a housing.
   arrow.traverse(o=>{if(o instanceof THREE.Line||o instanceof THREE.Mesh){o.renderOrder=100;const materials=Array.isArray(o.material)?o.material:[o.material];materials.forEach(m=>{m.depthTest=false;m.depthWrite=false;});}});
   scene.add(arrow);
  }
  let robot:THREE.Group|undefined,ghost:THREE.Group|undefined;let disposed=false;
  const loader=new GLTFLoader();loader.load('/models/robot.glb',g=>{
   if(disposed)return;robot=g.scene;robot.traverse(o=>{if(o instanceof THREE.Mesh){o.castShadow=true;o.receiveShadow=true;}if(typeof o.userData.frame_index==='number')o.matrixAutoUpdate=false;});scene.add(robot);
   ghost=robot.clone(true);ghost.traverse(o=>{if(o instanceof THREE.Mesh){o.material=new THREE.MeshBasicMaterial({color:'#66ecd0',transparent:true,opacity:.19,depthWrite:false});o.castShadow=false;}});scene.add(ghost);onLoad('RevC 模型已载入 · 87 个零件');
  },undefined,()=>onLoad('模型加载失败，请检查本地服务与模型文件'));
  const targetObject=new THREE.Object3D();scene.add(targetObject);const axes=new THREE.AxesHelper(.05);targetObject.add(axes);
  const gizmo=new TransformControls(camera,renderer.domElement);gizmo.setMode('translate');gizmo.setSize(.75);gizmo.attach(targetObject);scene.add(gizmo.getHelper());let dragging=false;
  gizmo.addEventListener('dragging-changed',e=>{dragging=Boolean(e.value);controls.enabled=!dragging;live.current.onDragging(dragging);if(!dragging)live.current.onTarget(targetObject.position.toArray().map(x=>x*1000));});
  gizmo.addEventListener('objectChange',()=>{if(dragging)live.current.onTarget(targetObject.position.toArray().map(x=>x*1000));});
  const tcp=new THREE.Mesh(new THREE.SphereGeometry(.003,12,12),new THREE.MeshBasicMaterial({color:'#66ecd0'}));scene.add(tcp);
  const tcpAxes=new THREE.AxesHelper(.025);scene.add(tcpAxes);
  const targetDot=new THREE.Mesh(new THREE.SphereGeometry(.004,12,12),new THREE.MeshBasicMaterial({color:'#e6b86d'}));targetObject.add(targetDot);
  const deviation=new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(),new THREE.Vector3()]),new THREE.LineDashedMaterial({color:'#e6b86d',dashSize:.004,gapSize:.002}));scene.add(deviation);
  let line:THREE.Line|undefined,cloud:THREE.Points|undefined,oldPlan:Plan|null|undefined,oldPoints:number[][]|undefined,oldScene='';const obstacles=new THREE.Group();scene.add(obstacles);
  const frameMatrices=(object:THREE.Group,matrices:number[][])=>object.traverse(o=>{const index=o.userData.frame_index;if(typeof index==='number'&&index>=0){o.matrix.fromArray(matrices[index]).transpose();o.matrixWorldNeedsUpdate=true;}});
  // A ghost is updated with authoritative transforms from a separate FK endpoint.
  let ghostMatrices:number[][]|undefined;let requestId=0;
  const resize=()=>{camera.aspect=element.clientWidth/element.clientHeight;camera.updateProjectionMatrix();renderer.setSize(element.clientWidth,element.clientHeight);};const observer=new ResizeObserver(resize);observer.observe(element);
  let raf=0;const animate=()=>{
   if(disposed)return;raf=requestAnimationFrame(animate);const data=live.current;
   if(robot)frameMatrices(robot,data.state.matrices);
   const p=data.state.tcp;tcp.position.set(p[0][3],p[1][3],p[2][3]);
   tcpAxes.position.copy(tcp.position);tcpAxes.quaternion.setFromRotationMatrix(new THREE.Matrix4().set(...p.flat() as Parameters<THREE.Matrix4['set']>));tcpAxes.visible=data.drag;
   targetDot.visible=data.drag;targetDot.material.color.set(data.trialStatus==='reachable'?'#66ecd0':data.trialStatus==='solving'?'#e6b86d':'#ef8e87');
   gizmo.enabled=data.drag;gizmo.getHelper().visible=data.drag;axes.visible=data.drag;
   if(!dragging)targetObject.position.fromArray(data.target.map(x=>x/1000));
   deviation.visible=data.drag&&!data.plan&&tcp.position.distanceTo(targetObject.position)>.0005;
   if(deviation.visible){const positions=deviation.geometry.getAttribute('position') as THREE.BufferAttribute;positions.setXYZ(0,tcp.position.x,tcp.position.y,tcp.position.z);positions.setXYZ(1,targetObject.position.x,targetObject.position.y,targetObject.position.z);positions.needsUpdate=true;deviation.geometry.computeBoundingSphere();deviation.computeLineDistances();}
   if(data.plan!==oldPlan){oldPlan=data.plan;const id=++requestId;ghostMatrices=undefined;if(line){scene.remove(line);line.geometry.dispose();(line.material as THREE.Material).dispose();line=undefined;}
    if(data.plan){line=new THREE.Line(new THREE.BufferGeometry().setFromPoints(data.plan.path.map(p=>new THREE.Vector3(...p as [number,number,number]))),new THREE.LineBasicMaterial({color:'#6be1c1'}));scene.add(line);api('pose',{q_deg:data.plan.end.map(x=>x*180/Math.PI)}).then(r=>{if(id===requestId)ghostMatrices=r.matrices;}).catch(()=>{});}}
   if(ghost){ghost.visible=Boolean(data.plan&&ghostMatrices);if(ghostMatrices)frameMatrices(ghost,ghostMatrices);}
   if(data.points!==oldPoints){oldPoints=data.points;if(cloud){scene.remove(cloud);cloud.geometry.dispose();(cloud.material as THREE.Material).dispose();}cloud=new THREE.Points(new THREE.BufferGeometry().setFromPoints(data.points.map(p=>new THREE.Vector3(...p as [number,number,number]))),new THREE.PointsMaterial({color:'#6adfc6',size:.0018,transparent:true,opacity:.25,depthWrite:false}));scene.add(cloud);}
   const sceneKey=JSON.stringify(data.state.obstacles);if(sceneKey!==oldScene){oldScene=sceneKey;for(const child of [...obstacles.children]){obstacles.remove(child);if(child instanceof THREE.Mesh){child.geometry.dispose();child.material.dispose();}}for(const o of data.state.obstacles){const mesh=new THREE.Mesh(new THREE.BoxGeometry(...o.size as [number,number,number]),new THREE.MeshStandardMaterial({color:'#e9ae64',transparent:true,opacity:.6}));mesh.position.fromArray(o.center);mesh.castShadow=true;obstacles.add(mesh);}}
   controls.update();renderer.render(scene,camera);
  };animate();
  return()=>{disposed=true;cancelAnimationFrame(raf);observer.disconnect();gizmo.dispose();controls.dispose();scene.traverse(o=>{if(o instanceof THREE.Mesh||o instanceof THREE.Line||o instanceof THREE.Points){o.geometry.dispose();const materials=Array.isArray(o.material)?o.material:[o.material];materials.forEach(m=>m.dispose());}});renderer.dispose();element.removeChild(renderer.domElement);};
 },[]);
 useEffect(()=>{const s=system.current;if(!s)return;const positions:Record<string,number[]>={perspective:[.50,-.63,.38],top:[.12,-.001,.8],front:[.12,-.8,.13],side:[.9,0,.13]};s.camera.position.fromArray(positions[view]||positions.perspective);s.controls.target.set(.12,0,.115);},[view]);
 return <div className="viewport" ref={host} aria-label="机械臂三维视图"/>;
}
