# -*- coding: utf-8 -*-
"""
face_recognition_lite_uart.py
=============================
CanMV K230D —— 轻量人脸识别 + 串口上报（供 ESP32-S3 自平衡机器人使用）

基于官方 examples/05-AI-Demo/face_recognition_lite.py 修改：
  1) K230D 适配：rgb888p_size=[640,360]，display_mode 可选 "virt"(无屏) / "lcd"(带屏)
  2) UART1 上报：识别结果帧 + 心跳帧（协议见 protocol.md，115200-8-N-1）
  3) 去抖：连续 3 帧身份一致才发送结果，避免闪烁
  4) 限流：结果帧最快 150ms 一帧；心跳 1s 一帧

用法：
  1) 先跑 face_register_avg.py 或官方 face_registration_lite.py 注册人脸库
  2) 把本文件放到 /sdcard/examples/ (或任意目录)，CanMV IDE 运行
  3) K230D 排针 8(GPIO3/UART1_TXD)、10(GPIO4/UART1_RXD) 与 ESP32 交叉接线，共地

依赖文件（固件 /sdcard/examples 自带）：
  /sdcard/examples/kmodel/face_detection_320.kmodel
  /sdcard/examples/kmodel/face_recognition_mobile.kmodel
  /sdcard/examples/utils/prior_data_320.bin
  /sdcard/examples/utils/db/*.bin   (人脸库)
"""

from libs.PipeLine import PipeLine
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *
import os, sys, gc, math, time
from media.media import *
import nncase_runtime as nn
import ulab.numpy as np
import image
import aidemo
from machine import UART, FPIOA

# ---------------------- 用户配置 ----------------------
DISPLAY_MODE = "virt"          # virt=无屏(装车推荐) / lcd=带MIPI屏 / hdmi
DISPLAY_SIZE = [640, 360]      # virt 模式手动指定；lcd/hdmi 可设 None 用默认
RGB888P_SIZE = [640, 360]      # K230D 建议 [640,360]，官方注释：k230d 可调整为 640x360

FACE_DET_KMODEL  = "/sdcard/examples/kmodel/face_detection_320.kmodel"
FACE_REG_KMODEL  = "/sdcard/examples/kmodel/face_recognition_mobile.kmodel"
ANCHORS_PATH     = "/sdcard/examples/utils/prior_data_320.bin"
DATABASE_DIR     = "/sdcard/examples/utils/db/"

FACE_DET_INPUT   = [320, 320]
FACE_REG_INPUT   = [112, 112]
CONF_THRESH      = 0.5         # 检测置信度
NMS_THRESH       = 0.2
RECOG_THRESH     = 0.75        # 识别相似度阈值（0.75 = 官方默认，可 0.70~0.80 调）

BAUDRATE         = 115200
UART_PIN_TX      = 3           # 排针 8  = 芯片 GPIO3
UART_PIN_RX      = 4           # 排针 10 = 芯片 GPIO4

DEBOUNCE_FRAMES  = 3           # 连续几帧同身份才上报
RESULT_MIN_PERIOD = 0.150      # 结果帧最小间隔（秒）
HEARTBEAT_PERIOD = 1.0         # 心跳间隔（秒）
# ------------------------------------------------------

# 协议常量
PROTO_SYNC0, PROTO_SYNC1 = 0xAA, 0x55
PROTO_RESULT, PROTO_HEARTBEAT, PROTO_STATUS, PROTO_QUERY = 0x01, 0x02, 0x03, 0x04
PERSON_UNKNOWN = 0xFF


def proto_frame(ftype, payload=b''):
    """组帧：AA 55 | TYPE | LEN | PAYLOAD | SUM(所有字节和低8位)"""
    body = bytes([PROTO_SYNC0, PROTO_SYNC1, ftype, len(payload)]) + bytes(payload)
    s = 0
    for b in body:
        s = (s + b) & 0xFF
    return body + bytes([s])


