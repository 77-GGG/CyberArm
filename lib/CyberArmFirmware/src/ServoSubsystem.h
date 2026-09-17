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
  const JointMapping& mapping(uint8_t axis) const { return mappings_[axis]; }
  bool saveMapping(uint8_t axis, JointMapping candidate);
  bool validTarget(const float q[kAxisCount]) const;
  bool anglePulse(uint8_t axis, float q, float& pulse) const;
  bool testPulse(uint8_t axis, float us);
  float tickUs() const { return tickUs_; }
  uint16_t pulseTicks(float us) const;

  bool setCalibration(uint8_t axis, uint16_t minUs, uint16_t centerUs,
                      uint16_t maxUs, bool reversed);
  void centerAxis(uint8_t axis);
  void enableAt(const float jointDeg[kAxisCount]);
  void write(const float jointDeg[kAxisCount]);
  void disableAll();

 private:
  void loadCalibrations();

  PCA9685Servo servos_{wiring::kAddress};
  Preferences preferences_;
  AxisCalibration calibrations_[kAxisCount];
  JointMapping mappings_[kAxisCount];
  float tickUs_ = 4.88f;
  bool outputsEnabled_ = false;
  bool driverReady_ = false;
};

}  // namespace firmware
}  // namespace cyberarm
