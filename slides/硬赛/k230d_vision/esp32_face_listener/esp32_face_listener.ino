/*
 * esp32_face_listener.ino
 * =======================
 * ESP32-S3 接收 K230D 人脸识别结果（UART1），解析并驱动动作。
 *
 * 协议：见 k230d_vision/protocol.md（115200-8-N-1，二进制帧，校验和）
 *   AA 55 | TYPE | LEN | PAYLOAD | SUM
 *   0x01 RESULT   : id(u8) score(u8) cx(u16) cy(u16) w(u16) h(u16)
 *   0x02 HEARTBEAT: alive(u8) temp(u8)
 *   0x03 STATUS   : code(u8) n_persons(u8)
 *   0x04 QUERY    : ESP32 -> K230D 查询状态
 *
 * 接线：K230D 排针 8(GPIO3 UART1_TXD) -> ESP32 RX；排针 10 -> ESP32 TX；共地。
 *
 * 依赖：仅 Arduino 核心（无第三方库）。
 * 适配平台：ESP32-S3（其他 ESP32 改引脚定义即可）。
 */

// ------------------------- 配置 -------------------------
static const int    UART_RX_PIN    = 4;   // ESP32-S3 接收 K230D
static const int    UART_TX_PIN    = 5;   // ESP32-S3 发送 K230D
static const uint32_t BAUD         = 115200;
static const uint32_t HEARTBEAT_TIMEOUT_MS = 3000;  // 3s 无心跳判掉线
static const bool   VERBOSE        = true; // 串口打印原始帧

// 动作参数：人脸偏离画面中心多少像素开始转向（画面宽 640，中心 320）
static const int    CENTER_X       = 320;
static const int    DEADBAND_PX    = 30;   // 死区，防抖
static const float  TURN_KP        = 0.05f;// 比例系数，先保守，整车调试再调
// ------------------------------------------------

// ------------------------- 协议 -------------------------
enum { P_SYNC0 = 0xAA, P_SYNC1 = 0x55,
       P_RESULT = 0x01, P_HEARTBEAT = 0x02, P_STATUS = 0x03, P_QUERY = 0x04 };

// 状态机
enum { S_IDLE, S_SYNC1, S_TYPE, S_LEN, S_PAYLOAD, S_CHECKSUM };
uint8_t  rxState = S_IDLE;
uint8_t  rxType, rxLen, rxSum, rxIdx;
uint8_t  rxBuf[64];

// 解析结果
struct FaceResult { uint8_t id; uint8_t score; uint16_t cx, cy, w, h; bool valid; };
FaceResult face     = {0xFF, 0, 0, 0, 0, 0, false};
uint8_t    dbCount  = 0;
uint32_t   lastHeartbeatMs = 0;
bool       moduleAlive = false;

// ------------------------- 工具 -------------------------
uint8_t checksumOf(const uint8_t *buf, uint8_t len) {
  uint8_t s = 0;
  for (uint8_t i = 0; i < len; i++) s = (uint8_t)(s + buf[i]);
  return s;
}

void dumpFrame(const uint8_t *buf, uint8_t len) {
  Serial.printf("[RX]");
  for (uint8_t i = 0; i < len; i++) Serial.printf(" %02X", buf[i]);
  Serial.println();
}

void handleFrame(uint8_t type, const uint8_t *payload, uint8_t len) {
  switch (type) {
    case P_RESULT: {
      if (len != 10) break;
      face.id    = payload[0];
      face.score = payload[1];
      face.cx    = payload[2] | (payload[3] << 8);
      face.cy    = payload[4] | (payload[5] << 8);
      face.w     = payload[6] | (payload[7] << 8);
      face.h     = payload[8] | (payload[9] << 8);
      face.valid = (face.id != 0xFF);
      Serial.printf("[FACE] id=%u score=%u%% center=(%u,%u) box=%ux%u %s\n",
                    face.id, face.score, face.cx, face.cy, face.w, face.h,
                    face.valid ? "TRACKED" : "none");
      break;
    }
    case P_HEARTBEAT:
      if (len < 2) break;                       // 长度保护
      lastHeartbeatMs = millis();
      moduleAlive = (payload[0] == 0x01);
      break;
    case P_STATUS:
      dbCount = (len >= 2) ? payload[1] : 0;
      if (len >= 1) Serial.printf("[K230D] status code=0x%02X db_persons=%u\n", payload[0], dbCount);
      break;
    default:
      Serial.printf("[RX] unknown type 0x%02X len=%u\n", type, len);
  }
}

