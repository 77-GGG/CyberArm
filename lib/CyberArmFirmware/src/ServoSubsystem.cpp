#include "ServoSubsystem.h"

#include <math.h>
#include <stdio.h>

namespace cyberarm {
namespace firmware {

bool ServoSubsystem::begin() {
  preferences_.begin("cyberarm", false);
  loadCalibrations();
  driverReady_ =
      servos_.begin(CYBERARM_I2C_SDA, CYBERARM_I2C_SCL, 400000, 50.0F);

  // begin() touches the PCA9685, so force all channels off again before any
  // host connection. A serial handshake alone can never energise a servo.
  servos_.disableAll();
  outputsEnabled_ = false;
  return driverReady_;
}

bool ServoSubsystem::allCalibrated() const {
  for (const auto& calibration : calibrations_) {
    if (!calibration.confirmed) return false;
  }
  return true;
}

bool ServoSubsystem::setCalibration(uint8_t axis, uint16_t minUs,
                                    uint16_t centerUs, uint16_t maxUs,
                                    bool reversed) {
  if (axis >= kAxisCount) return false;

  AxisCalibration& item = calibrations_[axis];
  item.minUs = minUs;
  item.centerUs = centerUs;
  item.maxUs = maxUs;
  item.reversed = reversed;
  item.confirmed = true;
  servos_.setCalibration(axis, minUs, maxUs, centerUs, reversed);
  saveCalibration(axis);
  return true;
}

void ServoSubsystem::centerAxis(uint8_t axis) {
  servos_.disableAll();
  servos_.center(axis);
  outputsEnabled_ = true;
}

void ServoSubsystem::enableAt(const float jointDeg[kAxisCount]) {
  outputsEnabled_ = true;
  write(jointDeg);
}

void ServoSubsystem::write(const float jointDeg[kAxisCount]) {
  if (!driverReady_ || !outputsEnabled_) return;
  for (uint8_t axis = 0; axis < kAxisCount; ++axis) {
    servos_.writeMicroseconds(axis, angleToPulse(axis, jointDeg[axis]));
  }
}

void ServoSubsystem::disableAll() {
  servos_.disableAll();
  outputsEnabled_ = false;
}

void ServoSubsystem::saveCalibration(uint8_t axis) {
  char key[12];
  snprintf(key, sizeof(key), "a%u_min", axis);
  preferences_.putUShort(key, calibrations_[axis].minUs);
  snprintf(key, sizeof(key), "a%u_ctr", axis);
  preferences_.putUShort(key, calibrations_[axis].centerUs);
  snprintf(key, sizeof(key), "a%u_max", axis);
  preferences_.putUShort(key, calibrations_[axis].maxUs);
  snprintf(key, sizeof(key), "a%u_rev", axis);
  preferences_.putBool(key, calibrations_[axis].reversed);
  snprintf(key, sizeof(key), "a%u_ok", axis);
  preferences_.putBool(key, true);
}

void ServoSubsystem::loadCalibrations() {
  char key[12];
  for (uint8_t axis = 0; axis < kAxisCount; ++axis) {
    snprintf(key, sizeof(key), "a%u_min", axis);
    calibrations_[axis].minUs = preferences_.getUShort(key, 1300);
    snprintf(key, sizeof(key), "a%u_ctr", axis);
    calibrations_[axis].centerUs = preferences_.getUShort(key, 1500);
    snprintf(key, sizeof(key), "a%u_max", axis);
    calibrations_[axis].maxUs = preferences_.getUShort(key, 1700);
    snprintf(key, sizeof(key), "a%u_rev", axis);
    calibrations_[axis].reversed = preferences_.getBool(key, false);
    snprintf(key, sizeof(key), "a%u_ok", axis);
    calibrations_[axis].confirmed = preferences_.getBool(key, false);
    if (!(500 <= calibrations_[axis].minUs &&
          calibrations_[axis].minUs < calibrations_[axis].centerUs &&
          calibrations_[axis].centerUs < calibrations_[axis].maxUs &&
          calibrations_[axis].maxUs <= 2500)) {
      calibrations_[axis] = AxisCalibration{};
    }
    servos_.setCalibration(axis, calibrations_[axis].minUs,
                           calibrations_[axis].maxUs,
                           calibrations_[axis].centerUs,
                           calibrations_[axis].reversed);
  }
}

uint16_t ServoSubsystem::angleToPulse(uint8_t axis, float jointDeg) const {
  const AxisCalibration& calibration = calibrations_[axis];
  float physicalDeg = calibration.reversed ? -jointDeg : jointDeg;
  physicalDeg = constrain(physicalDeg, kMinDeg[axis], kMaxDeg[axis]);
  float pulse;
  if (physicalDeg >= 0) {
    pulse = calibration.centerUs +
            physicalDeg / kMaxDeg[axis] *
                (calibration.maxUs - calibration.centerUs);
  } else {
    pulse = calibration.centerUs +
            physicalDeg / -kMinDeg[axis] *
                (calibration.centerUs - calibration.minUs);
  }
  return static_cast<uint16_t>(lroundf(pulse));
}

}  // namespace firmware
}  // namespace cyberarm
