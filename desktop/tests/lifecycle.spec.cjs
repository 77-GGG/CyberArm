const {test,expect,_electron:electron}=require('@playwright/test');
const {spawn}=require('node:child_process');
const path=require('node:path');
test('重复启动不创建第二个服务，主进程异常退出后清理后端',async()=>{
  const packaged=process.env.CYBERARM_TEST_EXECUTABLE;
  const env={...process.env,CYBERARM_TEST_USER_DATA:path.resolve(__dirname,'../test-results/lifecycle-user')};
  delete env.ELECTRON_RUN_AS_NODE;
  const args=packaged?[]:[path.resolve(__dirname,'..')];
  const app=await electron.launch({...(packaged?{executablePath:packaged}:{}),args,env});
  let killed=false;
  try {
    const page=await app.firstWindow();
    await expect(page.locator('.connection')).toContainText('本地已连接',{timeout:60000});
    await page.getByRole('button',{name:'模式',exact:true}).click();
    await page.getByRole('button',{name:'自动运行',exact:true}).click();
    await page.getByRole('button',{name:'关闭面板'}).click();
    await page.getByRole('button',{name:'关节',exact:true}).click();
    const url=page.url();
    const second=spawn(packaged||require('electron'),args,{env,windowsHide:true,stdio:'ignore'});
    const code=await new Promise((resolve,reject)=>{second.on('error',reject);second.on('exit',resolve);});
    expect(code).toBe(0);
    expect((await fetch(new URL('/api/state',url))).status).toBe(200);
    await page.getByRole('button',{name:'预览路径',exact:true}).click();
    await expect(page.locator('.feedback')).toContainText('预览通过',{timeout:90000});
    const mainPid=await app.evaluate(()=>process.pid);
    process.kill(mainPid,'SIGKILL');killed=true;
    await expect.poll(async()=>{try{await fetch(new URL('/api/state',url),{signal:AbortSignal.timeout(1000)});return false;}catch{return true;}},{timeout:15000}).toBe(true);
  } finally {if(!killed)await app.close();}
});
