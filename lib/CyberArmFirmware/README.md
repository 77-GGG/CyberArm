# CyberArmFirmware

ESP32-S3 上位机通信固件的应用层库。入口文件只负责调用库；具体职责拆分为：

- `FirmwareConfig`：协议、机械臂范围、控制周期和公共数据结构。
- `ServoSubsystem`：PCA9685 输出、舵机标定和 NVS 持久化。
- `MotionController`：手动运动、轨迹缓存、启停和看门狗状态。
- `CommandProtocol`：USB CDC JSONL 协议解析及状态应答。
- `CyberArmFirmware`：初始化和主循环调度。

模块拆分不改变串口协议、运动参数、标定存储键或安全行为。