class FaceDetApp(AIBase):
    """人脸检测：face_detection_320.kmodel（与官方一致）"""
    def __init__(self, kmodel_path, model_input_size, anchors,
                 confidence_threshold=0.5, nms_threshold=0.2,
                 rgb888p_size=[640, 360], display_size=[640, 360], debug_mode=0):
        super().__init__(kmodel_path, model_input_size, rgb888p_size, debug_mode)
        self.kmodel_path = kmodel_path
        self.model_input_size = model_input_size
        self.confidence_threshold = confidence_threshold
        self.nms_threshold = nms_threshold
        self.anchors = anchors
        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0], 16), rgb888p_size[1]]
        self.display_size = [ALIGN_UP(display_size[0], 16), display_size[1]]
        self.debug_mode = debug_mode
        self.ai2d = Ai2d(debug_mode)
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)

    def config_preprocess(self, input_image_size=None):
        with ScopedTiming("set preprocess config", self.debug_mode > 0):
            ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size
            top, bottom, left, right, _ = letterbox_pad_param(self.rgb888p_size, self.model_input_size)
            self.ai2d.pad([0, 0, 0, 0, top, bottom, left, right], 0, [104, 117, 123])
            self.ai2d.resize(nn.interp_method.tf_bilinear, nn.interp_mode.half_pixel)
            self.ai2d.build([1, 3, ai2d_input_size[1], ai2d_input_size[0]],
                            [1, 3, self.model_input_size[1], self.model_input_size[0]])

    def postprocess(self, results):
        with ScopedTiming("postprocess", self.debug_mode > 0):
            res = aidemo.face_det_post_process(self.confidence_threshold, self.nms_threshold,
                                               self.model_input_size[0], self.anchors,
                                               self.rgb888p_size, results)
            if len(res) == 0:
                return res, res
            return res[0], res[1]


