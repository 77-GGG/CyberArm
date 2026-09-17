#pragma once
#include <cstdint>
#include <map>
namespace cyberarm {
class PCA9685Servo {
 public:
  static inline std::map<int,int> outputs;
  static inline int lastSda=-1,lastScl=-1,lastAddress=-1;
  explicit PCA9685Servo(int address){lastAddress=address;}
  bool begin(int sda,int scl,uint32_t,float){lastSda=sda;lastScl=scl;return true;}
  PCA9685Servo& rawDriver(){return *this;}
  void setOscillatorFrequency(uint32_t){}
  void setFrequency(float){}
  uint8_t readPrescale(){return 121;}
  int setPWM(int channel,int,int ticks){outputs[channel]=ticks;return 0;}
  void disableAll(){for(int i=0;i<16;++i)outputs[i]=4096;}
};
}
