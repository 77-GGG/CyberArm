# CyberArm 品牌图标

`cyberarm-icon.png` 是项目和 CyberArm Studio 上位机共用的 1024×1024 主图标。

图形以三个关节、机械臂和夹爪构成，使用白色玻璃底板与工业蓝色主体。外部透明区域便于适配项目主页、文档、启动器和安装程序。

派生文件：

- `desktop/assets/icon.ico`：Windows 安装程序、可执行文件和快捷方式的多尺寸图标。
- `desktop/assets/icon.png`：Electron 窗口图标。
- `simulator/frontend/public/icon.png`：浏览器和开发页面图标。

需要从新的主图重新生成时，在仓库根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File desktop/scripts/generate-icons.ps1 -Source <主图路径>
```
