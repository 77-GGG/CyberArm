# mechanical 文件索引

2026-09-14 当前开发顺序：用户确认先完成上位机与模拟控制器验证，再进入打印准备。RevC 为待验证机械基线，允许按软件与结构核验结果修改；现有 STL 不代表已批准整机打印。后续几何变化须同步生成新版本打印件，详见 [系统设计](../docs/CyberArm_设计文档.md)。

整理日期：2026-09-08。只分类归档，没有删除模型或原始资料。旧版本不能与当前打印件混用。

## 从这里开始

- [新建打印文件夹：数量与试装分类](E:/CyberArm/mechanical/打印/README_打印前必读.md)
- [当前 RevC Blender 装配](E:/CyberArm/mechanical/arduino_reference_revC/Arduino_Replica_RevC_Connections.blend)
- [RevC 连接与试装说明](E:/CyberArm/mechanical/arduino_reference_revC/ASSEMBLY_RevC_zh.md)
- [RevC 连接图册](E:/CyberArm/mechanical/arduino_reference_revC/connections.html)
- [最新结构、载荷与电流复核](E:/CyberArm/mechanical/arduino_reference_revC/audit_20260907/结构载荷与电流复核_20260907.md)

当前仍是接口试装版，未通过实物整机装配、承载、长期温升与全行程验证；不要把归档或网格检查通过理解为可以直接量产。

## 目录用途

| 目录 | 内容 |
|---|---|
| `打印/` | 当前 RevC 的完整打印件、先打印的接口试装片、无独立试片的完整件分类副本；有打印数量和来源校验，不混入旧版或五金模型 |
| `arduino_reference_revC/` | 当前版本：主模型、毫米 STL、试装片、连接图册及复核报告；保留原路径和内部配套结构 |
| `scripts/` | 48 个建模、转换、检查、导出和 MCP 启动脚本；路径引用已同步调整 |
| `logs/` | 17 个零散的构建、启动、联动和检查日志 |
| `inspection_data/` | 零散舵机尺寸、几何检查 JSON |
| `archive/arduino_reference_replica/` | 最初的参考机械臂复刻版，含当时模型、截图和检查结果 |
| `archive/arduino_reference_revB/` | RevB 历史版本，不与 RevC 接口混用 |
| `archive/blender_arm_v2/`～`blender_arm_v4/` | 早期自主设计方案及完整版本内输出 |
| `archive/fusion_v1/` | 最早 Fusion 模型、STEP、STL/3MF、截图及原说明书 |
| `archive/backups/RevC/` | 整理前的 RevC `.blend1` 备份；Blender 后续保存可能在主文件旁生成新的备份 |
| `archive/caches/` | 历史 Python 缓存，保留未删除 |
| `archive/_整理记录/20260908/` | 303 个文件的原位置/新位置、SHA256 校验和路径更新前的 37 个脚本原文 |
| `fusion_reference_review/` | Fusion 审查与 MG996R 转换辅助资料；当前重建脚本仍使用其中的舵机/螺丝源网格，故保留原路径 |
| `MG996R Servo Motor/` | 你提供的 MG996R 原始 SolidWorks 文件，未改动 |
| `servo配件/` | 你提供的舵盘原始文件，未改动 |
| `伺服电机模型_ mg90S_ Tower Pro(Servo_爱给网_aigei_com/` | 你提供的 MG90S 原始模型，未改动 |

历史版本内的图片、JSON、STL 和主模型整包保留，避免拆散相对链接。历史 JSON、日志及 Blender 内的来源备注可能记录生成时的旧绝对路径，它们作为历史证据未改写；请用 `move_manifest.json` 查找新位置。历史 `.blend` 的保存路径也应在再次编辑时确认，避免重新在根目录生成旧文件夹。

## 恢复与继续工作

当前 RevC 主模型和原始舵机/舵盘资料均未移动。生成脚本现在统一位于 `E:/CyberArm/mechanical/scripts/`；命令行请使用新路径。

旧位置到新位置的映射在 `archive/_整理记录/20260908/move_manifest.json`。脚本修改前的原文在同级 `original_scripts/`；只调整了路径，没有重跑建模或覆盖模型。整理过程中没有执行生成、安装插件、修改设置或重写模型的脚本。

注意：`scripts/organize_20260908.ps1` 是本次单次迁移记录用脚本，不要重复执行 `Move`；它会在发现目标已存在时拒绝覆盖。

复核摘要：在 PLA Basic、全舵机 5 V 条件下，当前尚不能给出可靠的全范围额定夹取质量；建议先处理底座固定/关节支承。六舵机按 10.5 A 峰值作选型预算，建议独立 5 V / 15 A 电源，但不等于实测最大电流；详见上面的复核报告。
