#pragma once

#include "FirmwareConfig.h"
#include "ServoSubsystem.h"

namespace cyberarm {
namespace firmware {

class MotionController {
 public:
  explicit MotionController(ServoSubsystem& servos) : servos_(servos) {}

  void initialize(bool driverReady);

  MotionMode mode() const { return mode_; }
  const char* modeName() const;
  bool isArmed() const;
  const float* commandedDeg() const { return commandedDeg_; }
  uint16_t expectedSegments() const { return expectedSegments_; }
  uint16_t receivedSegments() const { return receivedSegments_; }

  void disarm();
  void enterService(uint8_t axis);
  void arm(const float target[kAxisCount]);
  void startManualMove(const float target[kAxisCount], uint32_t durationMs,
                       uint32_t now);
  void prepare(uint16_t count, const float start[kAxisCount]);
  void appendSegment(const float end[kAxisCount], uint32_t durationMs);
  void commit(uint32_t startDelayMs, uint32_t now);
  void pause();
  void stop();
  void tick(uint32_t now);
  void handleWatchdog();

 private:
  static float quintic(float t);
  void clearPlan();
  void evaluateTrajectory(float trajectoryMs);
  void beginStop(bool pause);

  ServoSubsystem& servos_;
  Segment segments_[kMaxSegments];
  float commandedDeg_[kAxisCount] = {};
  float planStartDeg_[kAxisCount] = {};
  float manualStartDeg_[kAxisCount] = {};
  float manualEndDeg_[kAxisCount] = {};
  uint16_t expectedSegments_ = 0;
  uint16_t receivedSegments_ = 0;
  uint32_t planDurationMs_ = 0;
  float trajectoryTimeMs_ = 0;
  float stopTimeMs_ = 0;
  float stopDurationMs_ = 80;
  uint32_t scheduledStartMs_ = 0;
  uint32_t manualStartedMs_ = 0;
  uint32_t manualDurationMs_ = 0;
  MotionMode mode_ = MotionMode::kDisarmed;
  bool manualMoving_ = false;
  bool pauseAfterStop_ = false;
};

}  // namespace firmware
}  // namespace cyberarm
