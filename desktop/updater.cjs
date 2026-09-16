function plainText(value) {
  if (Array.isArray(value)) {
    value = value.map(item => item?.note || item?.version || '').filter(Boolean).join('\n');
  }
  return String(value || '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 1200);
}

function createUpdateManager({
  app,
  autoUpdater,
  dialog,
  getWindow,
  requestQuitForInstall,
  log,
  platform = process.platform,
  env = process.env,
  schedule = setTimeout,
}) {
  const enabled = app.isPackaged && platform === 'win32' &&
    env.CYBERARM_DISABLE_AUTO_UPDATE !== '1' && !env.CYBERARM_TEST_USER_DATA;
  let checking = false;
  let downloadInProgress = false;
  let manualCheck = false;
  let downloaded = false;
  let installOnQuit = false;

  const writeLog = (level, message) => log(`更新 ${level}：${String(message)}`);
  const messageBox = options => {
    const parent = getWindow();
    return parent ? dialog.showMessageBox(parent, options) : dialog.showMessageBox(options);
  };
  const resetProgress = () => getWindow()?.setProgressBar(-1);

  async function showError(error) {
    const interactive = manualCheck || downloadInProgress;
    checking = false;
    downloadInProgress = false;
    manualCheck = false;
    resetProgress();
    writeLog('失败', error?.stack || error?.message || error);
    if (interactive) {
      await messageBox({
        type: 'error',
        title: '更新失败',
        message: '无法检查或下载更新',
        detail: `${error?.message || error}\n\n请检查网络后重试。`,
      });
    }
  }

  if (enabled) {
    autoUpdater.autoDownload = false;
    autoUpdater.autoInstallOnAppQuit = false;
    autoUpdater.autoRunAppAfterInstall = true;
    autoUpdater.allowPrerelease = false;
    autoUpdater.allowDowngrade = false;
    autoUpdater.disableWebInstaller = true;
    autoUpdater.fullChangelog = false;
    autoUpdater.logger = {
      info: message => writeLog('信息', message),
      warn: message => writeLog('警告', message),
      error: message => writeLog('错误', message),
      debug: message => writeLog('调试', message),
    };

    autoUpdater.on('checking-for-update', () => writeLog('检查', `当前版本 ${app.getVersion()}`));
    autoUpdater.on('update-not-available', async info => {
      const interactive = manualCheck;
      checking = false;
      manualCheck = false;
      writeLog('结果', `已是最新版本 ${info?.version || app.getVersion()}`);
      if (interactive) {
        await messageBox({
          type: 'info',
          title: '检查更新',
          message: '当前已经是最新版本',
          detail: `CyberArm Studio ${app.getVersion()}`,
        });
      }
    });
    autoUpdater.on('update-available', async info => {
      checking = false;
      manualCheck = false;
      writeLog('发现', `版本 ${info.version}`);
      const notes = plainText(info.releaseNotes);
      const result = await messageBox({
        type: 'info',
        title: '发现新版本',
        message: `CyberArm Studio ${info.version} 可以下载`,
        detail: `${notes ? `${notes}\n\n` : ''}是否现在下载更新？下载期间可以继续使用软件。`,
        buttons: ['下载更新', '稍后'],
        defaultId: 0,
        cancelId: 1,
        noLink: true,
      });
      if (result.response !== 0) return;
      downloadInProgress = true;
      try {
        await autoUpdater.downloadUpdate();
      } catch (error) {
        await showError(error);
      }
    });
    autoUpdater.on('download-progress', progress => {
      const fraction = Math.max(0, Math.min(1, Number(progress.percent || 0) / 100));
      getWindow()?.setProgressBar(fraction);
    });
    autoUpdater.on('update-downloaded', async info => {
      downloadInProgress = false;
      downloaded = true;
      resetProgress();
      writeLog('完成', `版本 ${info.version} 已下载`);
      const result = await messageBox({
        type: 'info',
        title: '更新已下载',
        message: `CyberArm Studio ${info.version} 已准备好安装`,
        detail: '安装前会停止当前运动、关闭实机串口并退出本地后端。',
        buttons: ['立即重启安装', '退出软件时安装', '稍后'],
        defaultId: 0,
        cancelId: 2,
        noLink: true,
      });
      installOnQuit = result.response === 0 || result.response === 1;
      if (result.response === 0) requestQuitForInstall();
    });
    autoUpdater.on('error', error => { void showError(error); });
  }

  async function check(interactive = false) {
    if (!enabled) {
      if (interactive) {
        await messageBox({
          type: 'info',
          title: '检查更新',
          message: '自动更新仅在 Windows 安装版中启用',
          detail: `当前版本 ${app.getVersion()}。开发模式和自动化测试不会访问更新服务器。`,
        });
      }
      return false;
    }
    if (checking || downloadInProgress) {
      if (interactive) {
        await messageBox({type: 'info', title: '检查更新', message: '正在检查或下载更新，请稍候。'});
      }
      return false;
    }
    checking = true;
    manualCheck = interactive;
    try {
      await autoUpdater.checkForUpdates();
      return true;
    } catch (error) {
      await showError(error);
      return false;
    }
  }

  function scheduleAutomaticCheck(delayMs = 10000) {
    if (!enabled) return null;
    const timer = schedule(() => { void check(false); }, delayMs);
    timer?.unref?.();
    return timer;
  }

  function shouldInstallOnQuit() {
    return downloaded && installOnQuit;
  }

  function installDownloadedUpdate() {
    if (!shouldInstallOnQuit()) return false;
    writeLog('安装', '退出应用并启动安装程序');
    autoUpdater.quitAndInstall(false, true);
    return true;
  }

  return {enabled, check, scheduleAutomaticCheck, shouldInstallOnQuit, installDownloadedUpdate};
}

module.exports = {createUpdateManager, plainText};
