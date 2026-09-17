# CyberArm Electron 桌面应用

## 0.7.0 界面与实机调试

顶栏按“项目、模式、工作区、调试、设置、帮助”组织。操作模式只保留手动控制和自动运行：手动控制负责实时试摆和记录姿态，自动运行动作序列的预览与执行。原示教模式已经合并到手动控制。`调试 → 实机调试` 按连接与安全、回中与限位、运动测试、通信、视觉五步组织；命令控制台仍是可拖动、可拉伸的小浮窗。

界面结构、180° 舵机回中、逐轴标定、联动测试、通信方案与故障表见 [上位机界面与实机调试手册](../docs/上位机界面与实机调试_20260917.md)。

## Windows 安装与自动更新

执行 `npm run build:win` 会生成当前版本的 NSIS 安装程序（本版为 `dist/CyberArm-Studio-Setup-0.7.0-x64.exe`）、差分更新文件和 `latest.yml`。Windows 安装版启动后检查 GitHub Releases，也可通过“帮助 → 检查更新”手动检查；下载完成后，安装流程会先停止运动、断开实机串口并关闭本地后端。完整构建、发布和双版本升级验收流程见 [Windows 安装与自动更新](../docs/Windows安装与自动更新_20260916.md)。

开发模式和自动化测试不启用自动更新。当前安装程序未使用受信任的代码签名，Windows 可能显示“未知发布者”。

## 0.5.0 实机同步控制

`调试 → 实机调试` 可以连接 ESP32-S3 的 USB CDC 串口，逐路保存脉宽/方向校准、测试单路中位并显式使能实机跟随。使能后，手动目标和经过碰撞检查的规划轨迹会同时发送到实体机械臂；计划动作先完整上传，再由上位机和 ESP32-S3 按共同启动时刻及 20 ms 周期运行。连接本身不会输出 PWM，六路未全部校准时不能使能。

固件入口位于 `src/main.cpp`，各功能模块位于 `lib/CyberArmFirmware/src`。目标板是 `esp32-s3-devkitc-1`，默认 PCA9685 地址 `0x40`、SDA GPIO8、SCL GPIO9、通道 0–5 对应 J1–J5/G。依赖和 USB CDC 编译开关见 `platformio.ini`。完整接线、回中、校准、命令和已知限制见 [实机同步控制](../docs/实机同步控制_20260916.md)。普通三线舵机没有位置回读，软件显示的是指令角；实测角仍为空。

## 0.4.0 命令控制台

`调试 → 命令控制台`。默认小浮窗，标题栏可拖动、右下角可拉伸，位置与大小在本次会话内保留。支持 27 个命令、参数帮助、历史、补全和结构化结果。输入 `help` 查看列表，`status` 查询状态，`joint 1 3` 调整底座。命令复用原有运动校验；手动模式仍默认关闭路径显示。

`npm run build:console` 输出独立新版 `desktop/dist/console/win-unpacked/CyberArm Studio.exe`，保留旧版本。外部 CLI 连接控制台显示的本地服务 URL（桌面端口每次启动可能变化）：

```powershell
# 在仓库根目录运行；将端口替换为控制台所示端口
simulator/.venv/Scripts/python.exe simulator/sdk/cyberarm_cli.py --url http://127.0.0.1:实际端口
```

完整命令、Python SDK 和本地 API 见 [控制台与通信接口](../docs/控制台与通信接口_20260915.md)。实机串口和固件已实现；真实舵机角度反馈仍需外加传感器或更换可读位置的舵机。

## 0.3.0 浅色工作台

手动模式默认不显示路径，调关节、夹爪或拖动末端即可更新当前仿真姿态；姿态记录也在手动模式完成。自动运行用于路径预览、动作序列检查与执行。所有操作、说明与状态集中在固定区域。

运行 `npm run build:workbench`，新版输出到 `desktop/dist/workbench/win-unpacked/CyberArm Studio.exe`，保留下述旧版目录。完整说明见 [浅色工作台与手动控制](../docs/浅色工作台与手动控制_20260915.md)。

