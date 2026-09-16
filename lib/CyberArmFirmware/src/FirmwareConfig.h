#pragma once

#include <Arduino.h>

#ifndef CYBERARM_I2C_SDA
#define CYBERARM_I2C_SDA 8
#endif

#ifndef CYBERARM_I2C_SCL
#define CYBERARM_I2C_SCL 9
#endif

namespace cyberarm {
namespace firmware {

constexpr uint8_t kAxisCount = 6;
constexpr uint16_t kMaxSegments = 512;
constexpr uint32_t kControlPeriodMs = 20;
constexpr uint32_t kWatchdogMs = 1500;
constexpr char kFirmwareVersion[] = "0.1.0";
constexpr char kModelId[] = "revc-sim-1";
constexpr float kMinDeg[kAxisCount] = {-30, -30, -30, -30, -30, -8};
constexpr float kMaxDeg[kAxisCount] = {30, 30, 30, 30, 30, 8};
constexpr float kMaxAccelerationDegS2[kAxisCount] = {50, 40, 50, 70, 70, 24};

enum class MotionMode : uint8_t {
  kDisarmed,
  kArmed,
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
