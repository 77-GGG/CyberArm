# Windows 发布目录

该目录负责将 CyberArm 模拟器构建为 Windows 桌面应用。

## 构建

在仓库根目录运行：

```powershell
packaging/windows/build-windows.ps1
```

脚本依次构建 React 前端、打包 FastAPI sidecar，并使用 electron-builder 生成 NSIS 安装包和便携版。产物位于 `packaging/windows/dist/`。

## 当前更新策略

Electron 主进程支持用户主动检查更新、下载完成通知和安装入口，更新源使用 GitHub Releases。当前 Windows 构建未配置代码签名，首次运行可能出现 SmartScreen 提示。

## 发布前检查

- 运行 `simulator/tests` 和 C++ CTest。
- 确认 `simulator/frontend/dist`、C++ DLL 和 RevC 模型资源存在。
- 确认更新不会覆盖 `%APPDATA%\\CyberArm` 用户数据。
- 先验证便携版启动、关闭、模型加载、规划、停止和更新，再构建 NSIS 安装包。