## 0.2.0 末端实时试摆版

默认显示末端操作轴，拖动或输入坐标即可实时求解并联动模型。目标姿态通过检查后，仍需“预览路径 → 执行”。无解或姿态干涉时保留最后有效试摆姿态并显示偏差。

使用 `npm run build:tcp` 构建到独立目录 `desktop/dist/live-tcp/win-unpacked`，保留旧程序 `desktop/dist/win-unpacked`。新版入口是 `desktop/dist/live-tcp/win-unpacked/CyberArm Studio.exe`。

旧版源码标签：`backup/pre-live-tcp-20260915`（提交 `c9d2371`）。详细设计、限制与验证见 [末端实时试摆记录](../docs/末端实时试摆_20260915.md)。

桌面版直接加载 simulator/frontend 的生产构建，所有模拟 API、WebSocket、运动学、碰撞检查、动作编排和模型均复用 simulator。没有复制或另写桌面专用控制页面。

## 运行 Windows 版本

正式使用时运行 `desktop/dist/CyberArm-Studio-Setup-0.7.0-x64.exe` 完成安装。开发验收也可以打开 `desktop/dist/win-unpacked/CyberArm Studio.exe`；免安装目录必须整体保留，仅作为开发测试产物，不作为自动更新交付方式。用户机器无需另外安装 Python、Node.js 或 C++ 开发工具。

## 开发运行

在仓库根目录准备 simulator/.venv 和 C++ 核心，Python 版本采用 3.12：

```powershell
uv venv simulator/.venv --python 3.12
uv pip install --python simulator/.venv/Scripts/python.exe -r desktop/requirements-build.txt
cmake -S simulator/core -B simulator/core/build
cmake --build simulator/core/build --config Release
cd simulator/frontend
npm ci
npm run build
cd ../../desktop
npm ci
npm start
```

已有环境不需要重新创建。Windows 使用已安装的 C++ 编译器配置 CMake；本机已配置为 MinGW。切换生成器应另建构建目录，不能混用旧缓存。macOS/Linux 的 Python 可执行路径为 `.venv/bin/python`。

## 构建与测试

在 desktop 目录执行：

```powershell
npm run build:dir
npm test
$env:CYBERARM_TEST_EXECUTABLE = (Resolve-Path 'dist/win-unpacked/CyberArm Studio.exe').Path
npm test
Remove-Item Env:CYBERARM_TEST_EXECUTABLE
```

`build:dir` 构建前端、编译并检查 C++ 核心，打包完整 Python 后端目录，复制模型及碰撞数据，再生成 Electron 应用。任一步失败会停止。npm 依赖使用 package-lock.json；Python 直接依赖版本见 requirements-build.txt，完整跨平台依赖锁及 CI 尚待后续发布阶段补齐。

自动测试会打开并关闭专用 Electron 窗口。导出测试用指定文件路径替代原生保存对话框，不测试系统对话框本身。测试截图和日志位于 test-results。自动更新测试覆盖安装版限制、检查、下载确认、任务栏进度和退出安装调用；真实覆盖升级仍需要两个已发布版本验收。

## 使用行为

- 模型视图、关节/夹爪、末端、速度、动作序列、场景、项目 JSON、运行记录与快捷键沿用网页版。
- 项目仍由“项目 → 导出项目”显式保存；关闭不会自动保存未导出的动作，与网页版一致。
- 导出会显示系统保存对话框；导入使用相同 JSON 校验，重新导入必须重新预览后才能执行。
- 应用菜单提供重新连接、退出；重新连接相当于刷新网页，会清空未导出的前端编辑状态。运行中会先请求暂停。
- 重复启动聚焦已有窗口。关闭时停止模拟并清理本应用创建的后端/规划进程；异常退出由后端父进程监控清理。
- 日志在 Electron userData 目录的 desktop.log，“帮助 → 关于”显示绝对路径。

Windows NSIS 安装和应用内更新已实现。Windows 代码签名、两个真实 Release 之间的覆盖升级验收，以及 macOS/Linux 的签名、构建和更新仍需后续完成。
