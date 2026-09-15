# CyberArm Electron 桌面应用

## 0.3.0 浅色工作台

手动模式默认不显示路径，调关节、夹爪或拖动末端即可更新当前仿真姿态。顶部可切换手动、示教和自动控制；需要规划时显式开启路径预览。所有操作、说明与状态集中在固定区域。

运行 `npm run build:workbench`，新版输出到 `desktop/dist/workbench/win-unpacked/CyberArm Studio.exe`，保留下述旧版目录。完整说明见 [浅色工作台与手动控制](../docs/浅色工作台与手动控制_20260915.md)。

## 0.2.0 末端实时试摆版

默认显示末端操作轴，拖动或输入坐标即可实时求解并联动模型。目标姿态通过检查后，仍需“预览路径 → 执行”。无解或姿态干涉时保留最后有效试摆姿态并显示偏差。

使用 `npm run build:tcp` 构建到独立目录 `desktop/dist/live-tcp/win-unpacked`，保留旧程序 `desktop/dist/win-unpacked`。新版入口是 `desktop/dist/live-tcp/win-unpacked/CyberArm Studio.exe`。

旧版源码标签：`backup/pre-live-tcp-20260915`（提交 `c9d2371`）。详细设计、限制与验证见 [末端实时试摆记录](../docs/末端实时试摆_20260915.md)。

桌面版直接加载 simulator/frontend 的生产构建，所有模拟 API、WebSocket、运动学、碰撞检查、动作编排和模型均复用 simulator。没有复制或另写桌面专用控制页面。

## 直接运行 Windows 独立版

构建完成后打开 `desktop/dist/win-unpacked/CyberArm Studio.exe`。必须保留整个 win-unpacked 目录；不能只复制这个 EXE。用户机器无需另外安装 Python、Node.js 或 C++ 开发工具。当前产物是独立应用目录，不是安装程序。

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

自动测试会打开并关闭专用 Electron 窗口。导出测试用指定文件路径替代原生保存对话框，不测试系统对话框本身。测试截图和日志位于 test-results。`npm run build:win` 留作后续生成 NSIS 安装包的入口，本轮以独立应用功能一致性为验收目标。

## 使用行为

- 模型视图、关节/夹爪、末端、速度、动作序列、场景、项目 JSON、运行记录与快捷键沿用网页版。
- 项目仍由“项目 → 导出项目”显式保存；关闭不会自动保存未导出的动作，与网页版一致。
- 导出会显示系统保存对话框；导入使用相同 JSON 校验，重新导入必须重新预览后才能执行。
- 应用菜单提供重新连接、退出；重新连接相当于刷新网页，会清空未导出的前端编辑状态。运行中会先请求暂停。
- 重复启动聚焦已有窗口。关闭时停止模拟并清理本应用创建的后端/规划进程；异常退出由后端父进程监控清理。
- 日志在 Electron userData 目录的 desktop.log，“帮助 → 关于”显示绝对路径。

当前是模拟模式。应用内自动更新、签名、公证和安装升级验收不属于本轮已实现功能。macOS/Linux 配置与资源路径已预留，但尚未在对应系统构建和验证。
