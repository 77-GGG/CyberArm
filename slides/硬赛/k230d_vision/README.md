# k230d_vision —— K230D 人脸识别视觉模块

供硬件设计大赛机器人项目使用：**CanMV K230D（BPI-CanMV-K230D-Zero）独立做人脸识别，结果经 UART 发给 ESP32-S3**。

## 文件清单

| 文件 | 运行平台 | 说明 |
|---|---|---|
| `K230D人脸识别落地指南.md` | - | 主文档：硬件/环境/原理/三步走计划/风险对策 |
| `protocol.md` | - | K230D ↔ ESP32 串口帧协议 v1.0（含校验能力实测数据） |
| `face_recognition_lite_uart.py` | K230D CanMV | 识别主程序（官方 lite 版 + K230D 分辨率适配 + UART 上报 + 去抖/心跳） |
| `face_register_avg.py` | K230D CanMV | 人脸注册（多张照片平均特征，输出 db/<名字>.bin） |
| `esp32_face_listener/esp32_face_listener.ino` | ESP32-S3 | 收帧解析 + 心跳看门狗 + 面向人脸转向的控制骨架 |
| `tools/protocol_sim.py` | 电脑 | 协议交叉验证：K230D 组帧逻辑 ↔ ESP32 解析逻辑对打，16 项测试 |
| `tools/verification_log.txt` | - | 最近一次验证输出（16 passed, 0 failed） |
| `reference/` | - | 嘉楠官方原版示例（face_detection / face_registration_lite / face_recognition_lite） |

## 已验证 / 待验证状态

**已完成（本机可验证的全部项）**
- [x] 官方轻量人脸识别流程梳理：`face_registration_lite` + `face_recognition_lite`（K230D 适配参数来自官方注释）
- [x] 两侧代码语法检查通过（py_compile）；可与官方示例逐行对照
- [x] 协议交叉验证 16/16 通过：组帧↔解析字节级一致、粘包/逐字节/噪声/坏校验 fuzz（详见 `protocol.md` §5.1）

**待硬件验证（需要你在板子上做，见 `K230D人脸识别落地指南.md` M1/M2/M3）**
- [ ] 刷固件后跑通 `reference/face_detection.py`（K230D 改显示模式+分辨率）
- [ ] 注册人脸库并测试识别效果、调阈值
- [ ] 排针 8/10 串口接线后 `fpioa.help(FPIOA.UART1_TXD, func=True)` 核验引脚映射
- [ ] USB-TTL 抓包核对帧格式 → 连 ESP32 联调

## 最快上手路径

```
1. 刷固件（TF 卡） → 两根 USB 线接电脑，CanMV IDE 连 REPL
2. 跑 reference/face_detection.py        → 确认摄像头/模型/显示 OK
3. 照片放 /sdcard/examples/utils/db_img/  → 跑 face_register_avg.py
4. 跑 face_recognition_lite_uart.py      → 电脑 USB-TTL 接排针 8/10 看帧
5. ESP32 烧 esp32_face_listener.ino      → 联调
```

## 关键事实（避免踩坑）

- K230D 内存 128MB，**只能用轻量版**人脸识别（`face_recognition_lite` / `face_registration_lite`）；完整版 `face_recognition.py` 跑不了。
- 无显示屏运行时：`display_mode="virt"`，`display_size=[640,360]`；有 MIPI 屏用 `"lcd"`。
- 官方建议 K230D 上将 AI 输入分辨率降到 `[640,360]`。
- 串口：排针 8/10 是干净的 UART1（GPIO3/4）；**避开** 3/5、27/28（与 CSI IIC 共用）。
- 供电：K230D 需 5V/2A，另接 DC-DC，与 ESP32 共地。

## 联系方式/资料

- 嘉楠 CanMV 文档：https://www.kendryte.com/k230_canmv/
- 官方示例源码：https://github.com/kendryte/canmv_k230 （`resources/examples/05-AI-Demo/`）
- 固件下载：https://github.com/kendryte/k230_canmv/releases