// 逐字节喂入状态机（所有字节都从这里走，天然抗粘包/断流）
void uartFeed(uint8_t b) {
  switch (rxState) {
    case S_IDLE:
      if (b == P_SYNC0) rxState = S_SYNC1;
      break;
    case S_SYNC1:
      if (b == P_SYNC1)      rxState = S_TYPE;
      else if (b != P_SYNC0) rxState = S_IDLE;   // 连续 0xAA 时保持同步
      break;
    case S_TYPE:
      rxType = b; rxState = S_LEN;
      break;
    case S_LEN:
      rxLen = b;
      if (rxLen > sizeof(rxBuf)) { rxState = S_IDLE; break; } // 超长非法
      rxIdx = 0;
      rxState = (rxLen == 0) ? S_CHECKSUM : S_PAYLOAD;
      break;
    case S_PAYLOAD:
      rxBuf[rxIdx++] = b;
      if (rxIdx >= rxLen) rxState = S_CHECKSUM;
      break;
    case S_CHECKSUM:
      rxSum = b;
      {
        uint8_t frame[80];
        frame[0] = P_SYNC0; frame[1] = P_SYNC1; frame[2] = rxType; frame[3] = rxLen;
        memcpy(frame + 4, rxBuf, rxLen);
        if (checksumOf(frame, 4 + rxLen) == rxSum) {
          if (VERBOSE) { dumpFrame(frame, 4 + rxLen + 1); }
          handleFrame(rxType, rxBuf, rxLen);
        } else {
          Serial.printf("[RX] checksum err: calc=0x%02X recv=0x%02X\n",
                        checksumOf(frame, 4 + rxLen), rxSum);
        }
        rxState = S_IDLE;
      }
      break;
  }
}

// ------------------------- 动作逻辑（骨架）------------------------
// 后续要接到你们的控制环：FOC 双轮自平衡 + 机械臂
// 这里只做“面向目标人”的比例输出示例
void runBehavior() {
  if (!moduleAlive) {                       // K230D 掉线：走保护/降级
    // 例如：停止跟随、进入待机
    static uint32_t lastWarn = 0;
    if (millis() - lastWarn > 2000) {
      Serial.println("[BEHAVIOR] K230D offline -> standby");
      lastWarn = millis();
    }
    return;
  }
  if (!face.valid) {
    // 画面中没识别到目标人：保持当前姿态（由主控决定）
    return;
  }
  int err = (int)face.cx - CENTER_X;         // 目标人脸相对画面中心的偏移
  if (abs(err) <= DEADBAND_PX) return;       // 已在中心：保持

  float turnCmd = err * TURN_KP;             // 比例控制量（注意方向盘符号按整车标定）
  // TODO: 接入平衡车主控，例如：
  //   motorCtrl.setYawRate(turnCmd);         // 正/负 = 左右转
  //   armCtrl.waveOnDetect(face.id);         // 机械臂对特定人打招呼
  static uint32_t lastLog = 0;
  if (millis() - lastLog > 500) {
    Serial.printf("[BEHAVIOR] target offset=%d -> turn=%.3f\n", err, turnCmd);
    lastLog = millis();
  }
}

// ------------------------- 主程序 -------------------------
HardwareSerial &k230 = Serial1;

void setup() {
  Serial.begin(115200);                      // USB 调试口
  k230.begin(BAUD, SERIAL_8N1, UART_RX_PIN, UART_TX_PIN);
  Serial.printf("[ESP32] K230D listener on UART1 RX=%d TX=%d @%u\n",
                UART_RX_PIN, UART_TX_PIN, BAUD);
  // 启动后主动查询一次 K230D 状态（模块收到 0x04 会回 0x03）
  k230.write((const uint8_t[]){P_SYNC0, P_SYNC1, P_QUERY, 0x00,
                               (P_SYNC0 + P_SYNC1 + P_QUERY + 0x00) & 0xFF}, 5);
}

void loop() {
  // 接收：逐字节喂状态机（抗粘包）
  while (k230.available()) {
    uartFeed(k230.read());
  }

  // 心跳看门狗
  if (moduleAlive && (millis() - lastHeartbeatMs > HEARTBEAT_TIMEOUT_MS)) {
    moduleAlive = false;
    face.valid = false;
    Serial.println("[ESP32] heartbeat timeout: K230D lost");
  }

  runBehavior();
  // 车速/舵机控制循环在这里并行（你们的现有循环体）
  delay(5);
}
