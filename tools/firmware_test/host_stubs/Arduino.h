#pragma once
#include <cstdint>
#include <cstring>
#include <cmath>
#include <algorithm>
#include <cstddef>
#include <cstdio>
using std::min;using std::max;using std::isfinite;
template<class T> T constrain(T v,T lo,T hi){return std::max(lo,std::min(hi,v));}
inline uint32_t fakeNow=0;
inline uint32_t millis(){return fakeNow;}
struct FakeESP{uint64_t getEfuseMac(){return 12345;}};
inline FakeESP ESP;
class Stream{
 public:
  virtual int available()=0;
  virtual int read()=0;
  virtual size_t write(uint8_t)=0;
  virtual size_t write(const uint8_t*,size_t)=0;
};
