const {test,expect,_electron:electron}=require('@playwright/test');
const path=require('node:path');
// UI contract test with a deterministic HTTP/WS device fixture. Actual C++
// firmware and serial/server behavior are executed by test_calibration.py.
test('单轴工作台：开启、计数点动、记录、关闭、保存与接线显示',async()=>{
 const env={...process.env,CYBERARM_TEST_USER_DATA:path.resolve(__dirname,'../test-results/calibration-user')};delete env.ELECTRON_RUN_AS_NODE;
 const packaged=process.env.CYBERARM_TEST_EXECUTABLE;
 // A packaged build ignores CYBERARM_TEST_USER_DATA, so give it an isolated
 // profile instead of sharing the developer's real one with later tests.
 const profile=path.resolve(__dirname,'../test-results/calibration-user/packaged-profile');
 const app=await electron.launch({...(packaged?{executablePath:packaged,args:['--user-data-dir='+profile]}:{args:[path.resolve(__dirname,'..')]}),env});
 try{
  const page=await app.firstWindow();await expect(page.locator('.connection')).toContainText('本地已连接',{timeout:60000});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const boot=await page.evaluate(()=>fetch('/api/bootstrap').then(r=>r.json()));
  const state=boot.state;
  state.hardware={...state.hardware,connected:true,driver_ready:true,port:'TEST',firmware_version:'0.3.0',
    capabilities:{axis_calibration:1,editable_limits:1},model_limits_deg:[[-30,30],[-30,30],[-30,30],[-30,30],[-30,30],[-8,8]],limits_revisions:[0,0,0,0,0,0],device_id:'ui-device',wiring_hash:'ui-wiring',tick_us:4.88,motion_busy:false,
    wiring:{i2c:{sda_gpio:8,scl_gpio:9,clock_hz:400000},pca9685:{address:64,pwm_hz:50,oscillator_hz:25000000},axes:['J1','J2','J3','J4','J5','G'].map((name,channel)=>({name,channel}))},
    mappings:Array.from({length:6},()=>({confirmed:false,revision:0,points:[]})),test:{active:false,axis:0,pulse_us:1500,target_us:1500,ticks:307,nominal_us:1498.16,moving:false}};
  const calls=[];const drafts={};let ws;
  await page.routeWebSocket('**/ws?*',socket=>{ws=socket;socket.onMessage(()=>{});socket.send(JSON.stringify(state));});
  const send=()=>ws?.send(JSON.stringify(state));
  await page.route('**/api/**',async route=>{
   const url=new URL(route.request().url()),p=url.pathname;const b=route.request().postDataJSON();
   let data;
   if(p==='/api/bootstrap')data={...boot,state};
   else if(p.endsWith('/reference'))data=await (await route.fetch()).json();
   else if(p.endsWith('/records'))data={schema_version:1,axes:drafts,current_mappings:state.hardware.mappings,saved_mappings:[],backup_matches:true};
   else if(p.endsWith('/ports'))data={ports:[]};
   else if(p.endsWith('/draft')){drafts[b.axis]=b.data;data={ok:true};}
   else if(p.endsWith('/test')){
    calls.push(b.action);const h=state.hardware;
    if(b.action==='begin'){h.mode='SERVICE';h.outputs_enabled=true;h.test={...h.test,active:true,axis:b.axis,pulse_us:b.pulse_us,target_us:b.pulse_us};}
    if(b.action==='target'){h.test.pulse_us=b.pulse_us;h.test.target_us=b.pulse_us;h.test.ticks=Math.round(b.pulse_us/4.88);h.test.nominal_us=h.test.ticks*4.88;}
    if(b.action==='angle'){
     const points=h.mappings[b.axis-1].points;
     const index=points.findIndex((v,i)=>i>0&&b.angle_deg<=v.deg),a=points[index-1],z=points[index];
     const us=a.us+(b.angle_deg-a.deg)*(z.us-a.us)/(z.deg-a.deg);
     h.test.pulse_us=us;h.test.target_us=us;h.test.ticks=Math.round(us/4.88);h.test.nominal_us=h.test.ticks*4.88;
    }
    if(b.action==='end'){h.mode='DISARMED';h.outputs_enabled=false;h.test.active=false;}
    data=h;send();
   } else if(p.endsWith('/limits')){
    calls.push('limits');const h=state.hardware;
    h.model_limits_deg[b.axis-1]=[b.low_deg,b.high_deg];h.limits_revisions[b.axis-1]++;
    data={state:h,warning:''};send();
   } else if(p.endsWith('/save')){
    calls.push('save');const h=state.hardware;
    h.mappings[b.axis-1]={...b,work_low_deg:b.low_deg,work_high_deg:b.high_deg,revision:h.mappings[b.axis-1].revision+1,confirmed:true};h.calibrated[b.axis-1]=true;
    data={state:h,warning:''};send();
   } else data=state;
   await route.fulfill({json:data});
  });
  await page.reload();await expect(page.locator('.connection')).toContainText('本地已连接');
  await page.getByRole('button',{name:'调试',exact:true}).click();await page.getByRole('button',{name:'实机调试',exact:true}).click();
  await page.getByRole('tab',{name:'单轴标定',exact:true}).click();
  const panel=page.locator('.calibration-workbench');
  await expect(panel.getByRole('button',{name:/^3.*采集角度/})).toBeDisabled();
  await expect(panel.getByRole('button',{name:/^4.*限位与保存/})).toBeDisabled();
  await expect(panel.getByRole('button',{name:/^5.*验证角度/})).toBeDisabled();
  await expect(panel.getByRole('button',{name:'开启选中舵机'})).toBeDisabled();
  await panel.getByLabel('下限 μs',{exact:true}).fill('1700');
  await expect(panel).toContainText('请填写有效窗口');
  await expect(panel.getByRole('button',{name:'开启选中舵机'})).toBeDisabled();
  await panel.getByLabel('下限 μs',{exact:true}).fill('1400');
  await page.screenshot({path:path.resolve(__dirname,'../test-results/calibration-preparation.png')});
  await panel.getByRole('checkbox',{name:'已断开传动或支撑机构，确认第一帧脉宽'}).check();
  await panel.getByRole('button',{name:'开启选中舵机'}).click();
  await expect(panel.getByRole('button',{name:'关闭输出',exact:true})).toBeEnabled();
  await expect(panel.locator('.zero-reference canvas')).toBeVisible();
  const motionCount=calls.filter(c=>c!=='renew').length;
  await panel.getByRole('button',{name:'查看本轴 +5°'}).click();
  await expect(panel.getByRole('button',{name:'查看本轴 +5°'})).toHaveAttribute('aria-pressed','true');
  await expect(panel.locator('.zero-reference-scene')).toHaveAttribute('data-model-ready','true');
  await panel.locator('.zero-reference-scene').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.resolve(__dirname,'../test-results/calibration-zero-reference.png')});
  await panel.getByRole('button',{name:'查看全零姿态'}).click();
  expect(calls.filter(c=>c!=='renew')).toHaveLength(motionCount);
  await panel.getByRole('button',{name:'记录当前位置为关节 0°'}).click();
  await expect(panel.getByLabel('调试关节')).toBeDisabled();
  await panel.getByRole('button',{name:'下一步：采集角度'}).click();
  await panel.getByRole('button',{name:'-5 计数',exact:true}).click();
  await panel.getByLabel('人工角度读数').fill('-5');await panel.getByRole('button',{name:'记录人工测量'}).click();
  await panel.getByRole('button',{name:'+5 计数',exact:true}).click();
  await panel.getByRole('button',{name:'+5 计数',exact:true}).click();
  await panel.getByLabel('人工角度读数').fill('5');await panel.getByRole('button',{name:'记录人工测量'}).click();
  await panel.getByRole('button',{name:'下一步：限位与保存'}).click();
  await expect(panel.getByRole('button',{name:'确认保存到 ESP32 并读回'})).toBeDisabled();
  await expect(panel.getByRole('button',{name:'+5 计数',exact:true})).toHaveCount(0);
  await panel.getByRole('button',{name:'关闭输出',exact:true}).click();
  const limitEditor=panel.locator('.calibration-limit-editor');
  await limitEditor.locator('summary').click();
  await limitEditor.getByLabel('模型软限位下限').fill('-75');
  await limitEditor.getByLabel('模型软限位上限').fill('80');
  await expect(limitEditor.getByRole('button',{name:'保存模型软限位并同步'})).toBeDisabled();
  await limitEditor.getByRole('checkbox').check();
  await limitEditor.getByRole('button',{name:'保存模型软限位并同步'}).click();
  await expect(limitEditor).toContainText('读回一致');
  await expect(panel.locator('.calibration-ranges')).toContainText('-75.0° ～ 80.0°');
  await expect(panel.locator('.calibration-ranges .effective')).toContainText('-5.0° ～ 5.0°');
  await limitEditor.locator('summary').click();
  await panel.getByLabel('工作正限位').fill('6');
  await expect(panel).toContainText('工作限位超出实测覆盖');
  await panel.getByRole('checkbox',{name:'这些点为当前设备人工实测，方向、零位及范围已复核'}).check();
  await expect(panel.getByRole('button',{name:'确认保存到 ESP32 并读回'})).toBeDisabled();
  await panel.getByLabel('工作正限位').fill('4');
  await expect(panel.getByRole('checkbox',{name:'这些点为当前设备人工实测，方向、零位及范围已复核'})).not.toBeChecked();
  await expect(panel.locator('.calibration-ranges .effective')).toContainText('-5.0° ～ 4.0°');
  await panel.getByRole('checkbox',{name:'这些点为当前设备人工实测，方向、零位及范围已复核'}).check();
  await panel.getByRole('button',{name:'确认保存到 ESP32 并读回'}).click();
  await expect(panel.getByRole('status')).toContainText('读回一致');
  expect(calls).toContain('begin');expect(calls).toContain('target');expect(calls.indexOf('end')).toBeLessThan(calls.indexOf('save'));
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setSize(1100,850));
  await page.screenshot({path:path.resolve(__dirname,'../test-results/calibration-workbench.png')});
  await panel.getByRole('button',{name:'下一步：验证角度'}).click();
  await panel.getByRole('checkbox',{name:'已断开传动或支撑机构，确认第一帧脉宽'}).check();
  await panel.getByRole('button',{name:'开启选中舵机'}).click();
  await panel.getByLabel('人工角度读数').fill('0.2');
  await expect(panel.getByRole('button',{name:'记录人工测量'})).toBeDisabled();
  await panel.getByRole('button',{name:'按已保存标定试转'}).click();
  await panel.getByLabel('人工角度读数').fill('0.2');
  await panel.getByRole('button',{name:'记录人工测量'}).click();
  await expect(panel).toContainText('最大绝对误差 0.20°');
  await panel.getByLabel('标定试转角度').fill('1');
  await panel.getByLabel('人工角度读数').fill('1');
  await expect(panel.getByRole('button',{name:'记录人工测量'})).toBeDisabled();
  await panel.getByLabel('标定试转角度').fill('5');
  await expect(panel.getByRole('button',{name:'按已保存标定试转'})).toBeDisabled();
  await expect(panel).toContainText('目标必须位于设备当前有效范围内');
  await panel.getByRole('button',{name:'关闭输出',exact:true}).click();
  await panel.getByLabel('调试关节').selectOption('2');
  await expect(panel.getByRole('button',{name:/^3.*采集角度/})).toBeDisabled();
  await expect(panel.getByRole('checkbox',{name:'已断开传动或支撑机构，确认第一帧脉宽'})).not.toBeChecked();
  await panel.getByLabel('调试关节').selectOption('1');
  await panel.getByRole('button',{name:/^4.*限位与保存/}).click();
  await expect(panel.getByLabel('工作正限位')).toHaveValue('4');
  // Load the actual device mapping, then widen only the work limit within coverage.
  await panel.getByText('草稿、备份与设备数据',{exact:true}).click();
  await panel.getByRole('button',{name:'用设备值替换草稿'}).click();
  await panel.getByLabel('工作正限位').fill('5');
  await panel.getByRole('checkbox',{name:'这些点为当前设备人工实测，方向、零位及范围已复核'}).check();
  await panel.getByRole('button',{name:'确认保存到 ESP32 并读回'}).click();
  await panel.getByRole('button',{name:'下一步：验证角度'}).click();
  await expect(panel).toContainText('设备版本 2 的验证记录 0 次');
  // Invalid imports do not crash rendering or overwrite the device.
  await panel.getByLabel('导入当前轴草稿',{exact:true}).setInputFiles({name:'bad.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({schema_version:1,axes:{1:{points:[null],readings:[],low:-5,high:5,load:''}}}))});
  await expect(panel.getByRole('alert')).toContainText('当前轴草稿无效');
  await expect(panel).toContainText('设备版本 2');
  const overflow=await panel.evaluate(el=>el.scrollWidth>el.clientWidth);
  expect(overflow).toBe(false);
  await page.getByRole('tab',{name:'通信',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'实机调试'})).toContainText('SDA → GPIO8');
  expect(errors).toEqual([]);
 }finally{await app.close();}
});
