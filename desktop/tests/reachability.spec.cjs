const {test,expect,_electron:electron}=require('@playwright/test');
const path=require('node:path');
const fs=require('node:fs');

test('末端实时试摆、无解保留、过期响应和选定姿态执行',async()=>{
 const output=path.resolve(__dirname,'../test-results/reachability');fs.mkdirSync(output,{recursive:true});
 const env={...process.env,CYBERARM_TEST_USER_DATA:path.join(output,'user')};delete env.ELECTRON_RUN_AS_NODE;
 const packaged=process.env.CYBERARM_TEST_EXECUTABLE;
 const app=await electron.launch({...(packaged?{executablePath:packaged,args:[]}:{args:[path.resolve(__dirname,'..')]}),env});
 try{
  const page=await app.firstWindow();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await expect(page.locator('.connection')).toContainText('本地已连接',{timeout:60000});
  await expect(page.locator('.scene-stage')).toHaveAttribute('data-model-status',/已载入/,{timeout:60000});
  await page.getByRole('button',{name:'模式',exact:true}).click();
  await page.getByRole('button',{name:'自动运行',exact:true}).click();
  await page.getByRole('button',{name:'关闭面板'}).click();
  const status=page.getByTestId('reachability-status');
  await expect(status).toContainText('目标可达',{timeout:60000});
  const state=()=>page.evaluate(()=>fetch('/api/state').then(r=>r.json()));
  const before=await state();const y=page.getByLabel('目标Y',{exact:true});
  // Exercise the real Three.js transform handle with the mouse. Project a
  // point on its Z shaft using the same documented camera configuration.
  const {pathToFileURL}=require('node:url');
  const THREE=await import(pathToFileURL(path.resolve(__dirname,'../../simulator/frontend/node_modules/three/build/three.module.js')).href);
  const rect=await page.locator('.viewport canvas').boundingBox();
  const camera=new THREE.PerspectiveCamera(40,rect.width/rect.height,.001,10);
  camera.up.set(0,0,1);camera.position.set(.50,-.63,.38);camera.lookAt(.12,0,.115);
  camera.updateMatrixWorld();
  const tcp=new THREE.Vector3(...before.tcp.slice(0,3).map(r=>r[3]));
  const shaft=tcp.clone().add(new THREE.Vector3(0,0,.035)).project(camera);
  const x=rect.x+(shaft.x+1)*rect.width/2,z=rect.y+(1-shaft.y)*rect.height/2;
  await page.mouse.move(x,z);await page.mouse.down();
  await page.mouse.move(x,z-8,{steps:8});
  await expect.poll(async()=>Number(await page.getByLabel('目标Z',{exact:true}).inputValue())).toBeGreaterThan(before.tcp[2][3]*1000+1);
  await expect.poll(async()=>Math.max(...await page.locator('.trial-joints b').allTextContents().then(values=>values.map(v=>Math.abs(parseFloat(v)))))).toBeGreaterThan(.1);
  await page.mouse.up();await expect(status).toContainText('目标可达');
  await page.getByRole('button',{name:'取当前值'}).click();await expect(status).toContainText('目标可达');
  await y.fill('20');
  await expect(status).toContainText('目标可达');
  await expect(page.getByTestId('trial-joint-0')).not.toHaveText('0.0°');
  const valid=await page.locator('.trial-joints').innerText();
  expect((await state()).q_deg).toEqual(before.q_deg);
  expect(Number(await page.getByTestId('target-deviation').innerText())).toBeLessThanOrEqual(.5);
  await page.screenshot({path:path.join(output,'reachable.png')});
  await page.getByLabel('目标X',{exact:true}).fill('10000');
  await expect(status).toContainText('未找到有效解');
  expect(await page.locator('.trial-joints').innerText()).toBe(valid);
  await expect(page.getByRole('button',{name:'预览路径',exact:true})).toBeDisabled();
  await page.screenshot({path:path.join(output,'unsolved.png')});
  await page.getByRole('button',{name:'取当前值'}).click();
  await expect(status).toContainText('目标可达');
  // Delay a successful response past a newer, unreachable target.
  let entered;const started=new Promise(r=>entered=r);let release;const hold=new Promise(r=>release=r);
  await page.route('**/api/reachability',async route=>{
   const response=await route.fetch();entered();await hold;await route.fulfill({response});
  },{times:1});
  await y.fill('18');await started;
  await page.getByLabel('目标X',{exact:true}).fill('10000');release();
  await expect(status).toContainText('未找到有效解');
  expect((await state()).q_deg).toEqual(before.q_deg);
  await page.getByRole('button',{name:'取当前值'}).click();
  await expect(status).toContainText('目标可达');
  await y.fill('20');await expect(status).toContainText('目标可达');
  const trial=await page.getByTestId('trial-joint-0').innerText();
  await page.getByRole('button',{name:'预览路径',exact:true}).click();
  await expect(page.locator('.feedback')).toContainText('预览通过',{timeout:90000});
  await page.getByRole('button',{name:'执行',exact:true}).click();
  await expect.poll(async()=>(await state()).q_deg[0],{timeout:20000}).toBeCloseTo(parseFloat(trial),0);
  expect(errors).toEqual([]);
 }finally{await app.close();}
});
