#include <cassert>
#include <iostream>
#include "MotionController.h"
#include "CommandProtocol.h"
#include <string>
using namespace cyberarm::firmware;
struct TestStream:Stream{
 std::string input,output;
 int available() override{return input.size();}
 int read() override{char c=input[0];input.erase(0,1);return c;}
 size_t write(uint8_t c) override{output+=char(c);return 1;}
 size_t write(const uint8_t* p,size_t n) override{output.append((const char*)p,n);return n;}
};
int main(){
  JointMapping m{};m.count=3;m.low=-10;m.high=10;
  m.points[0]={-10,1400};m.points[1]={0,1500};m.points[2]={10,1620};
  assert(validMapping(m));float pulse=0;
  assert(mapAngle(m,5,pulse)&&std::fabs(pulse-1560)<.01);
  m.low=-5;m.high=5;assert(mapAngle(m,5,pulse)&&pulse==1560);
  assert(!mapAngle(m,6,pulse));
  auto reversed=m;reversed.points[0].us=1620;reversed.points[2].us=1400;
  assert(validMapping(reversed));assert(mapAngle(reversed,5,pulse)&&pulse==1450);
  reversed.points[1].us=1700;assert(!validMapping(reversed));
  AxisTest t;t.begin(2,42,1500,1400,1600,100,0);t.target=1600;
  assert(t.tick(20)&&t.pulse==1502);t.hold();assert(t.tick(40)&&t.pulse==1502);
  assert(!t.owns(43));assert(t.tick(1199));assert(!t.tick(1200));
  t.begin(0,7,1500,1400,1600,100,UINT32_MAX-100);t.target=1520;
  assert(t.tick(10));assert(!t.tick(1200));
  ServoSubsystem servos;assert(servos.begin());
  assert(cyberarm::PCA9685Servo::lastSda==cyberarm::wiring::kSda);
  assert(cyberarm::PCA9685Servo::lastScl==cyberarm::wiring::kScl);
  assert(!servos.allCalibrated());
  assert(servos.testPulse(2,1500));
  assert(cyberarm::PCA9685Servo::outputs[cyberarm::wiring::kChannels[2]]!=4096);
  for(int i=0;i<16;++i)if(i!=cyberarm::wiring::kChannels[2])assert(cyberarm::PCA9685Servo::outputs[i]==4096);
  assert(!servos.saveMapping(2,m));servos.disableAll();
  for(int i=0;i<6;++i)assert(servos.saveMapping(i,m));
  assert(servos.allCalibrated());
  Preferences::failWrite=true;assert(!servos.saveMapping(0,m));assert(servos.mapping(0).revision==1);Preferences::failWrite=false;
  ServoSubsystem reboot;assert(reboot.begin()&&reboot.allCalibrated());
  MotionController motion(reboot);motion.initialize(true);
  float q[6]={3,0,0,0,0,0};motion.arm(q,100);
  assert(motion.mode()==MotionMode::kArming);motion.tick(80);assert(motion.commandedDeg()[0]==0);
  motion.tick(400);assert(motion.commandedDeg()[0]>0&&motion.commandedDeg()[0]<3);
  motion.tick(2100);assert(motion.mode()==MotionMode::kArmed&&motion.commandedDeg()[0]==3);
  motion.handleWatchdog();motion.stop();assert(motion.mode()==MotionMode::kFault);
  motion.disarm();assert(!reboot.outputsEnabled());
  TestStream serial;CommandProtocol protocol(serial,motion,reboot);protocol.begin(0);
  auto command=[&](const std::string& fields){
    serial.input="{\"protocol_version\":1,\"id\":1,"+fields+"}\n";serial.output.clear();
    protocol.service();JsonDocument response;assert(!deserializeJson(response,serial.output));return response;
  };
  fakeNow=0;
  auto reply=command("\"command\":\"test_begin\",\"axis\":1,\"test_session\":7,\"pulse_us\":1500,\"low_us\":1400,\"high_us\":1600,\"rate_us_s\":50,\"confirmation\":\"SUPPORTED\"");
  assert(reply["ok"].as<bool>()&&reply["state"]["test"]["active"].as<bool>());
  assert(!command("\"command\":\"arm\",\"q_deg\":[0,0,0,0,0,0]")["ok"].as<bool>());
  assert(!command("\"command\":\"test_target\",\"test_session\":8,\"pulse_us\":1520")["ok"].as<bool>());
  assert(command("\"command\":\"test_target\",\"test_session\":7,\"pulse_us\":1520")["ok"].as<bool>());
  fakeNow=800;command("\"command\":\"heartbeat\"");protocol.tick(fakeNow);
  fakeNow=1200;protocol.tick(fakeNow);assert(!reboot.outputsEnabled());
  assert(!command("\"command\":\"test_renew\",\"test_session\":7")["ok"].as<bool>());
  assert(command("\"command\":\"arm\",\"q_deg\":[3,0,0,0,0,0]")["ok"].as<bool>());
  assert(!command("\"command\":\"target\",\"duration_ms\":120,\"q_deg\":[0,0,0,0,0,0]")["ok"].as<bool>());
  assert(!command("\"command\":\"prepare\",\"model_id\":\"revc-sim-1\",\"count\":1,\"start_deg\":[3,0,0,0,0,0]")["ok"].as<bool>());
  command("\"command\":\"disarm\"");
  // Editable model limits are independent of the angle mapping and survive reboot.
  const std::string limitFields=std::string("\"command\":\"save_limits\",\"axis\":0,\"low_deg\":-75,\"high_deg\":80,\"confirmed\":true,\"expected_revision\":0,\"model_id\":\"revc-sim-1\",\"wiring_hash\":\"")+cyberarm::wiring::kHash+"\"";
  Preferences::failWrite=true;assert(!command(limitFields)["ok"].as<bool>());Preferences::failWrite=false;
  assert(reboot.limits(0).revision==0);
  reply=command(limitFields);assert(reply["ok"].as<bool>());
  assert(reply["state"]["model_limits_deg"][0][1].as<float>()==80);
  assert(reply["state"]["limits_revisions"][0].as<int>()==1);
  assert(!command(limitFields)["ok"].as<bool>()); // stale revision
  assert(!command("\"command\":\"arm\",\"q_deg\":[60,0,0,0,0,0]")["ok"].as<bool>()); // mapping still ±5
  JointMapping wide=m;wide.low=-90;wide.high=90;wide.points[0]={-90,1000};wide.points[2]={90,2000};
  assert(reboot.saveMapping(0,wide));
  assert(command("\"command\":\"arm\",\"q_deg\":[60,0,0,0,0,0]")["ok"].as<bool>());
  JointLimits narrow{};narrow.low=-20;narrow.high=20;
  assert(!reboot.saveLimits(0,narrow)); // active outputs
  command("\"command\":\"disarm\"");
  assert(!command("\"command\":\"arm\",\"q_deg\":[85,0,0,0,0,0]")["ok"].as<bool>());
  ServoSubsystem limitsReboot;assert(limitsReboot.begin());
  assert(limitsReboot.limits(0).low==-75&&limitsReboot.limits(0).high==80&&limitsReboot.limits(0).revision==1);
  assert(limitsReboot.anglePulse(0,60,pulse)&&!limitsReboot.anglePulse(0,85,pulse));
  narrow.low=0;assert(!limitsReboot.saveLimits(0,narrow));
  // Oversized line must not execute a valid JSON suffix.
  serial.input=std::string(2048,'x')+"{\"protocol_version\":1,\"command\":\"arm\",\"q_deg\":[0,0,0,0,0,0]}\n";
  protocol.service();protocol.service();assert(!reboot.outputsEnabled());
  std::cout<<"mapping, lease, channel routing, NVS persistence, ramp and fault tests passed\n";
}
