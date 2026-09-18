#include "CyberArmFirmware.h"

namespace cyberarm {
namespace firmware {

CyberArmFirmware::CyberArmFirmware()
    : motion_(servos_), protocol_(Serial, motion_, servos_) {}

void CyberArmFirmware::begin() {
  // Size the receive queue before the port starts; the driver only honours
  // setRxBufferSize() while the queue does not exist yet.
  Serial.setRxBufferSize(kSerialRxBufferBytes);
  Serial.begin(kSerialBaud);
  motion_.initialize(servos_.begin());
  protocol_.begin(millis());
  lastControlMs_ = millis();
}

void CyberArmFirmware::update() {
  protocol_.service();
  const uint32_t now = millis();
  protocol_.tick(now);
  while (now - lastControlMs_ >= kControlPeriodMs) {
    lastControlMs_ += kControlPeriodMs;
    motion_.tick(lastControlMs_);
    // Do not replay a long burst after a debugger break or CPU stall.
    if (now - lastControlMs_ > 200) lastControlMs_ = now;
  }
  if (servos_.outputsEnabled() &&
      now - protocol_.lastContactMs() > kWatchdogMs &&
      motion_.mode() != MotionMode::kFault) {
    motion_.handleWatchdog();
  }
}

}  // namespace firmware
}  // namespace cyberarm
