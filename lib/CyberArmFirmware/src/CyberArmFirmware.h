#pragma once

#include <Arduino.h>

#include "CommandProtocol.h"
#include "MotionController.h"
#include "ServoSubsystem.h"

namespace cyberarm {
namespace firmware {

class CyberArmFirmware {
 public:
  CyberArmFirmware();

  void begin();
  void update();

 private:
  ServoSubsystem servos_;
  MotionController motion_;
  CommandProtocol protocol_;
  uint32_t lastControlMs_ = 0;
};

}  // namespace firmware
}  // namespace cyberarm
