#pragma once

#include <Arduino.h>
#include <WiringConfig.h>
#include "CalibrationCore.h"


namespace cyberarm {
namespace firmware {

constexpr uint8_t kAxisCount = 6;
constexpr uint16_t kMaxSegments = 512;
constexpr uint32_t kControlPeriodMs = 20;
constexpr uint32_t kWatchdogMs = 1500;
constexpr uint32_t kSerialBaud = 921600;
// CommandProtocol accepts JSONL requests up to `inputLine_` bytes (2048). The
// USB CDC receive queue defaults to 256 bytes and silently drops the overflow,
// which truncated long requests such as save_mapping and left a half line in
// the parser. Keep the queue comfortably above the protocol limit.
constexpr size_t kSerialRxBufferBytes = 4096;
// Arm ramp: how long the six outputs take to travel from the last commanded
// pose to the requested pose when the controller is enabled. Must stay > 0.
constexpr uint32_t kArmRampMs = 600;
constexpr char kFirmwareVersion[] = "0.4.2";
constexpr char kModelId[] = "revc-sim-1";
// Factory defaults only. Device-bound NVS limits can be edited from the host.
constexpr float kMinDeg[kAxisCount] = {-30, -30, -30, -30, -30, -8};
constexpr float kMaxDeg[kAxisCount] = {30, 30, 30, 30, 30, 8};
constexpr float kMaxAccelerationDegS2[kAxisCount] = {50, 40, 50, 70, 70, 24};
constexpr float kMaxVelocityDegS[kAxisCount] = {25, 20, 25, 35, 35, 12};

enum class MotionMode : uint8_t {
  kDisarmed,
  kArmed,
  kArming,
  kService,
  kPrepared,
  kWaiting,
  kRunning,
  kStopping,
  kPaused,
  kFault,
};

struct AxisCalibration {
  uint16_t minUs = 1300;
  uint16_t centerUs = 1500;
  uint16_t maxUs = 1700;
  bool reversed = false;
  bool confirmed = false;
};

struct Segment {
  float endDeg[kAxisCount];
  uint32_t atMs;
  uint32_t durationMs;
};

}  // namespace firmware
}  // namespace cyberarm
