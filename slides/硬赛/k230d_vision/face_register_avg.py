# -*- coding: utf-8 -*-
"""
face_register_avg.py
====================
CanMV K230D —— 人脸注册（改进版：一人多张照片，特征取平均）

与官方 face_registration_lite.py 的区别：
  · 按文件名分组：db_img 里放 名字前缀_序号.jpg，例如
        zhangsan_1.jpg  zhangsan_2.jpg  zhangsan_3.jpg  lisi_1.jpg
    同名前缀的人脸特征会归一化求平均，写成一个库文件：
        /sdcard/examples/utils/db/zhangsan.bin  /sdcard/examples/utils/db/lisi.bin
  · 平均后识别更稳（单人单张照片受表情/光照影响大）
  · 照片要求：正脸、光线均匀、单人人脸、分辨率建议 ≥320×320

运行：把照片拷到 /sdcard/examples/utils/db_img/ 后，CanMV IDE 运行本文件。
"""

from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *
import os, sys, gc, math
import nncase_runtime as nn
import ulab.numpy as np
import image
import aidemo

FACE_DET_KMODEL = "/sdcard/examples/kmodel/face_detection_320.kmodel"
FACE_REG_KMODEL = "/sdcard/examples/kmodel/face_recognition_mobile.kmodel"
ANCHORS_PATH    = "/sdcard/examples/utils/prior_data_320.bin"
DB_DIR          = "/sdcard/examples/utils/db/"
DB_IMG_DIR      = "/sdcard/examples/utils/db_img/"
FACE_DET_INPUT  = [320, 320]
FACE_REG_INPUT  = [112, 112]
CONF_THRESH     = 0.5
NMS_THRESH      = 0.2
ANCHOR_LEN, DET_DIM = 4200, 4


class FaceDetApp(AIBase):
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


def image2rgb888array(img):
    """Image → CHW float 数组（供 AIBase.run 使用）"""
    img_data_rgb888 = img.to_rgb888()
    img_hwc = img_data_rgb888.to_numpy_ref()
    shape = img_hwc.shape
    img_tmp = img_hwc.reshape((shape[0] * shape[1], shape[2]))
    img_tmp_trans = img_tmp.transpose()
    img_res = img_tmp_trans.copy()
    return img_res.reshape((1, shape[2], shape[0], shape[1]))


def extract_feature(fr_det, fr_reg, img_file):
    """从一张照片提取 128 维特征；单人脸时返回特征，否则返回 None"""
    img = image.Image(img_file)
    img.compress_for_ide()
    arr = image2rgb888array(img)
    rgb888p_size = [arr.shape[3], arr.shape[2]]
    fr_det.config_preprocess(input_image_size=rgb888p_size)
    det_boxes, landms = fr_det.run(arr)
    if det_boxes is None or len(det_boxes) != 1:
        print("  - skip ({} persons detected)".format(0 if det_boxes is None else len(det_boxes)))
        return None
    for landm in landms:
        fr_reg.config_preprocess(landm, input_image_size=rgb888p_size)
        reg_result = fr_reg.run(arr)
        return reg_result
    return None


def main():
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR)
    if not os.path.exists(DB_IMG_DIR):
        os.makedirs(DB_IMG_DIR)
        print("请把照片放进 {} 后再运行".format(DB_IMG_DIR))
        return

    anchors = np.fromfile(ANCHORS_PATH, dtype=np.float).reshape((ANCHOR_LEN, DET_DIM))
    fr_det = FaceDetApp(FACE_DET_KMODEL, model_input_size=FACE_DET_INPUT, anchors=anchors,
                        confidence_threshold=CONF_THRESH, nms_threshold=NMS_THRESH)
    fr_reg = FaceRegApp(FACE_REG_KMODEL, model_input_size=FACE_REG_INPUT)

    # 按 前缀（_ 或 . 之前的部分）分组
    groups = {}
    for f in sorted(os.listdir(DB_IMG_DIR)):
        if not f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp')):
            continue
        name = f.split('_')[0].split('.')[0]
        groups.setdefault(name, []).append(f)

    print("[register] groups:", {k: len(v) for k, v in groups.items()})
    for name, files in groups.items():
        feats = []
        for f in files:
            print("[register] {} <- {}".format(name, f))
            feat = extract_feature(fr_det, fr_reg, DB_IMG_DIR + f)
            if feat is not None:
                feats.append(feat)
            gc.collect()
        if not feats:
            print("  - FAIL: {} 没有可用照片（需单人脸清晰正脸）".format(name))
            continue
        # 特征归一化后平均，再归一化
        acc = None
        for ft in feats:
            ft = ft / np.linalg.norm(ft)
            acc = ft if acc is None else acc + ft
        mean_feat = acc / len(feats)
        mean_feat = mean_feat / np.linalg.norm(mean_feat)
        with open(DB_DIR + name + '.bin', 'wb') as fp:
            fp.write(mean_feat.tobytes())
        print("  - OK: {}  <- {} 张照片平均".format(name, len(feats)))

    fr_det.deinit()
    fr_reg.deinit()
    print("[register] done. now run face_recognition_lite_uart.py")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("[register] fatal:", e)
        sys.print_exception(e)
