const {test,expect,_electron:electron}=require('@playwright/test');
const path=require('node:path');
const fs=require('node:fs');

test('命令控制台：查询、校验、运动、历史与小窗口',async()=>{
 const output=path.resolve(__dirname,'../test-results/console');fs.mkdirSync(output,{recursive:true});
 const env={...process.env,CYBERARM_TEST_USER_DATA:path.join(output,'user')};delete env.ELECTRON_RUN_AS_NODE;
 const packaged=process.env.CYBERARM_TEST_EXECUTABLE;
 const app=await electron.launch({...(packaged?{executablePath:packaged,args:[]}:{args:[path.resolve(__dirname,'..')]}),env});
 try{
  const page=await app.firstWindow();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await expect(page.locator('.connection')).toContainText('本地已连接',{timeout:60000});
  await expect(page.locator('.scene-stage')).toHaveAttribute('data-model-status',/已载入/,{timeout:60000});
  await page.getByRole('button',{name:'关节',exact:true}).click();
  const openConsole=async()=>{
   await page.getByRole('button',{name:'调试',exact:true}).click();
   await page.getByRole('button',{name:'命令控制台',exact:true}).click();
  };
  await openConsole();
  const panel=page.getByRole('dialog',{name:'命令控制台'}),stage=await page.locator('.scene-stage').boundingBox();
  const initial=await panel.boundingBox();
  expect(initial.width*initial.height).toBeLessThan(stage.width*stage.height*.45);
  await page.screenshot({path:path.join(output,'console-floating.png')});
  const drag=await page.getByRole('button',{name:'移动控制台'}).boundingBox();
  await page.mouse.move(drag.x+50,drag.y+15);await page.mouse.down();
  await page.mouse.move(drag.x+150,drag.y-55,{steps:8});await page.mouse.up();
  const moved=await panel.boundingBox();
  expect(moved.x).toBeCloseTo(initial.x+100,0);expect(moved.y).toBeCloseTo(initial.y-70,0);
  const resize=await page.getByRole('button',{name:'调整控制台大小'}).boundingBox();
  await page.mouse.move(resize.x+8,resize.y+8);await page.mouse.down();
  await page.mouse.move(resize.x+68,resize.y+48,{steps:8});await page.mouse.up();
  const resized=await panel.boundingBox();
  expect(resized.width).toBeCloseTo(moved.width+60,0);expect(resized.height).toBeCloseTo(moved.height+40,0);
  const input=page.getByLabel('控制台命令');
  const run=async(line)=>{await input.fill(line);await input.press('Enter');await expect(input).toBeEnabled({timeout:60000});};
  await run('help');await expect(page.getByRole('log')).toContainText('movej');
  await run('status');await expect(page.getByRole('log')).toContainText('simulation');
  await run('joint 1 3');await expect(page.getByLabel('底座旋转目标角度')).toHaveValue('3');
  await run('grip 1');await expect(page.getByLabel('夹爪开合目标角度')).toHaveValue('1');
  await run('joint 1 90');await expect(page.locator('.console-entry').last()).toContainText('错误 422');
  await expect(page.getByLabel('底座旋转目标角度')).toHaveValue('3');
  await input.press('ArrowUp');await expect(input).toHaveValue('joint 1 90');
  await input.fill('sta');await input.press('Tab');await expect(input).toHaveValue('status ');
  await run('movej 4 0 0 0 0 1');
  await expect.poll(()=>page.evaluate(()=>fetch('/api/state').then(r=>r.json()).then(s=>s.q_deg[0]))).toBeCloseTo(4,2);
  await expect.poll(()=>page.evaluate(()=>fetch('/api/state').then(r=>r.json()).then(s=>s.execution?.status))).toBe('completed');
  await expect(page.getByLabel('显示路径预览')).not.toBeChecked();
  await page.getByRole('button',{name:'关闭控制台'}).click();
  await openConsole();
  expect(await panel.boundingBox()).toEqual(resized);
  await expect(page.getByRole('log')).toContainText('joint 1 90');
  await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows()[0].setSize(960,720));
  await expect(input).toBeInViewport();await expect(page.getByTitle('停止 Esc')).toBeInViewport();
  const small=await panel.boundingBox(),smallStage=await page.locator('.scene-stage').boundingBox();
  expect(small.x+small.width).toBeLessThanOrEqual(smallStage.x+smallStage.width);
  expect(small.y+small.height).toBeLessThanOrEqual(smallStage.y+smallStage.height);
  // Keyboard movement and sizing remain available after the window shrinks.
  await page.getByRole('button',{name:'移动控制台'}).focus();
  await page.keyboard.press('ArrowUp');
  await page.getByRole('button',{name:'调整控制台大小'}).focus();
  await page.keyboard.press('ArrowLeft');
  await page.screenshot({path:path.join(output,'console-960.png')});
  await run('clear');await expect(page.locator('.console-entry')).toHaveCount(0);
  expect(errors).toEqual([]);
 }finally{await app.close();}
});
