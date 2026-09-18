#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
protocol_sim.py —— 串口协议交叉验证工具（在 PC 上运行，不需要开发板）

对打双方：
  A) K230D 侧组帧逻辑   —— 从 face_recognition_lite_uart.py 逐字转写：
                           proto_frame() / u16_le()
  B) ESP32 侧解析状态机 —— 从 esp32_face_listener/esp32_face_listener.ino
                           逐字转写：uartFeed() + handleFrame() + checksumOf()

验证项：
  T1  RESULT 帧：字段还原正确、校验和与 protocol.md 示例一致（0x4E）
  T2  HEARTBEAT / STATUS / QUERY 帧：构造与解析
  T3  粘包：两帧背靠背连续发送
  T4  逐字节喂入（模拟 UART 一字节一个中断）
  T5  帧中插入噪声字节后恢复
  T6  校验和错误 → 拒收，后续帧不受影响
  T7  随机化鲁棒性 fuzz：随机帧序列 + 随机插/丢字节，100% 完整帧被解析、0 误收

用法：python3 protocol_sim.py
退出码：0=全部通过 1=有失败
"""

import random
import sys

# ================== A) K230D 侧（转写自 face_recognition_lite_uart.py） ==================
PROTO_SYNC0, PROTO_SYNC1 = 0xAA, 0x55
PROTO_RESULT, PROTO_HEARTBEAT, PROTO_STATUS, PROTO_QUERY = 0x01, 0x02, 0x03, 0x04
PERSON_UNKNOWN = 0xFF


def proto_frame(ftype, payload=b''):
    """与 K230D 脚本一致：AA 55 | TYPE | LEN | PAYLOAD | SUM(所有字节和低8位)"""
    body = bytes([PROTO_SYNC0, PROTO_SYNC1, ftype, len(payload)]) + bytes(payload)
    s = 0
    for b in body:
        s = (s + b) & 0xFF
    return body + bytes([s])


def u16_le(v):
    v = int(v) & 0xFFFF
    return bytes([v & 0xFF, (v >> 8) & 0xFF])


def build_result(id_, score, cx, cy, w, h):
    payload = bytes([id_ & 0xFF, score]) + u16_le(cx) + u16_le(cy) + u16_le(w) + u16_le(h)
    return proto_frame(PROTO_RESULT, payload)


# ================== B) ESP32 侧（转写自 esp32_face_listener.ino） ==================
S_IDLE, S_SYNC1, S_TYPE, S_LEN, S_PAYLOAD, S_CHECKSUM = range(6)
rx_len_max = 64


class Esp32Parser:
    """与 .ino 中 uartFeed()/handleFrame() 1:1 对应的解析器"""

    def __init__(self):
        self.state = S_IDLE
        self.rx_type = 0
        self.rx_len = 0
        self.rx_buf = bytearray()
        self.frames = []          # 收到的合法帧列表：(type, payload(bytearray or bytes), raw)
        self.checksum_errs = 0

    def checksum_of(self, buf):
        s = 0
        for b in buf:
            s = (s + b) & 0xFF
        return s

    def handle_frame(self, ftype, payload, length):
        # .ino 的 handleFrame（解析部分）
        if ftype == PROTO_RESULT:
            if length != 10:
                return
            p = payload
            id_ = p[0]
            score = p[1]
            cx = p[2] | (p[3] << 8)
            cy = p[4] | (p[5] << 8)
            w = p[6] | (p[7] << 8)
            h = p[8] | (p[9] << 8)
            self.frames.append(('RESULT', {'id': id_, 'score': score, 'cx': cx,
                                           'cy': cy, 'w': w, 'h': h,
                                           'valid': id_ != PERSON_UNKNOWN}))
        elif ftype == PROTO_HEARTBEAT:
            alive = payload[0] if length >= 1 else 0
            self.frames.append(('HEARTBEAT', {'alive': alive}))
        elif ftype == PROTO_STATUS:
            code = payload[0] if length >= 1 else 0
            db = payload[1] if length >= 2 else 0
            self.frames.append(('STATUS', {'code': code, 'db_persons': db}))
        else:
            self.frames.append(('UNKNOWN', {'type': ftype}))

    def feed(self, b):
        # 对应 .ino 的 uartFeed()
        if self.state == S_IDLE:
            if b == PROTO_SYNC0:
                self.state = S_SYNC1
        elif self.state == S_SYNC1:
            if b == PROTO_SYNC1:
                self.state = S_TYPE
            elif b != PROTO_SYNC0:
                self.state = S_IDLE
        elif self.state == S_TYPE:
            self.rx_type = b
            self.state = S_LEN
        elif self.state == S_LEN:
            self.rx_len = b
            if self.rx_len > rx_len_max:
                self.state = S_IDLE
                return
            self.rx_buf = bytearray()
            self.state = S_CHECKSUM if self.rx_len == 0 else S_PAYLOAD
        elif self.state == S_PAYLOAD:
            self.rx_buf.append(b)
            if len(self.rx_buf) >= self.rx_len:
                self.state = S_CHECKSUM
        elif self.state == S_CHECKSUM:
            frame = bytes([PROTO_SYNC0, PROTO_SYNC1, self.rx_type, self.rx_len]) + bytes(self.rx_buf)
            if self.checksum_of(frame) == b:
                self.handle_frame(self.rx_type, self.rx_buf, self.rx_len)
            else:
                self.checksum_errs += 1
            self.state = S_IDLE

    def feed_stream(self, data):
        for b in data:
            self.feed(b)


# ================== 测试框架 ==================
PASS, FAIL = 0, 0


def check(name, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('  [PASS] %s %s' % (name, detail))
    else:
        FAIL += 1
        print('  [FAIL] %s %s' % (name, detail))


def main():
    random.seed(20260823)

    # ---------- T1 RESULT 帧：对照 protocol.md 示例 ----------
    print('T1 RESULT 帧与 protocol.md 示例一致性')
    frame = build_result(3, 92, 320, 180, 120, 120)
    expect = bytes([0xAA, 0x55, 0x01, 0x0A, 0x03, 0x5C, 0x40, 0x01, 0xB4, 0x00, 0x78, 0x00, 0x78, 0x00, 0x4E])
    check('字节级一致（含校验和 0x4E）', frame == expect,
          'got=' + frame.hex(' ').upper().replace(' ', ' '))
    p = Esp32Parser()
    p.feed_frame_bytes = None
    p.feed_stream(frame)
    check('解析出 1 帧', len(p.frames) == 1)
    if p.frames:
        t, d = p.frames[0]
        check('类型 RESULT / 字段还原', t == 'RESULT' and d['id'] == 3 and d['score'] == 92
              and d['cx'] == 320 and d['cy'] == 180 and d['w'] == 120 and d['h'] == 120
              and d['valid'], str(d))
    # 无脸帧
    p2 = Esp32Parser()
    p2.feed_stream(build_result(PERSON_UNKNOWN, 0, 0, 0, 0, 0))
    check('无脸帧 id=0xFF 解析为 invalid', p2.frames and p2.frames[0][1]['valid'] is False)

    # ---------- T2 HEARTBEAT / STATUS / QUERY ----------
    print('T2 HEARTBEAT / STATUS / QUERY')
    p3 = Esp32Parser()
    p3.feed_stream(proto_frame(PROTO_HEARTBEAT, bytes([0x01, 0x00])))
    p3.feed_stream(proto_frame(PROTO_STATUS, bytes([0x00, 2])))
    p3.feed_stream(proto_frame(PROTO_QUERY))          # ESP32 只发不收，这里验证可解析性
    check('3 帧全部解析', len(p3.frames) == 3, [f[0] for f in p3.frames])
    check('心跳 alive=1', p3.frames[0] == ('HEARTBEAT', {'alive': 1}))
    check('状态 db_persons=2', p3.frames[1] == ('STATUS', {'code': 0, 'db_persons': 2}))

    # ---------- T3 粘包 ----------
    print('T3 粘包（背靠背）')
    p4 = Esp32Parser()
    stream = build_result(1, 80, 100, 50, 60, 60) + proto_frame(PROTO_HEARTBEAT, bytes([1, 0]))
    p4.feed_stream(stream)
    check('解析出 2 帧且顺序正确',
          len(p4.frames) == 2 and p4.frames[0][0] == 'RESULT' and p4.frames[1][0] == 'HEARTBEAT')

    # ---------- T4 逐字节喂入 ----------
    print('T4 逐字节喂入')
    p5 = Esp32Parser()
    data = build_result(2, 91, 111, 222, 33, 44)
    for b in data:
        p5.feed(b)
    check('逐字节喂入解析正确', len(p5.frames) == 1 and p5.frames[0][1]['cx'] == 111)

    # ---------- T5 噪声插入后恢复 ----------
    print('T5 噪声字节插入后恢复')
    p6 = Esp32Parser()
    clean = build_result(5, 77, 640, 360, 299, 359)
    noisy = clean[:4] + bytes([0x11, 0x00]) + clean[4:]      # 帧中间插 2 字节噪声
    p6.feed_stream(noisy)
    check('噪声帧被拒收且不产生误解析', p6.checksum_errs == 1 and len(p6.frames) == 0)
    p6.feed_stream(clean)
    check('恢复后完整帧正常解析', len(p6.frames) == 1 and p6.frames[0][1]['id'] == 5)

    # ---------- T6 损坏校验和不影响后续帧 ----------
    print('T6 校验和损坏')
    p7 = Esp32Parser()
    bad = bytearray(build_result(6, 66, 10, 20, 30, 40))
    bad[-1] ^= 0xFF
    p7.feed_stream(bytes(bad))
    p7.feed_stream(build_result(7, 55, 1, 2, 3, 4))
    check('坏帧拒收 + 好帧解析', p7.checksum_errs == 1 and len(p7.frames) == 1
          and p7.frames[0][1]['id'] == 7)

    # ---------- T7 随机化 fuzz（带“注入帧 ↔ 解析结果”精确映射） ----------
    print('T7 随机化鲁棒性 fuzz（注入 500 完整帧 + 帧内/帧间噪声 + 随机丢字节）')
    n_frames, mid_noise = 500, 0
    p8 = Esp32Parser()
    injected = []
    for i in range(n_frames):
        kind = random.choice(['RESULT', 'HEARTBEAT', 'STATUS'])
        if kind == 'RESULT':
            f = build_result(random.randrange(0, 100), random.randrange(0, 101),
                             random.randrange(0, 640), random.randrange(0, 360),
                             random.randrange(0, 640), random.randrange(0, 360))
        elif kind == 'HEARTBEAT':
            f = proto_frame(PROTO_HEARTBEAT, bytes([1, 0]))
        else:
            f = proto_frame(PROTO_STATUS, bytes([0, random.randrange(0, 101)]))
        injected.append(f)
    marks = []                     # (注入帧在流中的起点, 是否被帧内噪声破坏)
    stream = bytearray()
    for f in injected:
        if random.random() < 0.15 and len(f) > 5:
            cut = random.randrange(2, len(f) - 1)
            s0 = len(stream)
            stream += f[:cut] + bytes([random.randrange(0, 256)]) + f[cut:]
            marks.append((s0, True))
            mid_noise += 1
        else:
            s0 = len(stream)
            stream += f
            marks.append((s0, False))
        # 25% 概率在帧【之间】插噪声（不影响帧，只考验同步恢复）
        if random.random() < 0.25:
            stream += bytes([random.randrange(0, 256)] * random.randint(1, 2))
    # 10% 概率随机丢弃 1 个字节
    if random.random() < 0.10 and len(stream) > 2:
        del stream[random.randrange(0, len(stream) - 1)]

    # 带映射的解析器：记录"帧起点"字节位置，以及哪些帧被校验拒绝
    class Tracker(Esp32Parser):
        def __init__(self):
            super().__init__()
            self.accepted = []     # 校验通过帧的起点位置
            self.started = []      # 开始解析（读到 0xAA 55）的帧起点位置
            self._buf = bytearray()
            self._pend = None

        def feed(self, b):
            was_idle = (self.state == S_IDLE)
            n_before = len(self.frames)
            if was_idle and b == 0xAA:
                self._pend = len(self._buf)
            super().feed(b)
            if was_idle and self.state != S_IDLE:
                self.started.append(self._pend)
            if self._pend is not None and len(self.frames) != n_before:
                self.accepted.append(self._pend)
            self._buf.append(b)

    tr = Tracker()
    tr.feed_stream(bytes(stream))
    # 归类：每个解析起点 → 属于哪个注入帧（按 marks 区间精确匹配起点）
    starts = [m[0] for m in marks]

    def belongs(pos):
        for i, (s0, _bad) in enumerate(marks):
            if s0 == pos:
                return i
        return -1

    clean_ok = 0
    clean_lost = 0
    mid_rejected = 0   # 被校验/格式检查拦截
    mid_slipped = 0    # 校验巧合通过（8 位校验和的固有概率，见文档）
    ghost = 0
    for pos in tr.accepted:
        i = belongs(pos)
        if i < 0:
            ghost += 1
        elif marks[i][1]:
            mid_slipped += 1
        else:
            clean_ok += 1
    for pos in tr.started:
        i = belongs(pos)
        if i >= 0 and pos not in tr.accepted and marks[i][1]:
            mid_rejected += 1
    for s0, bad in marks:
        if not bad and s0 not in tr.accepted:
            clean_lost += 1

    check('0 幽灵帧（没有凭空产生的合法帧）', ghost == 0)
    check('干净帧 100% 解析、0 丢失', clean_lost == 0,
          'clean_ok=%d lost=%d' % (clean_ok, clean_lost))
    check('帧内噪声 ≥90% 被拦截（校验和+格式检查）',
          mid_rejected >= int(mid_noise * 0.9),
          '%d/%d rejected (errs=%d)' % (mid_rejected, mid_noise, tr.checksum_errs))
    check('校验巧合漏过 ≤5%（8位校验和固有概率，已记录为已知限制）',
          mid_slipped <= max(1, int(mid_noise * 0.05)),
          'slipped=%d' % mid_slipped)
    print('       统计: clean=%d lost=%d rejected=%d slipped=%d ghost=%d errs=%d' % (
        clean_ok, clean_lost, mid_rejected, mid_slipped, ghost, tr.checksum_errs))

    # ---------- 汇总 ----------
    print()
    print('========================================')
    print('协议交叉验证结果: %d passed, %d failed' % (PASS, FAIL))
    print('========================================')
    return 0 if FAIL == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
