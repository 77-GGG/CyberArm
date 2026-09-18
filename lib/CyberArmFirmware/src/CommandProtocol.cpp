#include "CommandProtocol.h"

#include <math.h>
#include <string.h>

namespace cyberarm {
namespace firmware {

void CommandProtocol::service() {
  unsigned budget=2048;
  while (serial_.available() && budget--) {
    const char value = static_cast<char>(serial_.read());
    if (value == '\n') {
      inputLine_[inputLength_] = '\0';
      if (inputLength_ && !droppingLine_) handleCommand(inputLine_);
      inputLength_ = 0;
      droppingLine_ = false;
    } else if (value != '\r') {
      if (inputLength_ + 1 < sizeof(inputLine_)) {
        inputLine_[inputLength_++] = value;
      } else {
        inputLength_ = 0;
        droppingLine_ = true;
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
    if (!isfinite(angle) || angle < servos_.limits(i).low - 0.001F ||
        angle > servos_.limits(i).high + 0.001F) {
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

  if (!strcmp(command, "hello")) {
    reply(id, true);
    return;
  }
  if (!strcmp(command, "heartbeat")) {
    replyRuntime(id, true);
    return;
  }
  if (!strcmp(command, "disarm")) {
    test_.active=false;
    motion_.disarm();
    reply(id, true);
    return;
  }
  if (debugCommand(command,request,id)) return;
  if (!strcmp(command, "set_calibration") || !strcmp(command, "center_axis")) {
    reply(id,false,"use axis calibration workbench (firmware 0.3)");return;
  }
  if (!strcmp(command, "arm")) {
    float target[kAxisCount];
    if (motion_.mode()!=MotionMode::kDisarmed || test_.active || !servos_.driverReady() || !servos_.allCalibrated() ||
        !readJointArray(request["q_deg"], target) || !servos_.validTarget(target) ||
        !servos_.validTarget(motion_.commandedDeg())) {
      reply(id, false, "driver/calibration/joint target is not ready");
      return;
    }
    motion_.arm(target, millis());
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
        duration > 5000 || !readJointArray(request["q_deg"], target) || !servos_.validTarget(target)) {
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
    if (motion_.manualMoving() || (motion_.mode() != MotionMode::kArmed &&
         motion_.mode() != MotionMode::kPaused) ||
        count < 1 || count > kMaxSegments || strcmp(modelId, kModelId) ||
        !readJointArray(request["start_deg"], start) || !servos_.validTarget(start)) {
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
        !readJointArray(request["end_deg"], end) || !servos_.validTarget(end) || !motion_.segmentDurationValid(end,duration)) {
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

void CommandProtocol::tick(uint32_t now) {
  if(!test_.active) return;
  if(!test_.tick(now) || !servos_.testPulse(test_.axis,test_.pulse)) {
    test_.active=false;motion_.disarm();
  }
}

bool CommandProtocol::debugCommand(const char* command,JsonDocument& r,uint32_t id) {
  if(!strcmp(command,"save_limits")) {
    const int axis=r["axis"] | -1;
    JointLimits limits{};limits.low=r["low_deg"] | NAN;limits.high=r["high_deg"] | NAN;
    if(axis<0 || axis>=kAxisCount || motion_.mode()!=MotionMode::kDisarmed || test_.active ||
       strcmp(r["wiring_hash"] | "",wiring::kHash) || strcmp(r["model_id"] | "",kModelId) ||
       (r["expected_revision"] | UINT32_MAX)!=servos_.limits(axis).revision ||
       !r["confirmed"].is<bool>() || !r["confirmed"].as<bool>() || !servos_.saveLimits(axis,limits))
      reply(id,false,"invalid limits, output active, stale revision or save failed");
    else reply(id,true);
    return true;
  }
  if(!strcmp(command,"save_mapping")) {
    const int axis=r["axis"] | -1;
    JointMapping m{};
    JsonArrayConst points=r["points"].as<JsonArrayConst>();
    m.low=r["low_deg"] | NAN;m.high=r["high_deg"] | NAN;
    bool valid=points.size()>=3 && points.size()<=kMappingPoints;
    m.count=valid ? points.size() : 0;
    for(unsigned i=0;i<m.count;++i) {
      m.points[i].deg=points[i]["deg"] | NAN;m.points[i].us=points[i]["us"] | NAN;
    }
    if(axis<0 || axis>=kAxisCount || motion_.mode()!=MotionMode::kDisarmed ||
       strcmp(r["wiring_hash"] | "",wiring::kHash) || strcmp(r["model_id"] | "",kModelId) ||
       (axis>=0 && axis<kAxisCount && (r["expected_revision"] | UINT32_MAX)!=servos_.mapping(axis).revision) ||
       !r["confirmed"].is<bool>() || !r["confirmed"].as<bool>() || !valid ||
       !servos_.saveMapping(axis,m)) reply(id,false,"invalid mapping, output active or save failed");
    else reply(id,true);
    return true;
  }
  if(strncmp(command,"test_",5)) return false;
  const uint32_t session=r["test_session"] | 0;
  const uint32_t now=millis();
  // Check expiry before processing renewals, even if the main loop was stalled.
  if(test_.active && now-test_.renewed>=1200) { test_.active=false;motion_.disarm(); }
  if(!strcmp(command,"test_begin")) {
    int axis=r["axis"] | -1;
    float pulse=r["pulse_us"] | NAN,low=r["low_us"] | NAN,high=r["high_us"] | NAN,rate=r["rate_us_s"] | NAN;
    if(motion_.mode()!=MotionMode::kDisarmed || test_.active || !servos_.driverReady() ||
       !session || axis<0 || axis>=kAxisCount || !isfinite(pulse) || !isfinite(low) || !isfinite(high) ||
       !isfinite(rate) || low<500 || high>2500 || low>=high || pulse<low || pulse>high || rate<5 || rate>200 ||
       strcmp(r["confirmation"] | "","SUPPORTED")) {
      reply(id,false,"invalid test start or controller busy");return true;
    }
    servos_.disableAll();motion_.enterService(axis);
    test_.begin(axis,session,pulse,low,high,rate,now);
    if(!servos_.testPulse(axis,pulse)) { test_.active=false;motion_.disarm();reply(id,false,"PWM write failed"); }
    else reply(id,true);
    return true;
  }
  if(!test_.owns(session)) { reply(id,false,"test session expired or not owner");return true; }
  if(!strcmp(command,"test_target")) {
    float pulse=r["pulse_us"] | NAN;
    if(!isfinite(pulse) || pulse<test_.low || pulse>test_.high || fabsf(pulse-test_.pulse)>100) {
      reply(id,false,"test target outside window or step exceeds 100 us");return true;
    }
    test_.target=pulse;
  } else if(!strcmp(command,"test_hold")) test_.hold();
  else if(!strcmp(command,"test_end")) { test_.active=false;motion_.disarm(); }
  else if(!strcmp(command,"test_renew")) { test_.renewed=now;replyRuntime(id,true);return true; }
  else { reply(id,false,"unknown test command");return true; }
  test_.renewed=now;reply(id,true);return true;
}

void CommandProtocol::addRuntimeState(JsonObject state) const {
  state["motion_busy"] = motion_.manualMoving();
  JsonObject test=state["test"].to<JsonObject>();
  test["active"]=test_.active;test["axis"]=test_.active ? test_.axis+1 : 0;
  test["pulse_us"]=test_.pulse;test["target_us"]=test_.target;
  test["ticks"]=servos_.pulseTicks(test_.pulse);
  test["nominal_us"]=servos_.pulseTicks(test_.pulse)*servos_.tickUs();
  test["moving"]=test_.active && fabsf(test_.pulse-test_.target)>.01f;
  state["armed"] = motion_.isArmed();
  state["outputs_enabled"] = servos_.outputsEnabled();
  state["mode"] = motion_.modeName();
  JsonArray q = state["commanded_q_deg"].to<JsonArray>();
  for (uint8_t axis = 0; axis < kAxisCount; ++axis) {
    q.add(motion_.commandedDeg()[axis]);
  }
}

void CommandProtocol::addState(JsonObject state) const {
  state["firmware_version"] = kFirmwareVersion;
  state["capabilities"]["axis_calibration"] = 1;
  state["capabilities"]["editable_limits"] = 1;
  JsonArray limits=state["model_limits_deg"].to<JsonArray>();
  JsonArray revisions=state["limits_revisions"].to<JsonArray>();
  for(uint8_t i=0;i<kAxisCount;++i) {
    JsonArray row=limits.add<JsonArray>();row.add(servos_.limits(i).low);row.add(servos_.limits(i).high);
    revisions.add(servos_.limits(i).revision);
  }
  char deviceId[17];snprintf(deviceId,sizeof(deviceId),"%016llx",static_cast<unsigned long long>(ESP.getEfuseMac()));
  state["device_id"] = deviceId;
  state["wiring_hash"] = wiring::kHash;
  JsonDocument wiringDoc;deserializeJson(wiringDoc,wiring::kJson);state["wiring"]=wiringDoc;
  state["tick_us"] = servos_.tickUs();
  addRuntimeState(state);
  JsonArray mappings=state["mappings"].to<JsonArray>();
  for(uint8_t i=0;i<kAxisCount;++i) {
    const auto& m=servos_.mapping(i);JsonObject row=mappings.add<JsonObject>();
    row["revision"]=m.revision;row["confirmed"]=validMapping(m);
    row["low_deg"]=max(servos_.limits(i).low,m.low);row["high_deg"]=min(servos_.limits(i).high,m.high);
    row["work_low_deg"]=m.low;row["work_high_deg"]=m.high;
    JsonArray points=row["points"].to<JsonArray>();
    for(unsigned j=0;j<m.count;++j) { JsonObject p=points.add<JsonObject>();p["deg"]=m.points[j].deg;p["us"]=m.points[j].us; }
  }

  state["model_id"] = kModelId;
  state["driver_ready"] = servos_.driverReady();
  state["measured_feedback"] = false;
  state["measured_q_deg"] = nullptr;
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

void CommandProtocol::replyRuntime(uint32_t id, bool ok, const char* error) {
  JsonDocument response;
  response["protocol_version"] = 1;
  response["reply_to"] = id;
  response["ok"] = ok;
  if (error) response["error"] = error;
  JsonObject state = response["state"].to<JsonObject>();
  addRuntimeState(state);
  serializeJson(response, serial_);
  serial_.write('\n');
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
