# CyberArmFirmware

ESP32-S3 上位机通信固件的应用层库。入口文件只负责调用库；具体职责拆分为：

- `FirmwareConfig`：协议、机械臂范围、控制周期和公共数据结构。
- `ServoSubsystem`：PCA9685 输出、舵机标定和 NVS 持久化。
- `MotionController`：手动运动、轨迹缓存、启停和看门狗状态。
- `CommandProtocol`：USB CDC JSONL 协议解析及状态应答。
- `CyberArmFirmware`：初始化和主循环调度。

0.3.0 增加独立单轴测试租约、多点角度映射与 ARMING 过渡互斥。旧三脉宽标定不自动认证为实测映射。

0.4.0 增加可编辑模型软限位，能力字段 `capabilities.editable_limits=1`。`model_limits_deg` 和 `limits_revisions` 回报六轴设备参数。`FirmwareConfig.h` 的范围仅作为 NVS 尚无有效配置时的默认值。

0.4.1 将高频 `heartbeat` 和 `test_renew` 改为精简运行状态回包，减少 USB CDC 阻塞；完整设备配置仍在握手和参数变更响应中回报。主机允许一次心跳瞬时超时，并在单轴调试时降低独立心跳频率，固件的 1.2 秒调试租约和 1.5 秒运动看门狗保持不变。

0.4.2 把 USB CDC 接收队列从默认 256 字节提升到 4096 字节。此前超过队列长度的请求会在中断里被静默丢弃，JSON 行被截断后既不回包也不报错，`save_mapping`（约 320 字节）因此必定失败并让上位机超时断开。协议、命令集与限位/标定格式均未改变。

`save_limits` 参数：`axis`（0–5）、`low_deg`、`high_deg`、`expected_revision`、`confirmed:true`、`model_id`、`wiring_hash`。仅 DISARMED 且输出关闭时可保存，要求 −180 ≤ low < 0 < high ≤ 180。每轴以单个 NVS blob 保存，绑定模型及接线摘要，递增版本并读回核对；无效值、版本冲突或存储失败拒绝。模型软限位不会替代实测工作限位，arm/target/trajectory 均使用运行时范围。

操作与零位参考见 [单轴调试操作手册](../../docs/单轴调试操作手册_20260918.md)。软件可以编辑范围，但不能检测舵机物理端点或回传三线舵机真实位置。

接线配置唯一入口为 [config/wiring.json](../../config/wiring.json)，PlatformIO 编译前校验并生成 WiringConfig.h。使用流程及兼容性见 [单轴标定与 JSON 接线说明](../../docs/单轴标定与JSON接线使用说明_20260917.md)。
