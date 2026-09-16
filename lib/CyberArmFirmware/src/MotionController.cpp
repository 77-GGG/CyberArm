#include "MotionController.h"

#include <math.h>
#include <string.h>

namespace cyberarm {
namespace firmware {

void MotionController::initialize(bool driverReady) {
  mode_ = driverReady ? MotionMode::kDisarmed : MotionMode::kFault;
}

const char* MotionController::modeName() const {
  switch (mode_) {
    case MotionMode::kDisarmed:
      return "DISARMED";
    case MotionMode::kArmed:
      return "ARMED";
    case MotionMode::kService:
      return "SERVICE";
    case MotionMode::kPrepared:
      return "PREPARED";
    case MotionMode::kWaiting:
      return "WAITING";
    case MotionMode::kRunning:
      return "RUNNING";
    case MotionMode::kStopping:
      return "STOPPING";
    case MotionMode::kPaused:
      return "PAUSED";
    case MotionMode::kFault:
      return "FAULT";
  }
  return "FAULT";
}

bool MotionController::isArmed() const {
  return mode_ == MotionMode::kArmed || mode_ == MotionMode::kPrepared ||
         mode_ == MotionMode::kWaiting || mode_ == MotionMode::kRunning ||
         mode_ == MotionMode::kStopping || mode_ == MotionMode::kPaused;
}

void MotionController::disarm() {
  servos_.disableAll();
  clearPlan();
  mode_ = MotionMode::kDisarmed;
}

void MotionController::enterService(uint8_t axis) {
  servos_.centerAxis(axis);
  mode_ = MotionMode::kService;
}

void MotionController::arm(const float target[kAxisCount]) {
  clearPlan();
  memcpy(commandedDeg_, target, sizeof(commandedDeg_));
  mode_ = MotionMode::kArmed;
  servos_.enableAt(commandedDeg_);
}

void MotionController::startManualMove(const float target[kAxisCount],
                                       uint32_t durationMs, uint32_t now) {
  memcpy(manualStartDeg_, commandedDeg_, sizeof(commandedDeg_));
  memcpy(manualEndDeg_, target, sizeof(manualEndDeg_));
  manualStartedMs_ = now;
  manualDurationMs_ = durationMs;
  manualMoving_ = true;
}

void MotionController::prepare(uint16_t count,
                               const float start[kAxisCount]) {
  clearPlan();
  expectedSegments_ = count;
  memcpy(planStartDeg_, start, sizeof(planStartDeg_));
  mode_ = MotionMode::kPrepared;
}

void MotionController::appendSegment(const float end[kAxisCount],
                                     uint32_t durationMs) {
  Segment& segment = segments_[receivedSegments_];
  memcpy(segment.endDeg, end, sizeof(segment.endDeg));
  segment.atMs = planDurationMs_;
  segment.durationMs = durationMs;
  planDurationMs_ += durationMs;
  ++receivedSegments_;
}

void MotionController::commit(uint32_t startDelayMs, uint32_t now) {
  trajectoryTimeMs_ = 0;
  scheduledStartMs_ = now + startDelayMs;
  mode_ = MotionMode::kWaiting;
}

void MotionController::pause() {
  if (mode_ == MotionMode::kWaiting || mode_ == MotionMode::kPrepared) {
    clearPlan();
    mode_ = MotionMode::kArmed;
  } else {
    beginStop(true);
  }
}

void MotionController::stop() {
  if (mode_ == MotionMode::kWaiting || mode_ == MotionMode::kPrepared ||
      mode_ == MotionMode::kPaused) {
    clearPlan();
    mode_ = MotionMode::kArmed;
  } else {
    beginStop(false);
  }
}

void MotionController::tick(uint32_t now) {
  if (mode_ == MotionMode::kWaiting &&
      static_cast<int32_t>(now - scheduledStartMs_) >= 0) {
    mode_ = MotionMode::kRunning;
  }
  if (mode_ == MotionMode::kRunning) {
    trajectoryTimeMs_ = min(trajectoryTimeMs_ + kControlPeriodMs,
                            static_cast<float>(planDurationMs_));
    evaluateTrajectory(trajectoryTimeMs_);
    if (trajectoryTimeMs_ >= planDurationMs_) {
      clearPlan();
      mode_ = MotionMode::kArmed;
    }
  } else if (mode_ == MotionMode::kStopping) {
    const float oldStop = stopTimeMs_;
    const float newStop = min(stopDurationMs_, oldStop + kControlPeriodMs);
    trajectoryTimeMs_ +=
        (newStop - oldStop) -
        (newStop * newStop - oldStop * oldStop) / (2.0F * stopDurationMs_);
    trajectoryTimeMs_ =
        min(trajectoryTimeMs_, static_cast<float>(planDurationMs_));
    stopTimeMs_ = newStop;
    evaluateTrajectory(trajectoryTimeMs_);
    if (stopTimeMs_ >= stopDurationMs_ ||
        trajectoryTimeMs_ >= planDurationMs_) {
      clearPlan();
      mode_ = pauseAfterStop_ ? MotionMode::kPaused : MotionMode::kArmed;
    }
  }

  if (manualMoving_ && mode_ == MotionMode::kArmed) {
    const uint32_t elapsed = now - manualStartedMs_;
    const float u =
        quintic(static_cast<float>(min(elapsed, manualDurationMs_)) /
                manualDurationMs_);
    for (uint8_t axis = 0; axis < kAxisCount; ++axis) {
      commandedDeg_[axis] =
          manualStartDeg_[axis] +
          (manualEndDeg_[axis] - manualStartDeg_[axis]) * u;
    }
    servos_.write(commandedDeg_);
    if (elapsed >= manualDurationMs_) manualMoving_ = false;
  }
}

void MotionController::handleWatchdog() {
  manualMoving_ = false;
  clearPlan();
  if (mode_ == MotionMode::kService) {
    disarm();
  } else {
    // Keep the last PWM to avoid dropping a loaded arm. Re-arming is required
    // after reconnect; the physical power switch remains the emergency stop.
    mode_ = MotionMode::kFault;
  }
}

float MotionController::quintic(float t) {
  t = constrain(t, 0.0F, 1.0F);
  return t * t * t * (10.0F + t * (-15.0F + 6.0F * t));
}

void MotionController::clearPlan() {
  expectedSegments_ = 0;
  receivedSegments_ = 0;
  planDurationMs_ = 0;
  trajectoryTimeMs_ = 0;
  stopTimeMs_ = 0;
  manualMoving_ = false;
}

void MotionController::evaluateTrajectory(float trajectoryMs) {
  if (receivedSegments_ == 0) return;
  uint16_t index = receivedSegments_ - 1;
  for (uint16_t i = 0; i < receivedSegments_; ++i) {
    if (trajectoryMs < segments_[i].atMs + segments_[i].durationMs) {
      index = i;
      break;
    }
  }
  const Segment& segment = segments_[index];
  const float* start =
      index == 0 ? planStartDeg_ : segments_[index - 1].endDeg;
  const float elapsed =
      constrain(trajectoryMs - segment.atMs, 0.0F,
                static_cast<float>(segment.durationMs));
  const float u = quintic(elapsed / segment.durationMs);
  for (uint8_t axis = 0; axis < kAxisCount; ++axis) {
    commandedDeg_[axis] =
        start[axis] + (segment.endDeg[axis] - start[axis]) * u;
  }
  servos_.write(commandedDeg_);
}

void MotionController::beginStop(bool pause) {
  manualMoving_ = false;
  if (mode_ != MotionMode::kRunning && mode_ != MotionMode::kStopping) {
    clearPlan();
    mode_ = pause && mode_ == MotionMode::kPaused ? MotionMode::kPaused
                                                  : MotionMode::kArmed;
    return;
  }
  if (mode_ == MotionMode::kStopping) {
    if (!pause) pauseAfterStop_ = false;
    return;
  }
  pauseAfterStop_ = pause;
  stopTimeMs_ = 0;
  stopDurationMs_ = 80;
  for (uint16_t i = 0; i < receivedSegments_; ++i) {
    const float* start =
        i == 0 ? planStartDeg_ : segments_[i - 1].endDeg;
    const float seconds = segments_[i].durationMs / 1000.0F;
    for (uint8_t axis = 0; axis < kAxisCount; ++axis) {
      const float velocity =
          1.875F * fabsf(segments_[i].endDeg[axis] - start[axis]) / seconds;
      const float requiredMs =
          1000.0F * velocity / (kMaxAccelerationDegS2[axis] * 0.5F);
      stopDurationMs_ = max(stopDurationMs_, requiredMs);
    }
  }
  mode_ = MotionMode::kStopping;
}

}  // namespace firmware
}  // namespace cyberarm
