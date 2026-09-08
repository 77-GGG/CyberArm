# 脚本说明

2026-09-08 从 mechanical 根目录归集。相互读取的脚本路径和历史输出目录已迁移；原始舵机目录、当前 RevC 和转换辅助资产的位置不变。

| 类型 | 代表脚本 |
|---|---|
| 当前 RevC 连接建模 | `build_revC_connections.py`、`revC_connections.py` |
| RevC 输出、检查 | `revC_delivery.py`、`revC_finalize.py`、`revC_verify_stl.py` |
| RevC 静力学复核 | `revC_stability_audit.py` |
| 参考复刻与 RevB 辅助 | `assemble_arduino_reference_blender.py`、`refine_reference_blender.py`、`revB_*.py` |
| 早期方案 | `build_blender_arm*.py` 及对应检查、渲染、打包脚本 |
| 舵机/CAD 转换 | `extract_solidworks_display_mesh.py`、`fusion_reference_review.py`、`inspect_*.py` |
| MCP 配套 | `blender_mcp_client.py`、`blender_bootstrap.py`、`start_reference_mcp.py` |

不要一次性运行整个文件夹。多数建模脚本会改变 Blender/Fusion 当前设计，一部分会保存文件，启动脚本还可能安装插件或改变设置。需先看对应脚本的用途和版本，在正确的后台模型副本或指定应用中运行。

`revC_stability_audit.py` 的运行示例（只读入模型、输出复核文件，不保存 .blend）：

```powershell
& 'E:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background 'E:\CyberArm\mechanical\arduino_reference_revC\Arduino_Replica_RevC_Connections.blend' --python 'E:\CyberArm\mechanical\scripts\revC_stability_audit.py'
```

历史脚本未全部重跑；本次以语法、静态路径和当前辅助加载链检查为主，不把整理等同于全部旧功能重新验收。
