# PCA9685Servo

面向 ESP32-S3 + PCA9685 + 舵机的轻量封装。底层使用 Adafruit 官方
`Adafruit PWM Servo Driver Library`。

## 默认参数

- SDA：GPIO8
- SCL：GPIO9
- I2C 地址：`0x40`
- I2C 时钟：100 kHz
- PWM 频率：50 Hz
- 舵机安全脉宽：1000–2000 μs
- 中位脉宽：1500 μs

## 基本用法

```cpp
#include <PCA9685Servo.h>

cyberarm::PCA9685Servo servos;

void setup() {
  if (!servos.begin()) {
    while (true) {
      delay(1000);
    }
  }

  servos.center(0);          // PWM0 回中位
  servos.writeAngle(0, 90);  // 角度接口，范围自动限制到 0–180°
  servos.writeMicroseconds(0, 1500);  // 也可直接使用微秒
}

void loop() {}
```

自定义接线、地址和校准：

```cpp
cyberarm::PCA9685Servo servos(0x41);

void setup() {
  servos.begin(5, 6);                    // SDA=5, SCL=6
  servos.setCalibration(7, 900, 2100, 1500, true);
  servos.writeAngle(7, 45);
}
```

多块 PCA9685 可以共用同一个 `Wire`，但必须设置不同地址，例如 `0x40`、
`0x41`。如果应用已经初始化了 I2C，可改用 `beginWithConfiguredWire()`。

## 常用接口

| 接口 | 用途 |
|---|---|
| `begin(sda, scl, clock, frequency)` | 初始化 I2C 和 PCA9685 |
| `setCalibration(channel, min, max, center, reversed)` | 设置某一路的安全脉宽、中心和方向 |
| `writeAngle(channel, angle)` | 按 0–180° 控制，自动限制范围 |
| `writeMicroseconds(channel, pulse)` | 使用微秒控制，自动限制到校准范围 |
| `center(channel)` | 回到该路校准的中位 |
| `disable(channel)` | 停止一路 PWM，舵机不再主动保持位置 |
| `disableAll()` | 停止全部 16 路 PWM |
| `rawDriver()` | 获取底层 Adafruit 驱动，供高级功能使用 |

通道编号范围是 `0–15`，对应 PCA9685 板上的 `PWM0–PWM15`。所有写入接口
都会先检查通道号；角度和脉宽超出范围时会被限制到该通道的校准边界。

## 接线与供电

| PCA9685 | ESP32-S3 / 电源 |
|---|---|
| VCC | ESP32-S3 3.3V |
| SDA | 默认 GPIO8 |
| SCL | 默认 GPIO9 |
| GND | ESP32-S3 GND 与外部电源负极共地 |
| V+ | 外部约 5V 舵机电源 |

不要用 ESP32-S3 的 3.3V 给舵机供电。首次运行建议保持默认 1000–2000 μs
范围；如果舵机嗡鸣、发热、堵转或引起 ESP32 重启，应立即断电检查。