class FaceRegApp(AIBase):
    """人脸特征提取：face_recognition_mobile.kmodel（Umeyama 5官点对齐，与官方一致）"""
    def __init__(self, kmodel_path, model_input_size,
                 rgb888p_size=[640, 360], display_size=[640, 360], debug_mode=0):
        super().__init__(kmodel_path, model_input_size, rgb888p_size, debug_mode)
        self.kmodel_path = kmodel_path
        self.model_input_size = model_input_size
        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0], 16), rgb888p_size[1]]
        self.display_size = [ALIGN_UP(display_size[0], 16), display_size[1]]
        self.debug_mode = debug_mode
        self.umeyama_args_112 = [
            38.2946, 51.6963,
            73.5318, 51.5014,
            56.0252, 71.7366,
            41.5493, 92.3655,
            70.7299, 92.2041]
        self.ai2d = Ai2d(debug_mode)
        self.ai2d.set_ai2d_dtype(nn.ai2d_format.NCHW_FMT, nn.ai2d_format.NCHW_FMT, np.uint8, np.uint8)

    def config_preprocess(self, landm, input_image_size=None):
        with ScopedTiming("set preprocess config", self.debug_mode > 0):
            ai2d_input_size = input_image_size if input_image_size else self.rgb888p_size
            affine_matrix = self.get_affine_matrix(landm)
            self.ai2d.affine(nn.interp_method.cv2_bilinear, 0, 0, 127, 1, affine_matrix)
            self.ai2d.build([1, 3, ai2d_input_size[1], ai2d_input_size[0]],
                            [1, 3, self.model_input_size[1], self.model_input_size[0]])

    def postprocess(self, results):
        with ScopedTiming("postprocess", self.debug_mode > 0):
            return results[0][0]

    def svd22(self, a):
        s = [0.0, 0.0]; u = [0.0, 0.0, 0.0, 0.0]; v = [0.0, 0.0, 0.0, 0.0]
        s[0] = (math.sqrt((a[0] - a[3]) ** 2 + (a[1] + a[2]) ** 2) +
                math.sqrt((a[0] + a[3]) ** 2 + (a[1] - a[2]) ** 2)) / 2
        s[1] = abs(s[0] - math.sqrt((a[0] - a[3]) ** 2 + (a[1] + a[2]) ** 2))
        v[2] = math.sin((math.atan2(2 * (a[0] * a[1] + a[2] * a[3]),
                                    a[0] ** 2 - a[1] ** 2 + a[2] ** 2 - a[3] ** 2)) / 2) if s[0] > s[1] else 0
        v[0] = math.sqrt(1 - v[2] ** 2); v[1] = -v[2]; v[3] = v[0]
        u[0] = -(a[0] * v[0] + a[1] * v[2]) / s[0] if s[0] != 0 else 1
        u[2] = -(a[2] * v[0] + a[3] * v[2]) / s[0] if s[0] != 0 else 0
        u[1] = (a[0] * v[1] + a[1] * v[3]) / s[1] if s[1] != 0 else -u[2]
        u[3] = (a[2] * v[1] + a[3] * v[3]) / s[1] if s[1] != 0 else u[0]
        v[0] = -v[0]; v[2] = -v[2]
        return u, s, v

    def image_umeyama_112(self, src):
        SRC_NUM, SRC_DIM = 5, 2
        src_mean = [0.0, 0.0]; dst_mean = [0.0, 0.0]
        for i in range(0, SRC_NUM * 2, 2):
            src_mean[0] += src[i]; src_mean[1] += src[i + 1]
            dst_mean[0] += self.umeyama_args_112[i]; dst_mean[1] += self.umeyama_args_112[i + 1]
        src_mean[0] /= SRC_NUM; src_mean[1] /= SRC_NUM
        dst_mean[0] /= SRC_NUM; dst_mean[1] /= SRC_NUM
        src_demean = [[0.0, 0.0] for _ in range(SRC_NUM)]
        dst_demean = [[0.0, 0.0] for _ in range(SRC_NUM)]
        for i in range(SRC_NUM):
            src_demean[i][0] = src[2 * i] - src_mean[0]
            src_demean[i][1] = src[2 * i + 1] - src_mean[1]
            dst_demean[i][0] = self.umeyama_args_112[2 * i] - dst_mean[0]
            dst_demean[i][1] = self.umeyama_args_112[2 * i + 1] - dst_mean[1]
        A = [[0.0, 0.0], [0.0, 0.0]]
        for i in range(SRC_DIM):
            for k in range(SRC_DIM):
                for j in range(SRC_NUM):
                    A[i][k] += dst_demean[j][i] * src_demean[j][k]
                A[i][k] /= SRC_NUM
        T = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        U, S, V = self.svd22([A[0][0], A[0][1], A[1][0], A[1][1]])
        T[0][0] = U[0] * V[0] + U[1] * V[2]
        T[0][1] = U[0] * V[1] + U[1] * V[3]
        T[1][0] = U[2] * V[0] + U[3] * V[2]
        T[1][1] = U[2] * V[1] + U[3] * V[3]
        scale = 1.0
        src_demean_mean = [0.0, 0.0]; src_demean_var = [0.0, 0.0]
        for i in range(SRC_NUM):
            src_demean_mean[0] += src_demean[i][0]
            src_demean_mean[1] += src_demean[i][1]
        src_demean_mean[0] /= SRC_NUM; src_demean_mean[1] /= SRC_NUM
        for i in range(SRC_NUM):
            src_demean_var[0] += (src_demean_mean[0] - src_demean[i][0]) ** 2
            src_demean_var[1] += (src_demean_mean[1] - src_demean[i][1]) ** 2
        src_demean_var[0] /= SRC_NUM; src_demean_var[1] /= SRC_NUM
        scale = 1.0 / (src_demean_var[0] + src_demean_var[1]) * (S[0] + S[1])
        T[0][2] = dst_mean[0] - scale * (T[0][0] * src_mean[0] + T[0][1] * src_mean[1])
        T[1][2] = dst_mean[1] - scale * (T[1][0] * src_mean[0] + T[1][1] * src_mean[1])
        T[0][0] *= scale; T[0][1] *= scale
        T[1][0] *= scale; T[1][1] *= scale
        return T

    def get_affine_matrix(self, sparse_points):
        with ScopedTiming("get_affine_matrix", self.debug_mode > 1):
            matrix_dst = self.image_umeyama_112(sparse_points)
            return [matrix_dst[0][0], matrix_dst[0][1], matrix_dst[0][2],
                    matrix_dst[1][0], matrix_dst[1][1], matrix_dst[1][2]]


