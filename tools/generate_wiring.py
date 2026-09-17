"""PlatformIO pre-build: validate JSON and generate wiring constants.

Importable without PlatformIO for configuration tests. Never uses a stale
generated header after invalid/missing JSON: validation fails the build.
"""
import hashlib
import json
from pathlib import Path


def validate(data):
    if set(data) != {'schema_version', 'board', 'i2c', 'pca9685', 'axes'}:
        raise ValueError('wiring.json: unexpected or missing top-level fields')
    if data['schema_version'] != 1 or data['board'] != 'esp32-s3-devkitc-1':
        raise ValueError('wiring.json: unsupported schema/board')
    def integer(value, low, high):
        return type(value) is int and low <= value <= high
    bus = data['i2c']; pwm = data['pca9685']
    if set(bus) != {'sda_gpio', 'scl_gpio', 'clock_hz'} or set(pwm) != {'address', 'pwm_hz', 'oscillator_hz'}:
        raise ValueError('wiring.json: invalid I2C/PCA9685 fields')
    # Native USB uses 19/20; reserve flash/PSRAM pins on supported S3 boards.
    pins = set(range(19)) | {21} | set(range(38, 49))
    if any(type(bus[k]) is not int or bus[k] not in pins for k in ('sda_gpio', 'scl_gpio')) or bus['sda_gpio'] == bus['scl_gpio']:
        raise ValueError('wiring.json: invalid, reserved or duplicate GPIO')
    if bus['clock_hz'] not in (100000, 400000) or type(bus['clock_hz']) is not int:
        raise ValueError('wiring.json: I2C clock must be 100000 or 400000')
    if not integer(pwm['address'], 0x40, 0x77) or not integer(pwm['pwm_hz'], 40, 60) or not integer(pwm['oscillator_hz'], 20000000, 30000000):
        raise ValueError('wiring.json: invalid PCA9685 address/frequency/oscillator')
    axes = data['axes']
    if not isinstance(axes, list) or len(axes) != 6:
        raise ValueError('wiring.json: six axes required')
    for axis, name in zip(axes, ['J1','J2','J3','J4','J5','G']):
        if set(axis) != {'name','channel'} or axis['name'] != name or not integer(axis['channel'], 0, 15):
            raise ValueError('wiring.json: axes must be ordered J1..J5,G with channels 0..15')
    if len({a['channel'] for a in axes}) != 6:
        raise ValueError('wiring.json: duplicate PWM channel')
    return data


def generate(source, destination):
    data = validate(json.loads(Path(source).read_text(encoding='utf-8')))
    encoded = json.dumps(data, sort_keys=True, separators=(',', ':'))
    digest = hashlib.sha256(encoded.encode()).hexdigest()[:16]
    b, p = data['i2c'], data['pca9685']
    content = f'''// Generated from config/wiring.json. Do not edit.
#pragma once
#include <stdint.h>
namespace cyberarm {{ namespace wiring {{
constexpr int kSda = {b['sda_gpio']}, kScl = {b['scl_gpio']};
constexpr uint32_t kI2cClock = {b['clock_hz']}, kOscillator = {p['oscillator_hz']};
constexpr uint8_t kAddress = {p['address']};
constexpr float kPwmHz = {p['pwm_hz']}.0f;
constexpr uint8_t kChannels[6] = {{{','.join(str(a['channel']) for a in data['axes'])}}};
constexpr char kHash[] = "{digest}";
constexpr char kJson[] = R"wiring({encoded})wiring";
}} }}
'''
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists() or destination.read_text(encoding='utf-8') != content:
        destination.write_text(content, encoding='utf-8')
    return digest


if 'Import' in globals():
    Import('env')
    root = Path(env.subst('$PROJECT_DIR'))
    output = Path(env.subst('$BUILD_DIR')).parent / ('generated-' + env.subst('$PIOENV'))
    generate(root/'config/wiring.json', output/'WiringConfig.h')
    env.Append(CPPPATH=[str(output)])
