#pragma once

#include <Adafruit_PWMServoDriver.h>
#include <Arduino.h>
#include <Wire.h>

namespace cyberarm {

/**
 * @brief ESP32-S3 上的 PCA9685 舵机控制封装。
 *
 * 该类负责初始化 I2C、检测 PCA9685、维护每路舵机的安全脉宽范围，
 * 并提供角度与微秒两种控制方式。通道编号范围为 0～15。
 */
class PCA9685Servo {
 public:
  /** PCA9685 的通道数量和默认 7 位 I2C 地址。 */
  enum : uint8_t {
    kChannelCount = 16,
    kDefaultAddress = 0x40,
  };

  /** 默认 SG90 脉宽参数，以及允许用户配置的绝对保护范围。 */
  enum : uint16_t {
    kDefaultMinPulseUs = 1000,
    kDefaultMaxPulseUs = 2000,
    kDefaultCenterPulseUs = 1500,
    kAbsoluteMinPulseUs = 500,
    kAbsoluteMaxPulseUs = 2500,
  };

  /**
   * @brief 单个舵机通道的校准参数。
   *
   * reversed 为 true 时，角度方向会反转；微秒接口不受方向设置影响。
   */
  struct Calibration {
    Calibration(uint16_t minPulseUs = kDefaultMinPulseUs,
                uint16_t maxPulseUs = kDefaultMaxPulseUs,
                uint16_t centerPulseUs = kDefaultCenterPulseUs,
                bool reversed = false)
        : minPulseUs(minPulseUs),
          maxPulseUs(maxPulseUs),
          centerPulseUs(centerPulseUs),
          reversed(reversed) {}

    uint16_t minPulseUs;     ///< 0° 对应的最小脉宽。
    uint16_t maxPulseUs;     ///< 180° 对应的最大脉宽。
    uint16_t centerPulseUs;  ///< center() 使用的中位脉宽。
    bool reversed;           ///< 是否反转角度方向。
  };

  /**
   * @param address PCA9685 的 7 位 I2C 地址，默认 0x40。
   * @param wire 使用的 I2C 总线，默认使用全局 Wire。
   */
  explicit PCA9685Servo(uint8_t address = kDefaultAddress,
                        TwoWire& wire = Wire);

  /**
   * @brief 初始化 ESP32-S3 I2C，并检测 PCA9685 是否响应。
   * @return 初始化成功返回 true；参数非法或设备无响应返回 false。
   */
  bool begin(int sdaPin = 8, int sclPin = 9, uint32_t i2cClockHz = 100000,
             float pwmFrequencyHz = 50.0F);

  /** 应用程序已经调用 Wire.begin() 时，使用此接口初始化驱动板。 */
  bool beginWithConfiguredWire(float pwmFrequencyHz = 50.0F);

  /** 设置舵机 PWM 频率；允许范围为 40～400 Hz。 */
  bool setFrequency(float pwmFrequencyHz);

  /**
   * @brief 设置指定通道的安全脉宽、中心位置和方向。
   * @return 通道及参数有效时返回 true。
   */
  bool setCalibration(
      uint8_t channel, uint16_t minPulseUs = kDefaultMinPulseUs,
      uint16_t maxPulseUs = kDefaultMaxPulseUs,
      uint16_t centerPulseUs = kDefaultCenterPulseUs,
      bool reversed = false);

  /** 将指定通道的当前校准参数复制到 calibration。 */
  bool getCalibration(uint8_t channel, Calibration& calibration) const;

  /** 按微秒写入舵机脉宽，数值会自动限制在该通道的安全范围内。 */
  bool writeMicroseconds(uint8_t channel, uint16_t pulseUs);

  /** 按 0～180° 控制舵机；越界角度会被自动限制。 */
  bool writeAngle(uint8_t channel, float angleDegrees);

  /** 将舵机移动到该通道校准的中位。 */
  bool center(uint8_t channel);

  /** 停止一路 PWM；舵机将不再主动保持位置。 */
  bool disable(uint8_t channel);

  /** 停止全部 16 路 PWM。 */
  void disableAll();

  /** 驱动板是否已经成功初始化。 */
  bool isReady() const { return ready_; }

  /** 返回当前驱动板的 7 位 I2C 地址。 */
  uint8_t address() const { return address_; }

  /** 返回当前 PWM 频率。 */
  float frequency() const { return frequencyHz_; }

  /** 获取底层 Adafruit 驱动，以便使用本封装未覆盖的高级功能。 */
  Adafruit_PWMServoDriver& rawDriver() { return pwm_; }

 private:
  // 参数检查集中放在私有函数中，确保所有公开写入接口行为一致。
  static bool isValidChannel(uint8_t channel);
  static bool isValidFrequency(float pwmFrequencyHz);
  static bool isValidCalibration(uint16_t minPulseUs, uint16_t maxPulseUs,
                                 uint16_t centerPulseUs);
  bool initializeDriver(float pwmFrequencyHz);

  // wire_ 由调用方拥有；本类只保存引用，不负责其生命周期。
  TwoWire& wire_;
  // Adafruit 官方 PCA9685 底层驱动实例。
  Adafruit_PWMServoDriver pwm_;
  // 每个通道各自保存一份校准参数，默认均为 1000/2000/1500 μs。
  Calibration calibrations_[kChannelCount];
  uint8_t address_;
  float frequencyHz_;
  bool ready_;
};

}  // namespace cyberarm