class FaceRecognizer:
    """人脸识别器：检测 + 对齐 + 提特征 + 查库（改动：database_search 返回 (name,score)）"""

    def __init__(self, face_det_kmodel, face_reg_kmodel, det_input_size, reg_input_size,
                 database_dir, anchors, confidence_threshold=0.5, nms_threshold=0.2,
                 face_recognition_threshold=0.75,
                 rgb888p_size=[640, 360], display_size=[640, 360], debug_mode=0):
        self.face_det_kmodel = face_det_kmodel
        self.face_reg_kmodel = face_reg_kmodel
        self.det_input_size = det_input_size
        self.reg_input_size = reg_input_size
        self.database_dir = database_dir
        self.anchors = anchors
        self.confidence_threshold = confidence_threshold
        self.nms_threshold = nms_threshold
        self.face_recognition_threshold = face_recognition_threshold
        self.rgb888p_size = [ALIGN_UP(rgb888p_size[0], 16), rgb888p_size[1]]
        self.display_size = [ALIGN_UP(display_size[0], 16), display_size[1]]
        self.debug_mode = debug_mode
        self.max_register_face = 100
        self.feature_num = 128
        self.valid_register_face = 0
        self.db_name = []
        self.db_data = []
        self.face_det = FaceDetApp(self.face_det_kmodel,
                                   model_input_size=self.det_input_size,
                                   anchors=self.anchors,
                                   confidence_threshold=self.confidence_threshold,
                                   nms_threshold=self.nms_threshold,
                                   rgb888p_size=self.rgb888p_size,
                                   display_size=self.display_size, debug_mode=0)
        self.face_reg = FaceRegApp(self.face_reg_kmodel,
                                   model_input_size=self.reg_input_size,
                                   rgb888p_size=self.rgb888p_size,
                                   display_size=self.display_size)
        self.face_det.config_preprocess()
        self.database_init()

    def run(self, input_np):
        det_boxes, landms = self.face_det.run(input_np)
        recg_res = []
        for landm in landms:
            self.face_reg.config_preprocess(landm)
            feature = self.face_reg.run(input_np)
            recg_res.append(self.database_search(feature))
        return det_boxes, recg_res

    def database_init(self):
        db_file_list = os.listdir(self.database_dir) if os.path.exists(self.database_dir) else []
        for db_file in db_file_list:
            if not db_file.endswith('.bin'):
                continue
            if self.valid_register_face >= self.max_register_face:
                break
            with open(self.database_dir + db_file, 'rb') as f:
                data = f.read()
            feature = np.frombuffer(data, dtype=np.float)
            self.db_data.append(feature)
            self.db_name.append(db_file.split('.')[0])
            self.valid_register_face += 1
        print("[K230D] face db loaded:", self.valid_register_face, "persons:", self.db_name)

    def database_search(self, feature):
        v_id = -1
        v_score_max = 0.0
        feature /= np.linalg.norm(feature)
        for i in range(self.valid_register_face):
            db_feature = self.db_data[i]
            db_feature /= np.linalg.norm(db_feature)
            v_score = np.dot(feature, db_feature) / 2 + 0.5
            if v_score > v_score_max:
                v_score_max = v_score
                v_id = i
        if v_id == -1:
            return None, 0.0
        if v_score_max < self.face_recognition_threshold:
            return None, float(v_score_max)
        return self.db_name[v_id], float(v_score_max)

    def draw_result(self, pl, dets, recg_results):
        pl.osd_img.clear()
        if dets:
            for i, det in enumerate(dets):
                x1, y1, w, h = map(lambda x: int(round(x, 0)), det[:4])
                x1 = x1 * self.display_size[0] // self.rgb888p_size[0]
                y1 = y1 * self.display_size[1] // self.rgb888p_size[1]
                w = w * self.display_size[0] // self.rgb888p_size[0]
                h = h * self.display_size[1] // self.rgb888p_size[1]
                pl.osd_img.draw_rectangle(x1, y1, w, h, color=(255, 0, 0, 255), thickness=4)
                name, score = recg_results[i]
                text = "unknown" if name is None else "{}:{:.2f}".format(name, score)
                pl.osd_img.draw_string_advanced(x1, y1, 32, text, color=(255, 255, 0, 0))


def u16_le(v):
    v = int(v) & 0xFFFF
    return bytes([v & 0xFF, (v >> 8) & 0xFF])


