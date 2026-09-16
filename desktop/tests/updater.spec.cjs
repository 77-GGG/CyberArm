const {EventEmitter} = require('node:events');
const {test, expect} = require('@playwright/test');
const {createUpdateManager, plainText} = require('../updater.cjs');

class FakeUpdater extends EventEmitter {
  constructor() {
    super();
    this.checkCount = 0;
    this.downloadCount = 0;
    this.installArgs = null;
  }
  async checkForUpdates() {
    this.checkCount += 1;
    this.emit('checking-for-update');
    return {};
  }
  async downloadUpdate() {
    this.downloadCount += 1;
    return ['update.exe'];
  }
  quitAndInstall(...args) { this.installArgs = args; }
}

const flush = () => new Promise(resolve => setImmediate(resolve));

test('开发模式不会访问更新服务器，手动检查会说明安装版限制', async () => {
  const updater = new FakeUpdater();
  const messages = [];
  const manager = createUpdateManager({
    app: {isPackaged:false, getVersion:()=> '0.6.0'},
    autoUpdater: updater,
    dialog: {showMessageBox:async (...args) => {messages.push(args.at(-1)); return {response:0};}},
    getWindow: () => undefined,
    requestQuitForInstall: () => {},
    log: () => {},
    platform: 'win32',
    env: {},
  });
  expect(manager.enabled).toBe(false);
  expect(await manager.check(true)).toBe(false);
  expect(updater.checkCount).toBe(0);
  expect(messages[0].message).toContain('Windows 安装版');
});

test('Windows 安装版确认下载，并在退出前调用 NSIS 安装', async () => {
  const updater = new FakeUpdater();
  const responses = [0, 1];
  const messages = [];
  const progress = [];
  let quitRequests = 0;
  let scheduled;
  const manager = createUpdateManager({
    app: {isPackaged:true, getVersion:()=> '0.6.0'},
    autoUpdater: updater,
    dialog: {showMessageBox:async (...args) => {messages.push(args.at(-1)); return {response:responses.shift()};}},
    getWindow: () => ({setProgressBar:value => progress.push(value)}),
    requestQuitForInstall: () => {quitRequests += 1;},
    log: () => {},
    platform: 'win32',
    env: {},
    schedule: callback => {scheduled = callback; return {unref(){}};},
  });

  expect(manager.enabled).toBe(true);
  manager.scheduleAutomaticCheck();
  expect(typeof scheduled).toBe('function');
  scheduled();
  await flush();
  expect(updater.checkCount).toBe(1);

  updater.emit('update-available', {version:'0.7.0', releaseNotes:'<b>硬件联动改进</b>'});
  await flush();
  await flush();
  expect(messages[0].message).toContain('0.7.0');
  expect(messages[0].detail).toContain('硬件联动改进');
  expect(updater.downloadCount).toBe(1);

  updater.emit('download-progress', {percent:42});
  expect(progress.at(-1)).toBeCloseTo(0.42);
  updater.emit('update-downloaded', {version:'0.7.0'});
  await flush();
  expect(progress).toContain(-1);
  expect(quitRequests).toBe(0);
  expect(manager.shouldInstallOnQuit()).toBe(true);
  expect(manager.installDownloadedUpdate()).toBe(true);
  expect(updater.installArgs).toEqual([false, true]);
});

test('发布说明转换为适合原生对话框的短文本', () => {
  expect(plainText([{version:'0.7.0', note:'<p>A &amp; B</p>'}])).toBe('A & B');
  expect(plainText('x'.repeat(1300))).toHaveLength(1200);
});
