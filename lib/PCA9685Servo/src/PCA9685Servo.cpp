#include "PCA9685Servo.h"

#include <math.h>

namespace cyberarm {

// 保存 I2C 总线引用，并使用指定地址构造底层 Adafruit 驱动。
PCA9685Servo::PCA9685Servo(uint8_t address, TwoWire& wire)
    : wire_(wire),
      pwm_(address, wire),
      address_(address),
      frequencyHz_(50.0F),
      ready_(false) {}

bool PCA9685Servo::begin(int sdaPin, int sclPin, uint32_t i2cClockHz,
                         float pwmFrequencyHz) {
  // 每次重新初始化前先清除就绪状态，避免失败后继续发送控制命令。
  ready_ = false;

  // GPIO 必须有效，I2C 时钟也不能为 0。
  if (sdaPin < 0 || sclPin < 0 || i2cClockHz == 0) {
    return false;
  }

  // ESP32 Arduino 支持在 begin() 时指定 SDA、SCL 和总线频率。
  if (!wire_.begin(sdaPin, sclPin, i2cClockHz)) {
    return false;
  }

  return initializeDriver(pwmFrequencyHz);
}

bool PCA9685Servo::beginWithConfiguredWire(float pwmFrequencyHz) {
  // 不重复配置 I2C 引脚，适合多个设备共享已初始化的 Wire。
  ready_ = false;
  return initializeDriver(pwmFrequencyHz);
}

bool PCA9685Servo::initializeDriver(float pwmFrequencyHz) {
  // pwm_.begin() 会通过 I2C 检测指定地址上的 PCA9685。
  if (!isValidFrequency(pwmFrequencyHz) || !pwm_.begin()) {
    return false;
  }

  // 舵机常用 50 Hz；修改频率后短暂等待芯片稳定。
  pwm_.setPWMFreq(pwmFrequencyHz);
  delay(10);

  frequencyHz_ = pwmFrequencyHz;
  ready_ = true;
  return true;
}

bool PCA9685Servo::setFrequency(float pwmFrequencyHz) {
  // 未初始化时禁止操作，防止向不存在的设备发送数据。
  if (!ready_ || !isValidFrequency(pwmFrequencyHz)) {
    return false;
  }

  pwm_.setPWMFreq(pwmFrequencyHz);
  delay(10);
  frequencyHz_ = pwmFrequencyHz;
  return true;
}

bool PCA9685Servo::setCalibration(uint8_t channel, uint16_t minPulseUs,
                                   uint16_t maxPulseUs,
                                   uint16_t centerPulseUs, bool reversed) {
  // 校准可在 begin() 前设置，但必须满足绝对保护范围和 min<center<max。
  if (!isValidChannel(channel) ||
      !isValidCalibration(minPulseUs, maxPulseUs, centerPulseUs)) {
    return false;
  }

  calibrations_[channel] =
      Calibration(minPulseUs, maxPulseUs, centerPulseUs, reversed);
  return true;
}

bool PCA9685Servo::getCalibration(uint8_t channel,
                                   Calibration& calibration) const {
  if (!isValidChannel(channel)) {
    return false;
  }

  // 使用输出参数返回副本，调用方无法意外修改内部状态。
  calibration = calibrations_[channel];
  return true;
}

bool PCA9685Servo::writeMicroseconds(uint8_t channel, uint16_t pulseUs) {
  if (!ready_ || !isValidChannel(channel)) {
    return false;
  }

  // 将输入限制到该通道的校准范围，减少舵机撞机械限位的风险。
  const Calibration& calibration = calibrations_[channel];
  if (pulseUs < calibration.minPulseUs) {
    pulseUs = calibration.minPulseUs;
  } else if (pulseUs > calibration.maxPulseUs) {
    pulseUs = calibration.maxPulseUs;
  }

  // Adafruit 驱动负责把微秒换算为 PCA9685 的 12 位计数值。
  pwm_.writeMicroseconds(channel, pulseUs);
  return true;
}

bool PCA9685Servo::writeAngle(uint8_t channel, float angleDegrees) {
  // NaN/Inf 无法安全换算，因此与非法通道一样直接拒绝。
  if (!ready_ || !isValidChannel(channel) || !isfinite(angleDegrees)) {
    return false;
  }

  // 对角度做饱和限制，让调用方无需自行 constrain()。
  if (angleDegrees < 0.0F) {
    angleDegrees = 0.0F;
  } else if (angleDegrees > 180.0F) {
    angleDegrees = 180.0F;
  }

  // 将角度归一化到 0.0～1.0，再按需反转方向。
  const Calibration& calibration = calibrations_[channel];
  float position = angleDegrees / 180.0F;
  if (calibration.reversed) {
    position = 1.0F - position;
  }

  // 在线性区间内把角度映射为微秒，并四舍五入为整数。
  const float pulseUs =
      calibration.minPulseUs +
      (calibration.maxPulseUs - calibration.minPulseUs) * position;
  return writeMicroseconds(channel, static_cast<uint16_t>(pulseUs + 0.5F));
}

bool PCA9685Servo::center(uint8_t channel) {
  if (!isValidChannel(channel)) {
    return false;
  }
  // 复用微秒接口，以获得相同的初始化检查和安全限幅。
  return writeMicroseconds(channel, calibrations_[channel].centerPulseUs);
}

bool PCA9685Servo::disable(uint8_t channel) {
  if (!ready_ || !isValidChannel(channel)) {
    return false;
  }

  // PCA9685 的 OFF=4096 表示设置 full-off 位，完全停止该路 PWM。
  pwm_.setPWM(channel, 0, 4096);
  return true;
}

void PCA9685Servo::disableAll() {
  if (!ready_) {
    return;
  }

  // 逐路关闭，避免直接暴露底层寄存器操作。
  for (uint8_t channel = 0; channel < kChannelCount; ++channel) {
    disable(channel);
  }
}

bool PCA9685Servo::isValidChannel(uint8_t channel) {
  return channel < kChannelCount;
}

bool PCA9685Servo::isValidFrequency(float pwmFrequencyHz) {
  // 40～400 Hz 覆盖常见模拟和数字舵机，同时排除明显错误参数。
  return isfinite(pwmFrequencyHz) && pwmFrequencyHz >= 40.0F &&
         pwmFrequencyHz <= 400.0F;
}

bool PCA9685Servo::isValidCalibration(uint16_t minPulseUs,
                                       uint16_t maxPulseUs,
                                       uint16_t centerPulseUs) {
  // 500～2500 μs 是硬保护边界；默认仍采用更保守的 1000～2000 μs。
  return minPulseUs >= kAbsoluteMinPulseUs &&
         maxPulseUs <= kAbsoluteMaxPulseUs && minPulseUs < centerPulseUs &&
         centerPulseUs < maxPulseUs;
}

}  // namespace cyberarm
