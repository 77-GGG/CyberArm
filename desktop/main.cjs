const { app, BrowserWindow, Menu, dialog } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');
const { autoUpdater } = require('electron-updater');
const { createUpdateManager } = require('./updater.cjs');

let window, backend, origin, session, updateManager, quitting = false, closing = false;
const root = path.resolve(__dirname, '..');
if (process.env.CYBERARM_TEST_USER_DATA && !app.isPackaged) app.setPath('userData', process.env.CYBERARM_TEST_USER_DATA);
const logPath = path.join(app.getPath('userData'), 'desktop.log');
fs.mkdirSync(path.dirname(logPath), { recursive: true });
function log(message) { fs.appendFileSync(logPath, `${new Date().toISOString()} ${message}\n`); }
function launchBackend() {
  const runtime = app.isPackaged ? path.join(process.resourcesPath, 'runtime') : path.join(__dirname, 'stage');
  const staged = app.isPackaged || process.env.CYBERARM_USE_STAGE === '1';
  const python = path.join(root, 'simulator', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const command = staged ? path.join(runtime, 'backend', process.platform === 'win32' ? 'cyberarm-backend.exe' : 'cyberarm-backend') : python;
  const args = staged ? [] : [path.join(__dirname, 'backend_entry.py')];
  return new Promise((resolve, reject) => {
    backend = spawn(command, args, { windowsHide: true, detached:process.platform!=='win32', cwd: app.getPath('userData'),
      env: {...process.env, CYBERARM_PARENT_PID:String(process.pid), PYTHONPATH: path.join(root, 'simulator/backend'), PYTHONIOENCODING: 'utf-8',
        CYBERARM_RESOURCE_DIR: staged ? path.join(runtime, 'simulator') : path.join(root, 'simulator')},
      stdio: ['pipe', 'pipe', 'pipe'] });
    const timeout = setTimeout(() => reject(new Error('后端启动超过 60 秒，请查看日志。')), 60000);
    backend.once('error', e => { clearTimeout(timeout); reject(e); });
    backend.stderr.on('data', d => log(d.toString()));
    readline.createInterface({input: backend.stdout}).on('line', line => {
      log(line);
      try {
        const data = JSON.parse(line);
        if (data.type === 'ready' && Number.isInteger(data.port) && data.port > 0 && data.port < 65536) {
          clearTimeout(timeout); resolve(`http://127.0.0.1:${data.port}`);
        }
      } catch {}
    });
    backend.on('exit', (code) => {
      clearTimeout(timeout);
      reject(new Error(`后端提前退出：${code}`));
      if (origin && !closing && !quitting) {
        dialog.showErrorBox('模拟服务已退出', `请重新打开应用。日志：${logPath}`);
        app.quit();
      }
    });
  });
}
async function post(action) {
  return fetch(origin + '/api/control', {method: 'POST', headers: {'Content-Type':'application/json', 'X-Session':session},
    body: JSON.stringify({action}), signal: AbortSignal.timeout(3000)});
}
async function postHardware(action) {
  return fetch(origin + '/api/hardware/' + action, {method: 'POST', headers: {'Content-Type':'application/json', 'X-Session':session},
    body: '{}', signal: AbortSignal.timeout(3000)});
}
async function stopBackend() {
  if (!backend?.pid) return;
  const child = backend;
  try {
    if (origin && child.exitCode === null) {
      await post('stop');
      for (let i = 0; i < 50; i++) {
        const state = await fetch(origin+'/api/state', {signal: AbortSignal.timeout(1500)}).then(r=>r.json());
        if (!['RUNNING','STOPPING'].includes(state.mode)) break;
        await new Promise(r=>setTimeout(r,100));
      }
      await postHardware('disconnect');
    }
  } catch(e) { log(`停止服务：${e.message}`); }
  // Shut down the whole owned process tree, including active planning workers.
  if (process.platform === 'win32') {
    await new Promise(resolve => {
      const killer = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], {windowsHide:true});
      killer.on('error', resolve); killer.on('exit', resolve);
    });
  } else {
    child.kill('SIGTERM');
    await Promise.race([new Promise(r=>child.once('exit',r)), new Promise(r=>setTimeout(r,5000))]);
    try { process.kill(-child.pid, 'SIGKILL'); } catch(e) { if(e.code!=='ESRCH')throw e; }
  }
  backend = null;
}
function configureDownloads() {
  window.webContents.session.on('will-download', (event, item, contents) => {
    if (contents !== window.webContents || !item.getURL().startsWith('blob:'+origin+'/')) { event.preventDefault(); return; }
    const destination = process.env.CYBERARM_TEST_DOWNLOAD_DIR && !app.isPackaged;
    if (destination) item.setSavePath(path.join(process.env.CYBERARM_TEST_DOWNLOAD_DIR, path.basename(item.getFilename())));
    else item.setSaveDialogOptions({title:'导出 CyberArm 项目', defaultPath:path.join(app.getPath('documents'),path.basename(item.getFilename())), filters:[{name:'项目 JSON',extensions:['json']}]});
    item.once('done', (_, state) => { if(state !== 'completed' && state !== 'cancelled') dialog.showErrorBox('导出失败','请检查目标目录权限并重试。'); });
  });
}
async function start() {
  origin = await launchBackend();
  const bootstrap = await fetch(origin+'/api/bootstrap', {signal:AbortSignal.timeout(10000)}).then(r=>{if(!r.ok)throw new Error('初始化失败');return r.json();});
  session = bootstrap.session;
  window = new BrowserWindow({width:1440,height:960,minWidth:960,minHeight:720,backgroundColor:'#111e2a',show:false,
    icon:path.join(__dirname,'assets','icon.png'),
    webPreferences:{nodeIntegration:false,contextIsolation:true,sandbox:true,backgroundThrottling:false}});
  window.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  window.webContents.on('will-navigate',(e,url)=>{if(new URL(url).origin!==origin)e.preventDefault();});
  window.webContents.session.setPermissionRequestHandler((_,__,callback)=>callback(false));
  configureDownloads();
  window.on('close', e => {if(!quitting){e.preventDefault();app.quit();}});
  updateManager = createUpdateManager({
    app,
    autoUpdater,
    dialog,
    getWindow: () => window,
    requestQuitForInstall: () => app.quit(),
    log,
  });
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    ...(process.platform==='darwin'?[{role:'appMenu'}]:[]),
    {label:'应用',submenu:[{label:'重新连接',click:async()=>{await post('pause').catch(()=>{});window.reload();}}, {label:'退出',click:()=>app.quit()}]},
    {label:'编辑',submenu:[{role:'undo'},{role:'redo'},{type:'separator'},{role:'cut'},{role:'copy'},{role:'paste'},{role:'selectAll'}]},
    {label:'视图',submenu:[{role:'resetZoom'},{role:'zoomIn'},{role:'zoomOut'},{role:'togglefullscreen'}]},
    {label:'帮助',submenu:[{label:'检查更新',click:()=>void updateManager.check(true)},{type:'separator'},{label:'关于',click:()=>dialog.showMessageBox(window,{message:`CyberArm Studio ${app.getVersion()}`,detail:`本地仿真与实机控制\n日志：${logPath}`})}]}
  ]));
  await window.loadURL(origin);
  window.show();
  updateManager.scheduleAutomaticCheck();
}
if(!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance',()=>{if(window){if(window.isMinimized())window.restore();window.show();window.focus();}});
  app.on('before-quit',e=>{
    if(quitting)return;
    e.preventDefault();
    if(closing)return;
    closing=true;
    stopBackend().catch(e=>log(e.stack)).finally(()=>{
      quitting=true;
      if (!updateManager?.installDownloadedUpdate()) app.quit();
    });
  });
  app.on('window-all-closed',()=>app.quit());
  app.whenReady().then(start).catch(async e=>{log(e.stack);dialog.showErrorBox('CyberArm 启动失败',`${e.message}\n日志：${logPath}`);app.quit();});
}
