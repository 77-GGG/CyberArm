#include <Arduino.h>
#include <CyberArmFirmware.h>

cyberarm::firmware::CyberArmFirmware firmware;

void setup() { firmware.begin(); }

void loop() { firmware.update(); }
