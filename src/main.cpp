#include <Arduino.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <PCA9685Servo.h>

#include <math.h>
#include <string.h>

#ifndef CYBERARM_I2C_SDA
#define CYBERARM_I2C_SDA 8
#endif
#ifndef CYBERARM_I2C_SCL
#define CYBERARM_I2C_SCL 9
#endif

namespace {

constexpr uint8_t kAxisCount = 6;
constexpr uint16_t kMaxSegments = 512;
constexpr uint32_t kControlPeriodMs = 20;
constexpr uint32_t kWatchdogMs = 1500;
constexpr char kFirmwareVersion[] = "0.1.0";
constexpr char kModelId[] = "revc-sim-1";
constexpr float kMinDeg[kAxisCount] = {-30, -30, -30, -30, -30, -8};
constexpr float kMaxDeg[kAxisCount] = {30, 30, 30, 30, 30, 8};
constexpr float kMaxAccelerationDegS2[kAxisCount] = {50, 40, 50, 70, 70, 24};

enum class MotionMode : uint8_t {
  kDisarmed, kArmed, kService, kPrepared, kWaiting,
  kRunning, kStopping, kPaused, kFault,
};

struct AxisCalibration {
  uint16_t minUs = 1300;
  uint16_t centerUs = 1500;
  uint16_t maxUs = 1700;
  bool reversed = false;
  bool confirmed = false;
};

struct Segment {
  float endDeg[kAxisCount];
  uint32_t atMs;
  uint32_t durationMs;
};

cyberarm::PCA9685Servo servos;
Preferences preferences;
AxisCalibration calibrations[kAxisCount];
Segment segments[kMaxSegments];
float commandedDeg[kAxisCount] = {};
float planStartDeg[kAxisCount] = {};
float manualStartDeg[kAxisCount] = {};
float manualEndDeg[kAxisCount] = {};
uint16_t expectedSegments = 0;
uint16_t receivedSegments = 0;
uint32_t planDurationMs = 0;
float trajectoryTimeMs = 0;
float stopTimeMs = 0;
float stopDurationMs = 80;
uint32_t scheduledStartMs = 0;
uint32_t manualStartedMs = 0;
uint32_t manualDurationMs = 0;
uint32_t lastContactMs = 0;
uint32_t lastControlMs = 0;
MotionMode mode = MotionMode::kDisarmed;
bool outputsEnabled = false;
bool driverReady = false;
bool manualMoving = false;
bool pauseAfterStop = false;
char inputLine[2048];
size_t inputLength = 0;

const char* modeName() {
  switch (mode) {
    case MotionMode::kDisarmed: return "DISARMED";
    case MotionMode::kArmed: return "ARMED";
    case MotionMode::kService: return "SERVICE";
    case MotionMode::kPrepared: return "PREPARED";
    case MotionMode::kWaiting: return "WAITING";
    case MotionMode::kRunning: return "RUNNING";
    case MotionMode::kStopping: return "STOPPING";
    case MotionMode::kPaused: return "PAUSED";
    case MotionMode::kFault: return "FAULT";
  }
  return "FAULT";
}

bool isArmed() {
  return mode == MotionMode::kArmed || mode == MotionMode::kPrepared ||
         mode == MotionMode::kWaiting || mode == MotionMode::kRunning ||
         mode == MotionMode::kStopping || mode == MotionMode::kPaused;
}

bool allCalibrated() {
  for (const auto& calibration : calibrations) {
    if (!calibration.confirmed) return false;
  }
  return true;
}

float quintic(float t) {
  t = constrain(t, 0.0F, 1.0F);
  return t * t * t * (10.0F + t * (-15.0F + 6.0F * t));
}

bool readJointArray(JsonVariantConst value, float output[kAxisCount]) {
  JsonArrayConst array = value.as<JsonArrayConst>();
  if (array.size() != kAxisCount) return false;
  for (uint8_t i = 0; i < kAxisCount; ++i) {
    if (!array[i].is<float>() && !array[i].is<int>()) return false;
    const float angle = array[i].as<float>();
    if (!isfinite(angle) || angle < kMinDeg[i] - 0.001F ||
        angle > kMaxDeg[i] + 0.001F) return false;
    output[i] = angle;
  }
  return true;
}

uint16_t angleToPulse(uint8_t axis, float jointDeg) {
  const AxisCalibration& calibration = calibrations[axis];
  float physicalDeg = calibration.reversed ? -jointDeg : jointDeg;
  physicalDeg = constrain(physicalDeg, kMinDeg[axis], kMaxDeg[axis]);
  float pulse;
  if (physicalDeg >= 0) {
    pulse = calibration.centerUs +
            physicalDeg / kMaxDeg[axis] * (calibration.maxUs - calibration.centerUs);
  } else {
    pulse = calibration.centerUs +
            physicalDeg / -kMinDeg[axis] * (calibration.centerUs - calibration.minUs);
  }
  return static_cast<uint16_t>(lroundf(pulse));
}

void writeCommanded() {
  if (!driverReady || !outputsEnabled) return;
  for (uint8_t axis = 0; axis < kAxisCount; ++axis) {
    servos.writeMicroseconds(axis, angleToPulse(axis, commandedDeg[axis]));
  }
}

void clearPlan() {
  expectedSegments = 0;
  receivedSegments = 0;
  planDurationMs = 0;
  trajectoryTimeMs = 0;
  stopTimeMs = 0;
  manualMoving = false;
}

void disableOutputs() {
  servos.disableAll();
  outputsEnabled = false;
  clearPlan();
  mode = MotionMode::kDisarmed;
}

void addState(JsonObject state) {
  state["firmware_version"] = kFirmwareVersion;
  state["model_id"] = kModelId;
  state["driver_ready"] = driverReady;
  state["armed"] = isArmed();
  state["outputs_enabled"] = outputsEnabled;
  state["mode"] = modeName();
  state["measured_feedback"] = false;
  state["measured_q_deg"] = nullptr;
  JsonArray q = state["commanded_q_deg"].to<JsonArray>();
  for (float angle : commandedDeg) q.add(angle);
  JsonArray calibrated = state["calibrated"].to<JsonArray>();
  JsonArray calibration = state["calibration"].to<JsonArray>();
  for (const auto& item : calibrations) {
    calibrated.add(item.confirmed);
    JsonObject row = calibration.add<JsonObject>();
    row["min_us"] = item.minUs;
    row["center_us"] = item.centerUs;
    row["max_us"] = item.maxUs;
    row["reversed"] = item.reversed;
    row["confirmed"] = item.confirmed;
  }
}

void reply(uint32_t id, bool ok, const char* error = nullptr) {
  JsonDocument response;
  response["protocol_version"] = 1;
  response["reply_to"] = id;
  response["ok"] = ok;
  if (error) response["error"] = error;
  JsonObject state = response["state"].to<JsonObject>();
  addState(state);
  serializeJson(response, Serial);
  Serial.write('\n');
}

void saveCalibration(uint8_t axis) {
  char key[12];
  snprintf(key, sizeof(key), "a%u_min", axis);
  preferences.putUShort(key, calibrations[axis].minUs);
  snprintf(key, sizeof(key), "a%u_ctr", axis);
  preferences.putUShort(key, calibrations[axis].centerUs);
  snprintf(key, sizeof(key), "a%u_max", axis);
  preferences.putUShort(key, calibrations[axis].maxUs);
  snprintf(key, sizeof(key), "a%u_rev", axis);
  preferences.putBool(key, calibrations[axis].reversed);
  snprintf(key, sizeof(key), "a%u_ok", axis);
  preferences.putBool(key, true);
}

void loadCalibration() {
  char key[12];
  for (uint8_t axis = 0; axis < kAxisCount; ++axis) {
    snprintf(key, sizeof(key), "a%u_min", axis);
    calibrations[axis].minUs = preferences.getUShort(key, 1300);
    snprintf(key, sizeof(key), "a%u_ctr", axis);
    calibrations[axis].centerUs = preferences.getUShort(key, 1500);
    snprintf(key, sizeof(key), "a%u_max", axis);
    calibrations[axis].maxUs = preferences.getUShort(key, 1700);
    snprintf(key, sizeof(key), "a%u_rev", axis);
    calibrations[axis].reversed = preferences.getBool(key, false);
    snprintf(key, sizeof(key), "a%u_ok", axis);
    calibrations[axis].confirmed = preferences.getBool(key, false);
    if (!(500 <= calibrations[axis].minUs &&
          calibrations[axis].minUs < calibrations[axis].centerUs &&
          calibrations[axis].centerUs < calibrations[axis].maxUs &&
          calibrations[axis].maxUs <= 2500)) {
      calibrations[axis] = AxisCalibration{};
    }
    servos.setCalibration(axis, calibrations[axis].minUs,
                          calibrations[axis].maxUs,
                          calibrations[axis].centerUs,
                          calibrations[axis].reversed);
  }
}

void evaluateTrajectory(float trajectoryMs) {
  if (receivedSegments == 0) return;
  uint16_t index = receivedSegments - 1;
  for (uint16_t i = 0; i < receivedSegments; ++i) {
    if (trajectoryMs < segments[i].atMs + segments[i].durationMs) {
      index = i;
      break;
    }
  }
  const Segment& segment = segments[index];
  const float* start = index == 0 ? planStartDeg : segments[index - 1].endDeg;
  const float elapsed = constrain(trajectoryMs - segment.atMs, 0.0F,
                                  static_cast<float>(segment.durationMs));
  const float u = quintic(elapsed / segment.durationMs);
  for (uint8_t axis = 0; axis < kAxisCount; ++axis) {
    commandedDeg[axis] = start[axis] + (segment.endDeg[axis] - start[axis]) * u;
  }
  writeCommanded();
}

void beginStop(bool pause) {
  manualMoving = false;
  if (mode != MotionMode::kRunning && mode != MotionMode::kStopping) {
    clearPlan();
    mode = pause && mode == MotionMode::kPaused
               ? MotionMode::kPaused
               : MotionMode::kArmed;
    return;
  }
  if (mode == MotionMode::kStopping) {
    if (!pause) pauseAfterStop = false;
    return;
  }
  pauseAfterStop = pause;
  stopTimeMs = 0;
  stopDurationMs = 80;
  for (uint16_t i = 0; i < receivedSegments; ++i) {
    const float* start = i == 0 ? planStartDeg : segments[i - 1].endDeg;
    const float seconds = segments[i].durationMs / 1000.0F;
    for (uint8_t axis = 0; axis < kAxisCount; ++axis) {
      const float velocity = 1.875F * fabsf(segments[i].endDeg[axis] - start[axis]) / seconds;
      const float requiredMs = 1000.0F * velocity / (kMaxAccelerationDegS2[axis] * 0.5F);
      stopDurationMs = max(stopDurationMs, requiredMs);
    }
  }
  mode = MotionMode::kStopping;
}

void handleCommand(const char* line) {
  JsonDocument request;
  DeserializationError parseError = deserializeJson(request, line);
  if (parseError) return;
  const uint32_t id = request["id"] | 0;
  if ((request["protocol_version"] | 0) != 1) {
    reply(id, false, "unsupported protocol_version");
    return;
  }
  const char* command = request["command"] | "";
  lastContactMs = millis();

  if (!strcmp(command, "hello") || !strcmp(command, "heartbeat")) {
    reply(id, true);
    return;
  }
  if (!strcmp(command, "disarm")) {
    disableOutputs();
    reply(id, true);
    return;
  }
  if (!strcmp(command, "set_calibration")) {
    if (outputsEnabled) {
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
    AxisCalibration& item = calibrations[axis];
    item.minUs = minUs;
    item.centerUs = centerUs;
    item.maxUs = maxUs;
    item.reversed = request["reversed"] | false;
    item.confirmed = true;
    servos.setCalibration(axis, minUs, maxUs, centerUs, item.reversed);
    saveCalibration(axis);
    reply(id, true);
    return;
  }
  if (!strcmp(command, "center_axis")) {
    const int axis = request["axis"] | -1;
    if (!driverReady || axis < 0 || axis >= kAxisCount ||
        !calibrations[axis].confirmed || isArmed()) {
      reply(id, false, "axis is not calibrated or controller is armed");
      return;
    }
    servos.disableAll();
    servos.center(axis);
    outputsEnabled = true;
    mode = MotionMode::kService;
    reply(id, true);
    return;
  }
  if (!strcmp(command, "arm")) {
    float target[kAxisCount];
    if (!driverReady || !allCalibrated() ||
        !readJointArray(request["q_deg"], target)) {
      reply(id, false, "driver/calibration/joint target is not ready");
      return;
    }
    clearPlan();
    memcpy(commandedDeg, target, sizeof(commandedDeg));
    outputsEnabled = true;
    mode = MotionMode::kArmed;
    writeCommanded();
    reply(id, true);
    return;
  }
  if (!isArmed()) {
    reply(id, false, "controller is not armed");
    return;
  }
  if (!strcmp(command, "target")) {
    float target[kAxisCount];
    const uint32_t duration = request["duration_ms"] | 0;
    if (mode != MotionMode::kArmed || duration < 20 || duration > 5000 ||
        !readJointArray(request["q_deg"], target)) {
      reply(id, false, "invalid manual target or controller mode");
      return;
    }
    memcpy(manualStartDeg, commandedDeg, sizeof(commandedDeg));
    memcpy(manualEndDeg, target, sizeof(target));
    manualStartedMs = millis();
    manualDurationMs = duration;
    manualMoving = true;
    reply(id, true);
    return;
  }
  if (!strcmp(command, "prepare")) {
    const int count = request["count"] | 0;
    float start[kAxisCount];
    const char* modelId = request["model_id"] | "";
    if ((mode != MotionMode::kArmed && mode != MotionMode::kPaused) ||
        count < 1 || count > kMaxSegments || strcmp(modelId, kModelId) ||
        !readJointArray(request["start_deg"], start)) {
      reply(id, false, "invalid trajectory header");
      return;
    }
    for (uint8_t axis = 0; axis < kAxisCount; ++axis) {
      if (fabsf(start[axis] - commandedDeg[axis]) > 1.0F) {
        reply(id, false, "trajectory start differs from commanded pose");
        return;
      }
    }
    clearPlan();
    expectedSegments = count;
    memcpy(planStartDeg, start, sizeof(start));
    mode = MotionMode::kPrepared;
    reply(id, true);
    return;
  }
  if (!strcmp(command, "segment")) {
    const int index = request["index"] | -1;
    const uint32_t duration = request["duration_ms"] | 0;
    float end[kAxisCount];
    if (mode != MotionMode::kPrepared || index != receivedSegments ||
        receivedSegments >= expectedSegments || duration < 20 || duration > 60000 ||
        !readJointArray(request["end_deg"], end)) {
      reply(id, false, "invalid trajectory segment");
      return;
    }
    Segment& segment = segments[receivedSegments];
    memcpy(segment.endDeg, end, sizeof(end));
    segment.atMs = planDurationMs;
    segment.durationMs = duration;
    planDurationMs += duration;
    ++receivedSegments;
    reply(id, true);
    return;
  }
  if (!strcmp(command, "commit")) {
    const uint32_t delayMs = request["start_delay_ms"] | 0;
    if (mode != MotionMode::kPrepared || receivedSegments != expectedSegments ||
        delayMs < 100 || delayMs > 2000) {
      reply(id, false, "trajectory is incomplete or start delay is invalid");
      return;
    }
    trajectoryTimeMs = 0;
    scheduledStartMs = millis() + delayMs;
    mode = MotionMode::kWaiting;
    reply(id, true);
    return;
  }
  if (!strcmp(command, "pause")) {
    if (mode == MotionMode::kWaiting || mode == MotionMode::kPrepared) {
      clearPlan();
      mode = MotionMode::kArmed;
    } else {
      beginStop(true);
    }
    reply(id, true);
    return;
  }
  if (!strcmp(command, "stop")) {
    if (mode == MotionMode::kWaiting || mode == MotionMode::kPrepared ||
        mode == MotionMode::kPaused) {
      clearPlan();
      mode = MotionMode::kArmed;
    } else {
      beginStop(false);
    }
    reply(id, true);
    return;
  }
  reply(id, false, "unknown command");
}

void controlTick(uint32_t now) {
  if (mode == MotionMode::kWaiting &&
      static_cast<int32_t>(now - scheduledStartMs) >= 0) {
    mode = MotionMode::kRunning;
  }
  if (mode == MotionMode::kRunning) {
    trajectoryTimeMs = min(trajectoryTimeMs + kControlPeriodMs,
                           static_cast<float>(planDurationMs));
    evaluateTrajectory(trajectoryTimeMs);
    if (trajectoryTimeMs >= planDurationMs) {
      clearPlan();
      mode = MotionMode::kArmed;
    }
  } else if (mode == MotionMode::kStopping) {
    const float oldStop = stopTimeMs;
    const float newStop = min(stopDurationMs, oldStop + kControlPeriodMs);
    trajectoryTimeMs += (newStop - oldStop) -
                        (newStop * newStop - oldStop * oldStop) /
                            (2.0F * stopDurationMs);
    trajectoryTimeMs = min(trajectoryTimeMs, static_cast<float>(planDurationMs));
    stopTimeMs = newStop;
    evaluateTrajectory(trajectoryTimeMs);
    if (stopTimeMs >= stopDurationMs || trajectoryTimeMs >= planDurationMs) {
      clearPlan();
      mode = pauseAfterStop ? MotionMode::kPaused : MotionMode::kArmed;
    }
  }

  if (manualMoving && mode == MotionMode::kArmed) {
    const uint32_t elapsed = now - manualStartedMs;
    const float u = quintic(static_cast<float>(min(elapsed, manualDurationMs)) /
                            manualDurationMs);
    for (uint8_t axis = 0; axis < kAxisCount; ++axis) {
      commandedDeg[axis] = manualStartDeg[axis] +
                           (manualEndDeg[axis] - manualStartDeg[axis]) * u;
    }
    writeCommanded();
    if (elapsed >= manualDurationMs) manualMoving = false;
  }
}

void serviceSerial() {
  while (Serial.available()) {
    const char value = static_cast<char>(Serial.read());
    if (value == '\n') {
      inputLine[inputLength] = '\0';
      if (inputLength) handleCommand(inputLine);
      inputLength = 0;
    } else if (value != '\r') {
      if (inputLength + 1 < sizeof(inputLine)) {
        inputLine[inputLength++] = value;
      } else {
        inputLength = 0;
      }
    }
  }
}

}  // namespace

void setup() {
  Serial.begin(921600);
  preferences.begin("cyberarm", false);
  loadCalibration();
  driverReady = servos.begin(CYBERARM_I2C_SDA, CYBERARM_I2C_SCL, 400000, 50.0F);
  // begin() touches the PCA9685, so force all channels off again before any
  // host connection. A serial handshake alone can never energise a servo.
  servos.disableAll();
  mode = driverReady ? MotionMode::kDisarmed : MotionMode::kFault;
  lastContactMs = millis();
  lastControlMs = millis();
}

void loop() {
  serviceSerial();
  const uint32_t now = millis();
  while (now - lastControlMs >= kControlPeriodMs) {
    lastControlMs += kControlPeriodMs;
    controlTick(lastControlMs);
    // Do not replay a long burst after a debugger break or CPU stall.
    if (now - lastControlMs > 200) lastControlMs = now;
  }
  if (outputsEnabled && now - lastContactMs > kWatchdogMs &&
      mode != MotionMode::kFault) {
    manualMoving = false;
    clearPlan();
    if (mode == MotionMode::kService) {
      disableOutputs();
    } else {
      // Keep the last PWM to avoid dropping a loaded arm. Re-arming is required
      // after reconnect; the physical power switch remains the emergency stop.
      mode = MotionMode::kFault;
    }
  }
}
