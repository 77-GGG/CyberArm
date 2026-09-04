#include <Arduino.h>
#include <PCA9685Servo.h>

cyberarm::PCA9685Servo servoBoard;

constexpr uint8_t kServoChannel = 0;

void setup() {
  Serial.begin(115200);

  if (!servoBoard.begin()) {
    Serial.println("PCA9685 not found. Check wiring and I2C address.");
    while (true) {
      delay(1000);
    }
  }

  servoBoard.center(kServoChannel);
  delay(1000);
}

void loop() {
  for (int angle = 30; angle <= 150; ++angle) {
    servoBoard.writeAngle(kServoChannel, angle);
    delay(15);
  }

  for (int angle = 150; angle >= 30; --angle) {
    servoBoard.writeAngle(kServoChannel, angle);
    delay(15);
  }
}