def main():
    # ---- UART 初始化 ----
    fpioa = FPIOA()
    fpioa.set_function(UART_PIN_TX, FPIOA.UART1_TXD)
    fpioa.set_function(UART_PIN_RX, FPIOA.UART1_RXD)
    uart = UART(UART.UART1, baudrate=BAUDRATE, bits=UART.EIGHTBITS,
                parity=UART.PARITY_NONE, stop=UART.STOPBITS_ONE)
    print("[K230D] UART1 ready @{}".format(BAUDRATE))

    # ---- PipeLine ----
    pl = PipeLine(rgb888p_size=RGB888P_SIZE, display_mode=DISPLAY_MODE, display_size=DISPLAY_SIZE)
    pl.create()
    display_size = pl.get_display_size()
    print("[K230D] display:", display_size, "mode:", DISPLAY_MODE)

    # ---- 识别器 ----
    anchors_len, det_dim = 4200, 4
    anchors = np.fromfile(ANCHORS_PATH, dtype=np.float)
    anchors = anchors.reshape((anchors_len, det_dim))
    fr = FaceRecognizer(FACE_DET_KMODEL, FACE_REG_KMODEL,
                        det_input_size=FACE_DET_INPUT, reg_input_size=FACE_REG_INPUT,
                        database_dir=DATABASE_DIR, anchors=anchors,
                        confidence_threshold=CONF_THRESH, nms_threshold=NMS_THRESH,
                        face_recognition_threshold=RECOG_THRESH,
                        rgb888p_size=RGB888P_SIZE, display_size=display_size)

    # ---- 状态帧：带人脸库人数 ----
    uart.write(proto_frame(PROTO_STATUS, bytes([0x00, fr.valid_register_face])))

    # ---- 去抖/限流状态 ----
    last_id = PERSON_UNKNOWN
    last_sent_id = PERSON_UNKNOWN
    streak = 0
    last_result_t = 0.0
    last_heartbeat_t = 0.0

    while True:
        t = time.ticks_ms() * 0.001  # 单调时钟（秒），避免依赖 RTC 是否已校准
        img = pl.get_frame()
        det_boxes, recg_res = fr.run(img)
        fr.draw_result(pl, det_boxes, recg_res)
        pl.show_image()
        gc.collect()

        # ---- 选最大人脸作为上报目标 ----
        cur_id = PERSON_UNKNOWN
        cur_score = 0.0
        cur_box = (0, 0, 0, 0)  # cx, cy, w, h（rgb888p 坐标系）
        if det_boxes is not None and len(det_boxes) > 0:
            best_i = 0
            best_area = -1
            for i, det in enumerate(det_boxes):
                area = float(det[2]) * float(det[3])
                if area > best_area:
                    best_area = area
                    best_i = i
            name, score = recg_res[best_i] if best_i < len(recg_res) else (None, 0.0)
            det = det_boxes[best_i]
            cx = float(det[0]) + float(det[2]) / 2
            cy = float(det[1]) + float(det[3]) / 2
            cur_box = (cx, cy, float(det[2]), float(det[3]))
            if name is not None and score >= RECOG_THRESH:
                cur_id = fr.db_name.index(name)
                cur_score = score

        # ---- 去抖：连续 DEBOUNCE_FRAMES 帧身份一致才发送 ----
        if cur_id == last_id and cur_id != PERSON_UNKNOWN:
            streak += 1
        else:
            last_id = cur_id
            streak = 1 if cur_id != PERSON_UNKNOWN else 0

        if streak >= DEBOUNCE_FRAMES and (t - last_result_t) >= RESULT_MIN_PERIOD:
            score_u8 = int(min(max(0.0, cur_score) * 100, 255))
            cx, cy, w, h = cur_box
            payload = bytes([cur_id & 0xFF, score_u8]) + u16_le(cx) + u16_le(cy) + u16_le(w) + u16_le(h)
            uart.write(proto_frame(PROTO_RESULT, payload))
            last_result_t = t
            last_sent_id = cur_id
            streak = 0  # 同一身份要重新数帧（限流已兜底）

        # ---- 目标丢失：立即上报一次"无人"，避免 ESP32 用过期数据继续跟随 ----
        if cur_id == PERSON_UNKNOWN and last_sent_id != PERSON_UNKNOWN:
            payload = bytes([PERSON_UNKNOWN, 0]) + u16_le(0) + u16_le(0) + u16_le(0) + u16_le(0)
            uart.write(proto_frame(PROTO_RESULT, payload))
            last_sent_id = PERSON_UNKNOWN
            last_result_t = t

        # ---- 心跳（ESP32 判断模块是否掉线）----
        if (t - last_heartbeat_t) >= HEARTBEAT_PERIOD:
            uart.write(proto_frame(PROTO_HEARTBEAT, bytes([0x01, 0x00])))
            last_heartbeat_t = t

        # ---- 响应 ESP32 查询（0x04 → 回 0x03 状态帧）----
        q = uart.read() or b''   # CanMV 的 UART.read() 无数据时可能返回 None
        if PROTO_QUERY in q:
            uart.write(proto_frame(PROTO_STATUS, bytes([0x00, fr.valid_register_face])))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import sys
        print("[K230D] fatal:", e)
        sys.print_exception(e)
