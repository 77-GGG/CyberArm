# CyberArmFirmware

ESP32-S3 上位机通信固件的应用层库。入口文件只负责调用库；具体职责拆分为：

- `FirmwareConfig`：协议、机械臂范围、控制周期和公共数据结构。
- `ServoSubsystem`：PCA9685 输出、舵机标定和 NVS 持久化。
- `MotionController`：手动运动、轨迹缓存、启停和看门狗状态。
- `CommandProtocol`：USB CDC JSONL 协议解析及状态应答。
- `CyberArmFirmware`：初始化和主循环调度。

0.3.0 增加独立单轴测试租约、多点角度映射与 ARMING 过渡互斥。旧三脉宽标定不自动认证为实测映射。

接线配置唯一入口为 [config/wiring.json](../../config/wiring.json)，PlatformIO 编译前校验并生成 WiringConfig.h。使用流程及兼容性见 [单轴标定与 JSON 接线说明](../../docs/单轴标定与JSON接线使用说明_20260917.md)。
