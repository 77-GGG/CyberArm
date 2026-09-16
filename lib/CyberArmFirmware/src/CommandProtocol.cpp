#include "CommandProtocol.h"

#include <math.h>
#include <string.h>

namespace cyberarm {
namespace firmware {

void CommandProtocol::service() {
  while (serial_.available()) {
    const char value = static_cast<char>(serial_.read());
    if (value == '\n') {
      inputLine_[inputLength_] = '\0';
      if (inputLength_) handleCommand(inputLine_);
      inputLength_ = 0;
    } else if (value != '\r') {
      if (inputLength_ + 1 < sizeof(inputLine_)) {
        inputLine_[inputLength_++] = value;
      } else {
        inputLength_ = 0;
      }
    }
  }
}

bool CommandProtocol::readJointArray(JsonVariantConst value,
                                     float output[kAxisCount]) {
  JsonArrayConst array = value.as<JsonArrayConst>();
  if (array.size() != kAxisCount) return false;
  for (uint8_t i = 0; i < kAxisCount; ++i) {
    if (!array[i].is<float>() && !array[i].is<int>()) return false;
    const float angle = array[i].as<float>();
    if (!isfinite(angle) || angle < kMinDeg[i] - 0.001F ||
        angle > kMaxDeg[i] + 0.001F) {
      return false;
    }
    output[i] = angle;
  }
  return true;
}

void CommandProtocol::handleCommand(const char* line) {
  JsonDocument request;
  DeserializationError parseError = deserializeJson(request, line);
  if (parseError) return;
  const uint32_t id = request["id"] | 0;
  if ((request["protocol_version"] | 0) != 1) {
    reply(id, false, "unsupported protocol_version");
    return;
  }
  const char* command = request["command"] | "";
  lastContactMs_ = millis();

  if (!strcmp(command, "hello") || !strcmp(command, "heartbeat")) {
    reply(id, true);
    return;
  }
  if (!strcmp(command, "disarm")) {
    motion_.disarm();
    reply(id, true);
    return;
  }
  if (!strcmp(command, "set_calibration")) {
    if (servos_.outputsEnabled()) {
      reply(id, false, "disarm before changing calibration");
      return;
    }
    const int axis = request["axis"] | -1;
    const int minUs = request["min_us"] | 0;
    const int centerUs = request["center_us"] | 0;
    const int maxUs = request["max_us"] | 0;
    if (axis < 0 || axis >= kAxisCount || minUs < 500 || maxUs > 2500 ||
        minUs >= centerUs || centerUs >= maxUs || centerUs - minUs < 100 ||
        maxUs - centerUs < 100) {
      reply(id, false, "invalid calibration");
      return;
    }
    servos_.setCalibration(axis, minUs, centerUs, maxUs,
                           request["reversed"] | false);
    reply(id, true);
    return;
  }
  if (!strcmp(command, "center_axis")) {
    const int axis = request["axis"] | -1;
    if (!servos_.driverReady() || axis < 0 || axis >= kAxisCount ||
        !servos_.calibrations()[axis].confirmed || motion_.isArmed()) {
      reply(id, false, "axis is not calibrated or controller is armed");
      return;
    }
    motion_.enterService(axis);
    reply(id, true);
    return;
  }
  if (!strcmp(command, "arm")) {
    float target[kAxisCount];
    if (!servos_.driverReady() || !servos_.allCalibrated() ||
        !readJointArray(request["q_deg"], target)) {
      reply(id, false, "driver/calibration/joint target is not ready");
      return;
    }
    motion_.arm(target);
    reply(id, true);
    return;
  }
  if (!motion_.isArmed()) {
    reply(id, false, "controller is not armed");
    return;
  }
  if (!strcmp(command, "target")) {
    float target[kAxisCount];
    const uint32_t duration = request["duration_ms"] | 0;
    if (motion_.mode() != MotionMode::kArmed || duration < 20 ||
        duration > 5000 || !readJointArray(request["q_deg"], target)) {
      reply(id, false, "invalid manual target or controller mode");
      return;
    }
    motion_.startManualMove(target, duration, millis());
    reply(id, true);
    return;
  }
  if (!strcmp(command, "prepare")) {
    const int count = request["count"] | 0;
    float start[kAxisCount];
    const char* modelId = request["model_id"] | "";
    if ((motion_.mode() != MotionMode::kArmed &&
         motion_.mode() != MotionMode::kPaused) ||
        count < 1 || count > kMaxSegments || strcmp(modelId, kModelId) ||
        !readJointArray(request["start_deg"], start)) {
      reply(id, false, "invalid trajectory header");
      return;
    }
    for (uint8_t axis = 0; axis < kAxisCount; ++axis) {
      if (fabsf(start[axis] - motion_.commandedDeg()[axis]) > 1.0F) {
        reply(id, false, "trajectory start differs from commanded pose");
        return;
      }
    }
    motion_.prepare(count, start);
    reply(id, true);
    return;
  }
  if (!strcmp(command, "segment")) {
    const int index = request["index"] | -1;
    const uint32_t duration = request["duration_ms"] | 0;
    float end[kAxisCount];
    if (motion_.mode() != MotionMode::kPrepared ||
        index != motion_.receivedSegments() ||
        motion_.receivedSegments() >= motion_.expectedSegments() ||
        duration < 20 || duration > 60000 ||
        !readJointArray(request["end_deg"], end)) {
      reply(id, false, "invalid trajectory segment");
      return;
    }
    motion_.appendSegment(end, duration);
    reply(id, true);
    return;
  }
  if (!strcmp(command, "commit")) {
    const uint32_t delayMs = request["start_delay_ms"] | 0;
    if (motion_.mode() != MotionMode::kPrepared ||
        motion_.receivedSegments() != motion_.expectedSegments() ||
        delayMs < 100 || delayMs > 2000) {
      reply(id, false,
            "trajectory is incomplete or start delay is invalid");
      return;
    }
    motion_.commit(delayMs, millis());
    reply(id, true);
    return;
  }
  if (!strcmp(command, "pause")) {
    motion_.pause();
    reply(id, true);
    return;
  }
  if (!strcmp(command, "stop")) {
    motion_.stop();
    reply(id, true);
    return;
  }
  reply(id, false, "unknown command");
}

void CommandProtocol::addState(JsonObject state) const {
  state["firmware_version"] = kFirmwareVersion;
  state["model_id"] = kModelId;
  state["driver_ready"] = servos_.driverReady();
  state["armed"] = motion_.isArmed();
  state["outputs_enabled"] = servos_.outputsEnabled();
  state["mode"] = motion_.modeName();
  state["measured_feedback"] = false;
  state["measured_q_deg"] = nullptr;
  JsonArray q = state["commanded_q_deg"].to<JsonArray>();
  for (uint8_t axis = 0; axis < kAxisCount; ++axis) {
    q.add(motion_.commandedDeg()[axis]);
  }
  JsonArray calibrated = state["calibrated"].to<JsonArray>();
  JsonArray calibration = state["calibration"].to<JsonArray>();
  for (uint8_t axis = 0; axis < kAxisCount; ++axis) {
    const AxisCalibration& item = servos_.calibrations()[axis];
    calibrated.add(item.confirmed);
    JsonObject row = calibration.add<JsonObject>();
    row["min_us"] = item.minUs;
    row["center_us"] = item.centerUs;
    row["max_us"] = item.maxUs;
    row["reversed"] = item.reversed;
    row["confirmed"] = item.confirmed;
  }
}

void CommandProtocol::reply(uint32_t id, bool ok, const char* error) {
  JsonDocument response;
  response["protocol_version"] = 1;
  response["reply_to"] = id;
  response["ok"] = ok;
  if (error) response["error"] = error;
  JsonObject state = response["state"].to<JsonObject>();
  addState(state);
  serializeJson(response, serial_);
  serial_.write('\n');
}

}  // namespace firmware
}  // namespace cyberarm
