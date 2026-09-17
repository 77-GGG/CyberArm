#pragma once
#include <cmath>
#include <cstdint>
#include <algorithm>

namespace cyberarm { namespace firmware {
constexpr unsigned kMappingPoints = 7;
struct CalibrationPoint { float deg = 0; float us = 0; };
struct JointMapping {
  uint32_t schema = 1;
  uint32_t revision = 0;
  uint8_t count = 0;
  float low = 0, high = 0;
  CalibrationPoint points[kMappingPoints];
  char wiringHash[17] = {};
  char modelId[24] = {};
};
inline bool validMapping(const JointMapping& m) {
  if(m.schema != 1 || m.count < 3 || m.count > kMappingPoints ||
     !std::isfinite(m.low) || !std::isfinite(m.high) || m.low >= 0 || m.high <= 0) return false;
  bool zero = false;
  float sign = m.points[1].us - m.points[0].us;
  if(sign == 0) return false;
  for(unsigned i=0;i<m.count;++i) {
    const auto& p=m.points[i];
    if(!std::isfinite(p.deg) || !std::isfinite(p.us) || p.deg < -180 || p.deg > 180 || p.us < 500 || p.us > 2500) return false;
    zero |= p.deg == 0;
    if(i && (p.deg <= m.points[i-1].deg || (p.us-m.points[i-1].us)*sign <= 0)) return false;
  }
  return zero && m.low >= m.points[0].deg && m.high <= m.points[m.count-1].deg;
}
inline bool mapAngle(const JointMapping& m, float q, float& pulse) {
  if(!validMapping(m) || !std::isfinite(q) || q < m.low || q > m.high) return false;
  for(unsigned i=1;i<m.count;++i) if(q <= m.points[i].deg) {
    const auto& a=m.points[i-1]; const auto& b=m.points[i];
    pulse=a.us+(q-a.deg)*(b.us-a.us)/(b.deg-a.deg); return true;
  }
  return false;
}
inline uint32_t moveDuration(float delta, float vmax, float amax) {
  return static_cast<uint32_t>(std::ceil(1000 * std::max(1.875f*std::fabs(delta)/vmax,
      std::sqrt(5.773503f*std::fabs(delta)/amax))));
}
// Independent lease: ordinary transport heartbeats never call renew().
struct AxisTest {
  bool active=false;
  int axis=-1;
  uint32_t session=0, renewed=0, previous=0;
  float pulse=1500, target=1500, low=1400, high=1600, rate=100;
  void begin(int a, uint32_t id, float p, float l, float h, float r, uint32_t now) {
    active=true;axis=a;session=id;pulse=target=p;low=l;high=h;rate=r;renewed=previous=now;
  }
  bool owns(uint32_t id) const { return active && session==id; }
  void hold() { target=pulse; }
  bool tick(uint32_t now) {
    if(!active) return false;
    if(now-renewed >= 1200) { active=false;return false; }
    float step=rate*std::min<uint32_t>(now-previous,40)/1000.f;previous=now;
    pulse+=std::max(-step,std::min(step,target-pulse));return true;
  }
};
} }
