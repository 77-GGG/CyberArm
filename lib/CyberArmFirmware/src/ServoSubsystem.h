#pragma once

#include <PCA9685Servo.h>
#include <Preferences.h>

#include "FirmwareConfig.h"

namespace cyberarm {
namespace firmware {

class ServoSubsystem {
 public:
  bool begin();

  bool driverReady() const { return driverReady_; }
  bool outputsEnabled() const { return outputsEnabled_; }
  bool allCalibrated() const;
  const AxisCalibration* calibrations() const { return calibrations_; }

  bool setCalibration(uint8_t axis, uint16_t minUs, uint16_t centerUs,
                      uint16_t maxUs, bool reversed);
  void centerAxis(uint8_t axis);
  void enableAt(const float jointDeg[kAxisCount]);
  void write(const float jointDeg[kAxisCount]);
  void disableAll();

 private:
  void loadCalibrations();
  void saveCalibration(uint8_t axis);
  uint16_t angleToPulse(uint8_t axis, float jointDeg) const;

  PCA9685Servo servos_;
  Preferences preferences_;
  AxisCalibration calibrations_[kAxisCount];
  bool outputsEnabled_ = false;
  bool driverReady_ = false;
};

}  // namespace firmware
}  // namespace cyberarm
