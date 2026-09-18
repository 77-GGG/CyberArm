#include "ServoSubsystem.h"

#include <math.h>
#include <stdio.h>

namespace cyberarm {
namespace firmware {

bool ServoSubsystem::begin() {
  preferences_.begin("cyberarm", false);
  loadCalibrations();
  driverReady_ =
      servos_.begin(wiring::kSda, wiring::kScl, wiring::kI2cClock, wiring::kPwmHz);
  if (driverReady_) {
    servos_.rawDriver().setOscillatorFrequency(wiring::kOscillator);
    servos_.setFrequency(wiring::kPwmHz);
    tickUs_ = (servos_.rawDriver().readPrescale() + 1) * 1000000.f / wiring::kOscillator;
  }

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
  // Legacy calibration writes cannot certify measured angle mappings.
  return false;
}

void ServoSubsystem::centerAxis(uint8_t axis) {
  servos_.disableAll();
  float pulse;
  if (anglePulse(axis, 0, pulse)) testPulse(axis, pulse);
}

void ServoSubsystem::enableAt(const float jointDeg[kAxisCount]) {
  outputsEnabled_ = true;
  write(jointDeg);
}

void ServoSubsystem::write(const float jointDeg[kAxisCount]) {
  if (!driverReady_ || !outputsEnabled_) return;
  for (uint8_t axis = 0; axis < kAxisCount; ++axis) {
    float pulse;
    if (!anglePulse(axis, jointDeg[axis], pulse) ||
        servos_.rawDriver().setPWM(wiring::kChannels[axis], 0, pulseTicks(pulse)) != 0) {
      driverReady_ = false; return;
    }
  }
}

void ServoSubsystem::disableAll() {
  servos_.disableAll();
  outputsEnabled_ = false;
}

void ServoSubsystem::loadCalibrations() {
  for (uint8_t axis=0; axis<kAxisCount; ++axis) {
    limits_[axis].low=kMinDeg[axis];limits_[axis].high=kMaxDeg[axis];
    char limitKey[12];snprintf(limitKey,sizeof(limitKey),"limit%u",axis);
    JointLimits savedLimits{};
    if(preferences_.getBytesLength(limitKey)==sizeof(savedLimits) &&
       preferences_.getBytes(limitKey,&savedLimits,sizeof(savedLimits))==sizeof(savedLimits) &&
       validLimits(savedLimits) && !strncmp(savedLimits.wiringHash,wiring::kHash,sizeof(savedLimits.wiringHash)) &&
       !strncmp(savedLimits.modelId,kModelId,sizeof(savedLimits.modelId))) limits_[axis]=savedLimits;
    char key[12]; snprintf(key,sizeof(key),"map%u",axis);
    JointMapping candidate{};
    if (preferences_.getBytesLength(key)==sizeof(candidate) &&
        preferences_.getBytes(key,&candidate,sizeof(candidate))==sizeof(candidate) &&
        validMapping(candidate) && !strncmp(candidate.wiringHash,wiring::kHash,sizeof(candidate.wiringHash)) &&
        !strncmp(candidate.modelId,kModelId,sizeof(candidate.modelId))) {
      mappings_[axis]=candidate;
      float center;mapAngle(candidate,0,center);
      calibrations_[axis].centerUs=lroundf(center);
      calibrations_[axis].confirmed=true;
    }
  }
  return;
}

uint16_t ServoSubsystem::pulseTicks(float us) const {
  return static_cast<uint16_t>(lroundf(us/tickUs_));
}
bool ServoSubsystem::testPulse(uint8_t axis,float us) {
  if(!driverReady_ || axis>=kAxisCount || !isfinite(us) || us<500 || us>2500) return false;
  if(servos_.rawDriver().setPWM(wiring::kChannels[axis],0,pulseTicks(us)) != 0) {
    driverReady_=false;return false;
  }
  outputsEnabled_=true;return true;
}
bool ServoSubsystem::anglePulse(uint8_t axis,float q,float& pulse) const {
  return axis<kAxisCount && q>=limits_[axis].low && q<=limits_[axis].high && mapAngle(mappings_[axis],q,pulse);
}
bool ServoSubsystem::validTarget(const float q[kAxisCount]) const {
  float pulse;
  for(uint8_t i=0;i<kAxisCount;++i) if(!anglePulse(i,q[i],pulse)) return false;
  return true;
}
bool ServoSubsystem::saveLimits(uint8_t axis,JointLimits candidate) {
  if(axis>=kAxisCount || outputsEnabled_ || !validLimits(candidate)) return false;
  candidate.revision=limits_[axis].revision+1;
  snprintf(candidate.modelId,sizeof(candidate.modelId),"%s",kModelId);
  snprintf(candidate.wiringHash,sizeof(candidate.wiringHash),"%s",wiring::kHash);
  char key[12];snprintf(key,sizeof(key),"limit%u",axis);
  if(preferences_.putBytes(key,&candidate,sizeof(candidate))!=sizeof(candidate)) return false;
  JointLimits check{};
  if(preferences_.getBytes(key,&check,sizeof(check))!=sizeof(check) || memcmp(&check,&candidate,sizeof(check))) {
    driverReady_=false;return false;
  }
  limits_[axis]=candidate;return true;
}
bool ServoSubsystem::saveMapping(uint8_t axis,JointMapping candidate) {
  if(axis>=kAxisCount || outputsEnabled_ || !validMapping(candidate)) return false;
  candidate.revision=mappings_[axis].revision+1;
  snprintf(candidate.modelId,sizeof(candidate.modelId),"%s",kModelId);
  snprintf(candidate.wiringHash,sizeof(candidate.wiringHash),"%s",wiring::kHash);
  char key[12];snprintf(key,sizeof(key),"map%u",axis);
  // One NVS blob is the commit unit. Never publish a half-written mapping.
  if(preferences_.putBytes(key,&candidate,sizeof(candidate))!=sizeof(candidate)) return false;
  JointMapping check{};
  if(preferences_.getBytes(key,&check,sizeof(check))!=sizeof(check) || memcmp(&check,&candidate,sizeof(check))) {
    calibrations_[axis].confirmed=false;mappings_[axis]=JointMapping{};return false;
  }
  mappings_[axis]=candidate;
  float center;mapAngle(candidate,0,center);
  calibrations_[axis].centerUs=lroundf(center);
  calibrations_[axis].confirmed=true;return true;
}

}  // namespace firmware
}  // namespace cyberarm
