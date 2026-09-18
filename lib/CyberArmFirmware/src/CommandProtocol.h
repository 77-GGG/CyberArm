#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>

#include "MotionController.h"
#include "ServoSubsystem.h"

namespace cyberarm {
namespace firmware {

class CommandProtocol {
 public:
  CommandProtocol(Stream& serial, MotionController& motion,
                  ServoSubsystem& servos)
      : serial_(serial), motion_(motion), servos_(servos) {}

  void begin(uint32_t now) { lastContactMs_ = now; }
  void service();
  void tick(uint32_t now);
  uint32_t lastContactMs() const { return lastContactMs_; }

 private:
  bool readJointArray(JsonVariantConst value,
                             float output[kAxisCount]);
  void handleCommand(const char* line);
  void addRuntimeState(JsonObject state) const;
  void addState(JsonObject state) const;
  void replyRuntime(uint32_t id, bool ok, const char* error = nullptr);
  void reply(uint32_t id, bool ok, const char* error = nullptr);
  bool debugCommand(const char* command, JsonDocument& request, uint32_t id);
  AxisTest test_;
  bool droppingLine_ = false;

  Stream& serial_;
  MotionController& motion_;
  ServoSubsystem& servos_;
  uint32_t lastContactMs_ = 0;
  char inputLine_[2048];
  size_t inputLength_ = 0;
};

}  // namespace firmware
}  // namespace cyberarm
