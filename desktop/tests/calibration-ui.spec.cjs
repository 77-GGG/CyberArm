const {test,expect,_electron:electron}=require('@playwright/test');
const path=require('node:path');
// UI contract test with a deterministic HTTP/WS device fixture. Actual C++
// firmware and serial/server behavior are executed by test_calibration.py.
test('单轴工作台：开启、计数点动、记录、关闭、保存与接线显示',async()=>{
 const env={...process.env,CYBERARM_TEST_USER_DATA:path.resolve(__dirname,'../test-results/calibration-user')};delete env.ELECTRON_RUN_AS_NODE;
 const app=await electron.launch({args:[path.resolve(__dirname,'..')],env});
 try{
  const page=await app.firstWindow();await expect(page.locator('.connection')).toContainText('本地已连接',{timeout:60000});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const boot=await page.evaluate(()=>fetch('/api/bootstrap').then(r=>r.json()));
  const state=boot.state;
  state.hardware={...state.hardware,connected:true,driver_ready:true,port:'TEST',firmware_version:'0.3.0',
    capabilities:{axis_calibration:1},device_id:'ui-device',wiring_hash:'ui-wiring',tick_us:4.88,motion_busy:false,
    wiring:{i2c:{sda_gpio:8,scl_gpio:9,clock_hz:400000},pca9685:{address:64,pwm_hz:50,oscillator_hz:25000000},axes:['J1','J2','J3','J4','J5','G'].map((name,channel)=>({name,channel}))},
    mappings:Array.from({length:6},()=>({confirmed:false,revision:0,points:[]})),test:{active:false,axis:0,pulse_us:1500,target_us:1500,ticks:307,nominal_us:1498.16,moving:false}};
  const calls=[];let ws;
  await page.routeWebSocket('**/ws?*',socket=>{ws=socket;socket.onMessage(()=>{});socket.send(JSON.stringify(state));});
  const send=()=>ws?.send(JSON.stringify(state));
  await page.route('**/api/**',async route=>{
   const url=new URL(route.request().url()),p=url.pathname;const b=route.request().postDataJSON();
   let data;
   if(p==='/api/bootstrap')data={...boot,state};
   else if(p.endsWith('/records'))data={schema_version:1,axes:{},saved_mappings:[],backup_matches:true};
   else if(p.endsWith('/ports'))data={ports:[]};
   else if(p.endsWith('/draft'))data={ok:true};
   else if(p.endsWith('/test')){
    calls.push(b.action);const h=state.hardware;
    if(b.action==='begin'){h.mode='SERVICE';h.outputs_enabled=true;h.test={...h.test,active:true,axis:b.axis};}
    if(b.action==='target'){h.test.pulse_us=b.pulse_us;h.test.target_us=b.pulse_us;h.test.ticks=Math.round(b.pulse_us/4.88);h.test.nominal_us=h.test.ticks*4.88;}
    if(b.action==='end'){h.mode='DISARMED';h.outputs_enabled=false;h.test.active=false;}
    data=h;send();
   } else if(p.endsWith('/save')){
    calls.push('save');const h=state.hardware;
    h.mappings[b.axis-1]={...b,revision:1,confirmed:true};h.calibrated[b.axis-1]=true;
    data={state:h,warning:''};send();
   } else data=state;
   await route.fulfill({json:data});
  });
  await page.reload();await expect(page.locator('.connection')).toContainText('本地已连接');
  await page.getByRole('button',{name:'调试',exact:true}).click();await page.getByRole('button',{name:'实机调试',exact:true}).click();
  await page.getByRole('tab',{name:'回中与限位',exact:true}).click();
  const panel=page.locator('.calibration-workbench');
  await panel.getByRole('checkbox',{name:'已断开传动或支撑机构，确认第一帧脉宽'}).check();
  await panel.getByRole('button',{name:'开启选中舵机'}).click();
  await expect(panel.getByRole('button',{name:'关闭输出',exact:true})).toBeEnabled();
  await panel.getByRole('button',{name:'记录当前位置为关节 0°'}).click();
  await panel.getByRole('button',{name:'2 角度采样'}).click();
  await panel.getByRole('button',{name:'-5 计数',exact:true}).click();
  await panel.getByLabel('人工角度读数').fill('-5');await panel.getByRole('button',{name:'记录人工测量'}).click();
  await panel.getByRole('button',{name:'+5 计数',exact:true}).click();
  await panel.getByRole('button',{name:'+5 计数',exact:true}).click();
  await panel.getByLabel('人工角度读数').fill('5');await panel.getByRole('button',{name:'记录人工测量'}).click();
  await panel.getByRole('button',{name:'3 范围与保存'}).click();
  await expect(panel.getByRole('button',{name:'确认保存到 ESP32 并读回'})).toBeDisabled();
  await panel.getByRole('button',{name:'关闭输出',exact:true}).click();
  await panel.getByRole('checkbox',{name:'这些点为当前设备人工实测，方向、零位及范围已复核'}).check();
  await panel.getByRole('button',{name:'确认保存到 ESP32 并读回'}).click();
  await expect(panel.getByRole('status')).toContainText('读回一致');
  expect(calls).toContain('begin');expect(calls).toContain('target');expect(calls.indexOf('end')).toBeLessThan(calls.indexOf('save'));
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setSize(1100,850));
  await page.screenshot({path:path.resolve(__dirname,'../test-results/calibration-workbench.png')});
  await page.getByRole('tab',{name:'通信',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'实机调试'})).toContainText('SDA → GPIO8');
  expect(errors).toEqual([]);
 }finally{await app.close();}
});
