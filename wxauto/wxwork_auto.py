# -*- coding: utf-8 -*-
"""
企业微信自动化工具 - 基于第一性原则设计

核心原理：
  - 看到：mss截图 + RapidOCR识别文字和坐标
  - 操作：SendInput模拟鼠标/键盘事件（硬件级，兼容性最好）

不依赖：
  - Accessibility Tree（企业微信WeWorkWindow无子控件）
  - 坐标硬编码（OCR动态定位）
  - 管理员权限/API
"""

import ctypes
import ctypes.wintypes
import time
import os
import tempfile
import logging

import mss
import mss.tools
from rapidocr_onnxruntime import RapidOCR

# 可选的OpenCV导入
try:
    import cv2
    import numpy as np
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False
    logger = logging.getLogger("wxwork_automation")
    logger.warning("OpenCV未安装，图像识别功能不可用，将使用OCR+相对坐标方案")

logger = logging.getLogger("wxwork_automation")

# ─── Win32 常量 ───
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_BACK = 0x08
VK_TAB = 0x09
VK_CTRL = 0x11
VK_SHIFT = 0x10
VK_ALT = 0x12

user32 = ctypes.windll.user32


# ─── OCR安全相关常量 ───

# 已知有效的UI文字白名单（不在此列表的文字会被警告）
UI_TEXT_WHITELIST = {
    # 主要操作按钮
    "发送", "添加", "确定", "取消", "关闭",
    # 弹窗标题
    "发送添加邀请",
    # 搜索相关
    "搜索", "网络查找",
    # 导航标签
    "消息", "日程", "待办", "会议", "微文档", "微盘", "通讯录", "高级功能", "分组",
    # 状态文字
    "发消息", "授权登录通知",
    # 输入框相关
    "验证申请", "备注", "邀请信息",
    # 其他常见文字
    "星期四", "星期五", "星期一", "星期二", "星期三", "星期六", "星期日",
    "今天", "昨天",
}

# 位置合理性阈值（像素）
POSITION_VARIANCE_THRESHOLD = 30  # 多次扫描位置波动阈值
REASONABLE_POSITION_MARGIN = 50   # 边缘留白


# ─── ctypes 结构体 ───
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long), ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD), ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", _INPUT_UNION)]


class WXWorkAutomation:
    """企业微信自动化控制器"""

    WINDOW_CLASS = "WeWorkWindow"

    def __init__(self, ocr_confidence=0.8, action_delay=0.3):
        self.ocr = RapidOCR()
        self.ocr_confidence = ocr_confidence
        self.action_delay = action_delay
        self._temp_dir = tempfile.gettempdir()

    # ─── 窗口管理 ───

    def find_window(self):
        """查找企业微信主窗口"""
        hwnd = user32.FindWindowW(self.WINDOW_CLASS, None)
        if not hwnd:
            raise RuntimeError("企业微信窗口未找到，请先打开企业微信")
        return hwnd

    def get_window_rect(self):
        """获取窗口位置和大小"""
        hwnd = self.find_window()
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return rect

    def bring_to_front(self):
        """将企业微信窗口置于前台（仅在窗口不是前台时操作）"""
        hwnd = self.find_window()
        foreground = user32.GetForegroundWindow()
        if foreground == hwnd:
            return
        if not user32.IsWindowVisible(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        time.sleep(self.action_delay)

    def is_window_visible(self):
        """检查窗口是否可见"""
        hwnd = self.find_window()
        return bool(user32.IsWindowVisible(hwnd))

    # ─── 截图与OCR ───

    def screenshot(self, save_path=None):
        """截取企业微信窗口截图"""
        rect = self.get_window_rect()
        with mss.MSS() as sct:
            monitor = {
                "left": rect.left, "top": rect.top,
                "width": rect.right - rect.left,
                "height": rect.bottom - rect.top,
            }
            img = sct.grab(monitor)
            if save_path:
                mss.tools.to_png(img.rgb, img.size, output=save_path)
                return save_path
            else:
                path = os.path.join(self._temp_dir, "wxwork_ocr.png")
                mss.tools.to_png(img.rgb, img.size, output=path)
                return path

    def ocr_scan(self, screenshot_path=None):
        """OCR扫描窗口，返回所有识别到的文字"""
        if not screenshot_path:
            screenshot_path = self.screenshot()
        result, elapse = self.ocr(screenshot_path)
        if not result:
            return []

        rect = self.get_window_rect()
        items = []
        for box, text, confidence in result:
            if confidence < self.ocr_confidence:
                continue
            x1, y1 = box[0]
            x2, y2 = box[2]
            items.append({
                "text": text,
                "confidence": confidence,
                "window_pos": ((x1 + x2) / 2, (y1 + y2) / 2),
                "screen_pos": (rect.left + (x1 + x2) / 2, rect.top + (y1 + y2) / 2),
                "window_rect": (x1, y1, x2, y2),
                "screen_rect": (rect.left + x1, rect.top + y1, rect.left + x2, rect.top + y2),
            })
        return items

    def find_text(self, target, screenshot_path=None):
        """查找指定文字在屏幕上的位置"""
        items = self.ocr_scan(screenshot_path)
        for item in items:
            if target in item["text"]:
                return item
        return None

    def find_all_text(self, target, screenshot_path=None):
        """查找所有匹配的文字位置"""
        items = self.ocr_scan(screenshot_path)
        return [item for item in items if target in item["text"]]

    # ─── OCR安全验证方法 ───

    def _is_text_in_whitelist(self, text):
        """检查文字是否在白名单中"""
        if not text:
            return False
        # 检查是否是白名单中的文字，或者是手机号/数字
        if text in UI_TEXT_WHITELIST:
            return True
        # 允许纯数字（手机号等）
        if text.isdigit():
            return True
        # 允许包含已知文字的混合
        for known in UI_TEXT_WHITELIST:
            if known in text:
                return True
        return False

    def _filter_whitelist_items(self, items):
        """过滤OCR结果，只保留白名单中的文字"""
        filtered = []
        for item in items:
            if self._is_text_in_whitelist(item["text"]):
                filtered.append(item)
            else:
                logger.warning(f"OCR识别到非白名单文字: '{item['text']}' (置信度{item['confidence']:.2f})，已过滤")
        return filtered

    def find_text_safe(self, target, confirm_times=2, require_stable=True, use_whitelist=True):
        """安全查找文字（带多重验证）

        Args:
            target: 目标文字
            confirm_times: 确认次数，多次扫描取平均
            require_stable: 是否要求位置稳定
            use_whitelist: 是否过滤白名单

        Returns:
            dict: 包含位置信息，失败返回None
        """
        positions = []
        confidences = []

        for i in range(confirm_times):
            items = self.ocr_scan()
            if use_whitelist:
                items = self._filter_whitelist_items(items)

            for item in items:
                if target in item["text"]:
                    positions.append(item["window_pos"])
                    confidences.append(item["confidence"])
                    break
            else:
                # 本次扫描未找到
                logger.debug(f"第{i+1}次扫描未找到 '{target}'")

            if i < confirm_times - 1:
                time.sleep(0.2)

        if not positions:
            logger.warning(f"安全查找失败: '{target}' 在{confirm_times}次扫描中均未找到")
            return None

        # 检查位置稳定性
        if len(positions) >= 2 and require_stable:
            # 计算位置方差
            avg_x = sum(p[0] for p in positions) / len(positions)
            avg_y = sum(p[1] for p in positions) / len(positions)
            variance = sum((p[0] - avg_x) ** 2 + (p[1] - avg_y) ** 2 for p in positions) / len(positions)

            if variance > POSITION_VARIANCE_THRESHOLD ** 2:
                logger.warning(f"'{target}' 位置不稳定，方差={variance:.1f}，可能识别有误")
                return None

        # 返回平均位置
        avg_pos = (sum(p[0] for p in positions) / len(positions),
                   sum(p[1] for p in positions) / len(positions))
        avg_confidence = sum(confidences) / len(confidences)

        rect = self.get_window_rect()
        return {
            "text": target,
            "window_pos": avg_pos,
            "screen_pos": (rect.left + avg_pos[0], rect.top + avg_pos[1]),
            "confidence": avg_confidence,
            "scans": len(positions),
        }

    def _is_position_reasonable(self, window_pos, expected_region=None):
        """检查位置是否合理

        Args:
            window_pos: 窗口内相对坐标 (x, y)
            expected_region: 预期区域，如 {"x_min": 100, "x_max": 800, "y_min": 200, "y_max": 600}
        """
        rect = self.get_window_rect()
        width = rect.right - rect.left
        height = rect.bottom - rect.top

        x, y = window_pos

        # 基本边界检查（顶部和侧边栏区域放宽）
        if x < REASONABLE_POSITION_MARGIN or x > width - REASONABLE_POSITION_MARGIN:
            logger.warning(f"位置x={x:.0f}超出合理边界")
            return False
        # 顶部搜索区域允许更小的y值（y<50是合理的）
        if y > height - REASONABLE_POSITION_MARGIN:
            logger.warning(f"位置y={y:.0f}超出合理边界")
            return False

        # 特定区域检查
        if expected_region:
            if not (expected_region.get("x_min", 0) <= x <= expected_region.get("x_max", width)):
                logger.warning(f"位置x={x:.0f}不在预期区域")
                return False
            if not (expected_region.get("y_min", 0) <= y <= expected_region.get("y_max", height)):
                logger.warning(f"位置y={y:.0f}不在预期区域")
                return False

        return True

    def click_text_safe(self, target, expected_region=None, pre_verify=True, post_verify=True):
        """安全点击文字（带前后验证）

        Args:
            target: 目标文字
            expected_region: 预期点击区域
            pre_verify: 点击前是否验证目标存在
            post_verify: 点击后是否验证目标消失
        """
        # 点击前验证
        if pre_verify:
            item = self.find_text_safe(target, confirm_times=2)
            if not item:
                raise RuntimeError(f"安全点击失败: 点击前未找到 '{target}'")
        else:
            item = self.find_text(target)
            if not item:
                raise RuntimeError(f"点击失败: 未找到 '{target}'")

        # 位置合理性检查
        if not self._is_position_reasonable(item["window_pos"], expected_region):
            raise RuntimeError(f"点击失败: '{target}' 位置不合理，可能识别错误")

        sx, sy = item["screen_pos"]
        logger.info(f"安全点击 '{target}' at ({sx:.0f}, {sy:.0f})，置信度{item.get('confidence', 0):.2f}")

        # 执行点击
        self.click(int(sx), int(sy))

        # 点击后验证（可选）
        if post_verify:
            time.sleep(0.3)
            if self.find_text(target):
                logger.warning(f"点击后 '{target}' 仍在，可能未点中")

        return item

    def verify_action_result(self, expected_text, timeout=3, should_exist=True):
        """验证操作结果

        Args:
            expected_text: 预期出现的文字
            timeout: 等待超时时间
            should_exist: True=应该出现，False=应该消失

        Returns:
            bool: 验证是否通过
        """
        start = time.time()
        while time.time() - start < timeout:
            found = self.find_text(expected_text)
            if should_exist and found:
                logger.info(f"验证通过: '{expected_text}' 已出现")
                return True
            if not should_exist and not found:
                logger.info(f"验证通过: '{expected_text}' 已消失")
                return True
            time.sleep(0.3)

        logger.warning(f"验证失败: '{expected_text}' 预期{'出现' if should_exist else '消失'}但未满足")
        return False

    # ─── 图像识别方法（OpenCV）───

    def find_template(self, template_path, screenshot_path=None, threshold=0.8):
        """使用OpenCV模板匹配查找图像位置

        Args:
            template_path: 模板图片路径
            screenshot_path: 截图路径，None则自动截图
            threshold: 匹配阈值，0-1之间

        Returns:
            dict: 包含位置信息，未找到返回None
        """
        if not HAS_OPENCV:
            logger.warning("OpenCV未安装，无法使用图像识别")
            return None

        if not os.path.exists(template_path):
            logger.warning(f"模板图片不存在: {template_path}")
            return None

        # 获取截图
        if not screenshot_path:
            screenshot_path = self.screenshot()

        # 读取图片
        screenshot = cv2.imread(screenshot_path)
        template = cv2.imread(template_path)

        if screenshot is None or template is None:
            return None

        # 模板匹配
        result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if max_val < threshold:
            return None

        # 计算中心点坐标
        h, w = template.shape[:2]
        center_x = max_loc[0] + w // 2
        center_y = max_loc[1] + h // 2

        rect = self.get_window_rect()

        return {
            "confidence": max_val,
            "window_pos": (center_x, center_y),
            "screen_pos": (rect.left + center_x, rect.top + center_y),
            "match_rect": (max_loc[0], max_loc[1], max_loc[0] + w, max_loc[1] + h),
        }

    def find_input_box_by_clear_button(self, screenshot_path=None, threshold=0.8):
        """通过叉号图标定位输入框

        输入框右侧有个清除按钮（×），找到它后向左偏移就是输入框
        """
        if not HAS_OPENCV:
            return None

        # 尝试多个可能的模板路径
        template_paths = [
            os.path.join(os.path.dirname(__file__), "templates", "clear_button.png"),
            os.path.join(self._temp_dir, "clear_button.png"),
            "clear_button.png",
        ]

        for template_path in template_paths:
            result = self.find_template(template_path, screenshot_path, threshold)
            if result:
                # 找到叉号，向左偏移60像素就是输入框中心
                cx, cy = result["window_pos"]
                rect = self.get_window_rect()
                return {
                    "method": "opencv_clear_button",
                    "window_pos": (cx - 60, cy),
                    "screen_pos": (rect.left + cx - 60, rect.top + cy),
                    "confidence": result["confidence"],
                }

        return None

    def find_input_box_by_contour(self, screenshot_path=None):
        """通过轮廓检测找输入框

        基于"发送添加邀请"标题位置，在其下方ROI区域内
        用OpenCV轮廓检测找输入框（白色矩形区域）

        Returns:
            dict: 包含位置信息，失败返回None
        """
        if not HAS_OPENCV:
            return None

        # 1. 找到弹窗标题
        popup_title = self.find_text_safe("发送添加邀请", confirm_times=1, require_stable=False)
        if not popup_title:
            logger.warning("轮廓检测：未找到弹窗标题")
            return None

        tx, ty = popup_title["window_pos"]

        # 2. 截取标题下方的ROI区域（相对标题位置）
        # ROI: 标题下方60px开始，宽度400px，高度120px
        roi_x = int(tx - 200)  # 标题左侧200px
        roi_y = int(ty + 60)   # 标题下方60px
        roi_w = 400
        roi_h = 120

        # 确保ROI在窗口范围内
        rect = self.get_window_rect()
        window_w = rect.right - rect.left
        window_h = rect.bottom - rect.top

        roi_x = max(0, min(roi_x, window_w - roi_w))
        roi_y = max(0, min(roi_y, window_h - roi_h))

        # 获取截图
        if not screenshot_path:
            screenshot_path = self.screenshot()

        # 读取截图并截取ROI
        screenshot = cv2.imread(screenshot_path)
        if screenshot is None:
            return None

        # ROI坐标转换为截图坐标（截图就是窗口内容）
        roi = screenshot[roi_y:roi_y + roi_h, roi_x:roi_x + roi_w]

        # 3. 图像处理找输入框
        # 转灰度
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        # 二值化 - 找白色/浅色区域（输入框背景）
        # 输入框通常是白色或很浅的灰色
        _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

        # 边缘检测
        edges = cv2.Canny(gray, 50, 150)

        # 找轮廓
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best_contour = None
        best_score = 0

        for contour in contours:
            # 近似多边形
            epsilon = 0.02 * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)

            # 只考虑四边形（矩形）
            if len(approx) != 4:
                continue

            # 获取边界框
            x, y, w, h = cv2.boundingRect(approx)

            # 筛选条件：
            # 1. 面积足够大（排除噪点）
            area = w * h
            if area < 2000 or area > roi_w * roi_h * 0.8:
                continue

            # 2. 宽高比在合理范围（横向输入框，宽度是高度的3-15倍）
            aspect_ratio = w / h if h > 0 else 0
            if aspect_ratio < 3 or aspect_ratio > 15:
                continue

            # 3. 在ROI中心区域（输入框通常在中间）
            center_x = x + w // 2
            center_y = y + h // 2
            if abs(center_x - roi_w // 2) > roi_w // 3:
                continue

            # 4. 白色区域占比高（输入框背景是白色）
            white_ratio = np.sum(binary[y:y+h, x:x+w] == 255) / (w * h)
            if white_ratio < 0.7:
                continue

            # 计算得分（面积越大越好，越居中越好）
            center_score = 1 - abs(center_x - roi_w // 2) / (roi_w // 2)
            score = area * center_score

            if score > best_score:
                best_score = score
                best_contour = (x, y, w, h)

        if best_contour is None:
            logger.warning("轮廓检测：未找到符合条件的输入框")
            return None

        x, y, w, h = best_contour
        center_x = x + w // 2
        center_y = y + h // 2

        # 转换回窗口坐标
        window_x = roi_x + center_x
        window_y = roi_y + center_y

        logger.info(f"轮廓检测找到输入框: window({window_x}, {window_y}), 大小{w}x{h}")

        return {
            "method": "contour_detection",
            "window_pos": (window_x, window_y),
            "screen_pos": (rect.left + window_x, rect.top + window_y),
            "confidence": 0.85,
            "size": (w, h),
        }

    def locate_input_box_multi_check(self, phone, verify_msg):
        """多重检查机制定位输入框

        使用多种方法交叉验证，确保定位准确：
        1. 轮廓检测（基于标题ROI找输入框）- 优先级最高
        2. OpenCV 找叉号图标
        3. OCR + 相对坐标（从"发送"按钮推算）- 兜底
        4. 交叉验证：结果对比
        5. 兜底：优先使用置信度高的结果

        Returns:
            tuple: (screen_x, screen_y, method_used)
        """
        results = []

        # 方法1: 轮廓检测（优先级最高，不依赖坐标偏移）
        if HAS_OPENCV:
            contour_result = self.find_input_box_by_contour()
            if contour_result:
                results.append(contour_result)

        # 方法2: OpenCV 找叉号图标
        if HAS_OPENCV:
            cv_result = self.find_input_box_by_clear_button()
            if cv_result:
                results.append(cv_result)

        # 方法3: OCR + 相对坐标（兜底方案）
        send_btn = self.find_text("发送")
        if send_btn:
            sx, sy = send_btn["window_pos"]
            # 输入框在发送按钮上方偏左
            input_x = sx - 110
            input_y = sy - 76
            rect = self.get_window_rect()
            results.append({
                "method": "ocr_relative",
                "screen_pos": (rect.left + input_x, rect.top + input_y),
                "window_pos": (input_x, input_y),
                "confidence": send_btn.get("confidence", 0.9) * 0.8,  # 相对坐标置信度打折扣
            })

        # 如果没有结果，报错
        if not results:
            raise RuntimeError("无法定位输入框：所有方法均失败")

        # 只有一条结果，直接使用
        if len(results) == 1:
            r = results[0]
            logger.info(f"使用单一方法定位输入框: {r['method']} at {r['screen_pos']}")
            return (*r["screen_pos"], r["method"])

        # 多条结果，进行交叉验证
        # 计算结果间的距离
        pos1 = results[0]["window_pos"]
        pos2 = results[1]["window_pos"]
        distance = ((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2) ** 0.5

        logger.info(f"多重验证: {results[0]['method']} vs {results[1]['method']}, 距离={distance:.1f}px")

        # 如果距离小于阈值（50像素），认为验证通过，取平均值
        if distance < 50:
            avg_x = (pos1[0] + pos2[0]) / 2
            avg_y = (pos1[1] + pos2[1]) / 2
            rect = self.get_window_rect()
            final_pos = (rect.left + avg_x, rect.top + avg_y)
            logger.info(f"交叉验证通过，使用平均位置: {final_pos}")
            return (*final_pos, "averaged")

        # 距离过大，选择置信度高的结果
        best = max(results, key=lambda x: x.get("confidence", 0))
        logger.warning(f"交叉验证失败（距离{distance:.1f}px），使用高置信度结果: {best['method']}")
        return (*best["screen_pos"], best["method"])

    # ─── 鼠标操作 ───

    def click(self, screen_x, screen_y, button="left", count=1, ensure_foreground=False):
        """在指定屏幕坐标点击"""
        if ensure_foreground:
            self.bring_to_front()
            time.sleep(0.1)
        user32.SetCursorPos(screen_x, screen_y)
        time.sleep(0.05)

        if button == "left":
            down_flag, up_flag = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
        elif button == "right":
            down_flag, up_flag = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
        else:
            raise ValueError(f"不支持按钮类型: {button}")

        extra = ctypes.c_ulong(0)
        for _ in range(count):
            for flag in [down_flag, up_flag]:
                inp = INPUT()
                inp.type = INPUT_MOUSE
                inp.union.mi.dwFlags = flag
                inp.union.mi.dwExtraInfo = ctypes.pointer(extra)
                user32.SendInput(1, ctypes.pointer(inp), ctypes.sizeof(INPUT))
                time.sleep(0.03)
            time.sleep(0.1)
        time.sleep(self.action_delay)

    def click_text(self, target, button="left", count=1, ensure_foreground=False):
        """点击指定文字所在位置"""
        item = self.find_text(target)
        if not item:
            raise RuntimeError(f"未找到文字: {target}")
        sx, sy = item["screen_pos"]
        logger.info(f"点击 '{target}' at ({sx:.0f}, {sy:.0f})")
        self.click(int(sx), int(sy), button, count, ensure_foreground)
        return item

    def double_click_text(self, target):
        """双击指定文字"""
        return self.click_text(target, count=2)

    # ─── 键盘操作 ───

    def type_text(self, text, delay=0.02):
        """输入文字（支持中文）"""
        extra = ctypes.c_ulong(0)
        for char in text:
            inp_down = INPUT()
            inp_down.type = INPUT_KEYBOARD
            inp_down.union.ki.wVk = 0
            inp_down.union.ki.wScan = ord(char)
            inp_down.union.ki.dwFlags = KEYEVENTF_UNICODE
            inp_down.union.ki.dwExtraInfo = ctypes.pointer(extra)

            inp_up = INPUT()
            inp_up.type = INPUT_KEYBOARD
            inp_up.union.ki.wVk = 0
            inp_up.union.ki.wScan = ord(char)
            inp_up.union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
            inp_up.union.ki.dwExtraInfo = ctypes.pointer(extra)

            user32.SendInput(1, ctypes.pointer(inp_down), ctypes.sizeof(INPUT))
            time.sleep(delay)
            user32.SendInput(1, ctypes.pointer(inp_up), ctypes.sizeof(INPUT))
            time.sleep(delay)
        time.sleep(self.action_delay)

    def press_key(self, vk_code, count=1):
        """按下指定虚拟键码"""
        extra = ctypes.c_ulong(0)
        for _ in range(count):
            inp_down = INPUT()
            inp_down.type = INPUT_KEYBOARD
            inp_down.union.ki.wVk = vk_code
            inp_down.union.ki.dwExtraInfo = ctypes.pointer(extra)

            inp_up = INPUT()
            inp_up.type = INPUT_KEYBOARD
            inp_up.union.ki.wVk = vk_code
            inp_up.union.ki.dwFlags = KEYEVENTF_KEYUP
            inp_up.union.ki.dwExtraInfo = ctypes.pointer(extra)

            user32.SendInput(1, ctypes.pointer(inp_down), ctypes.sizeof(INPUT))
            time.sleep(0.05)
            user32.SendInput(1, ctypes.pointer(inp_up), ctypes.sizeof(INPUT))
            time.sleep(0.1)
        time.sleep(self.action_delay)

    def press_enter(self):
        """按回车键"""
        self.press_key(VK_RETURN)

    def press_escape(self):
        """按Esc键"""
        self.press_key(VK_ESCAPE)

    def press_backspace(self, count=1):
        """按退格键"""
        self.press_key(VK_BACK, count)

    def press_tab(self):
        """按Tab键"""
        self.press_key(VK_TAB)

    def hotkey(self, *vk_codes):
        """发送组合键（如 Ctrl+C）"""
        extra = ctypes.c_ulong(0)
        # 按下所有键
        for vk in vk_codes:
            inp = INPUT()
            inp.type = INPUT_KEYBOARD
            inp.union.ki.wVk = vk
            inp.union.ki.dwExtraInfo = ctypes.pointer(extra)
            user32.SendInput(1, ctypes.pointer(inp), ctypes.sizeof(INPUT))
            time.sleep(0.05)
        # 释放所有键（逆序）
        for vk in reversed(vk_codes):
            inp = INPUT()
            inp.type = INPUT_KEYBOARD
            inp.union.ki.wVk = vk
            inp.union.ki.dwFlags = KEYEVENTF_KEYUP
            inp.union.ki.dwExtraInfo = ctypes.pointer(extra)
            user32.SendInput(1, ctypes.pointer(inp), ctypes.sizeof(INPUT))
            time.sleep(0.05)
        time.sleep(self.action_delay)

    def ctrl_a(self):
        """Ctrl+A 全选"""
        self.hotkey(VK_CTRL, 0x41)

    def ctrl_c(self):
        """Ctrl+C 复制"""
        self.hotkey(VK_CTRL, 0x43)

    def ctrl_v(self):
        """Ctrl+V 粘贴"""
        self.hotkey(VK_CTRL, 0x56)

    # ─── 等待与验证 ───

    def wait_for_text(self, target, timeout=10, interval=1):
        """等待指定文字出现在屏幕上"""
        start = time.time()
        while time.time() - start < timeout:
            item = self.find_text(target)
            if item:
                return item
            time.sleep(interval)
        raise TimeoutError(f"等待文字 '{target}' 超时 ({timeout}s)")

    def wait_for_text_disappear(self, target, timeout=10, interval=1):
        """等待指定文字从屏幕上消失"""
        start = time.time()
        while time.time() - start < timeout:
            item = self.find_text(target)
            if not item:
                return True
            time.sleep(interval)
        raise TimeoutError(f"等待文字 '{target}' 消失超时 ({timeout}s)")

    # ─── 企业微信专用操作 ───

    def navigate_to(self, tab_name):
        """导航到左侧栏指定标签页（消息/日程/待办/会议等）"""
        return self.click_text(tab_name)

    def search_contact(self, name):
        """搜索联系人"""
        self.click_text("搜索")
        time.sleep(0.5)
        self.type_text(name)
        time.sleep(1)
        return self.ocr_scan()

    def send_message_to(self, contact_name, message):
        """发送消息给指定联系人"""
        # 1. 搜索联系人
        self.click_text("搜索")
        time.sleep(0.5)
        self.type_text(contact_name)
        time.sleep(1)

        # 2. 点击搜索结果中的联系人
        contact = self.find_text(contact_name)
        if not contact:
            raise RuntimeError(f"未找到联系人: {contact_name}")
        self.click(int(contact["screen_pos"][0]), int(contact["screen_pos"][1]))
        time.sleep(1)

        # 3. 点击消息输入框
        self.press_escape()  # 关闭搜索
        time.sleep(0.5)

        # 4. 输入消息并发送
        self.type_text(message)
        self.press_enter()

    def get_chat_messages(self, save_path=None):
        """获取当前聊天窗口的消息列表"""
        items = self.ocr_scan(save_path)
        # 过滤出聊天区域内的文字（排除侧边栏和顶部）
        rect = self.get_window_rect()
        sidebar_width = 60  # 左侧栏大约60px宽
        chat_items = [
            item for item in items
            if item["window_pos"][0] > sidebar_width
        ]
        return chat_items

    def get_contact_list(self):
        """获取当前可见的联系人列表"""
        items = self.ocr_scan()
        # 左侧栏联系人区域
        return [
            item for item in items
            if item["window_pos"][0] < 200 and item["window_pos"][0] > 60
        ]

    # ─── 添加联系人 ───

    def add_contact_by_phone(self, phone, verify_msg=None, timeout=10):
        """通过手机号添加联系人

        Args:
            phone: 手机号码
            verify_msg: 好友验证消息，为None则不填写
            timeout: 等待搜索结果的超时时间(秒)

        Returns:
            dict: {"status": "success"|"already_friend"|"not_found"|"failed", "detail": str}
        """
        # 1. 确保在前台并回到消息页面（不强制bring_to_front，避免黑屏）
        # self.bring_to_front()  # 暂时禁用，可能导致窗口黑屏
        time.sleep(0.3)
        try:
            self.click_text("消息")
            time.sleep(0.5)
        except RuntimeError:
            pass

        # 2. 点击搜索框（使用普通查找，位置固定）
        search_item = self.find_text("搜索")
        if not search_item:
            return {"status": "failed", "detail": "未找到搜索框"}
        sx, sy = search_item["screen_pos"]
        self.click(int(sx), int(sy))
        time.sleep(0.5)

        # 3. 清空搜索框并输入手机号
        self.ctrl_a()
        time.sleep(0.1)
        self.press_backspace()
        time.sleep(0.1)
        self.type_text(phone)
        time.sleep(2.0)  # 增加等待时间，让搜索结果出现

        # 4. 查找搜索结果 — 优先找"网络查找"，其次找手机号本身
        # 使用普通查找，避免多次扫描不稳定
        lookup_item = self.find_text("网络查找")
        if not lookup_item:
            # 尝试查找手机号（数字允许）
            items = self.ocr_scan()
            for item in items:
                if phone in item["text"] and item["text"].replace(phone, "").strip() == "":
                    lookup_item = item
                    break
        if not lookup_item:
            self.press_escape()
            return {"status": "not_found", "detail": f"未找到手机号 {phone} 的搜索结果"}

        # 验证位置合理性（搜索结果应在搜索框下方）
        if not self._is_position_reasonable(lookup_item["window_pos"], {"y_min": 80}):
            self.press_escape()
            return {"status": "failed", "detail": "搜索结果位置异常，可能识别错误"}

        lx, ly = lookup_item["screen_pos"]
        self.click(int(lx), int(ly))
        time.sleep(1.5)

        # 5.1 检查是否出现"用户不存在"提示
        not_exist_hints = ["该用户不存在", "无法找到该用户", "用户不存在"]
        for hint in not_exist_hints:
            if self.find_text(hint):
                # 点击确定关闭提示
                try:
                    self.click_text("确定")
                    time.sleep(0.3)
                except:
                    pass
                self.press_escape()
                time.sleep(0.3)
                return {"status": "phone_not_exist", "detail": f"手机号 {phone} 不存在或无法找到"}

        # 5.2 检查是否出现"添加频繁"提示
        frequent_hints = ["添加好友过于频繁", "提升添加频率", "过于频繁"]
        for hint in frequent_hints:
            if self.find_text(hint):
                # 点击确定关闭提示
                try:
                    self.click_text("确定")
                    time.sleep(0.3)
                except:
                    pass
                self.press_escape()
                time.sleep(0.3)
                return {"status": "rate_limited", "detail": "添加好友过于频繁，请稍后再试"}

        # 5.3 判断当前状态
        # 检查是否已是好友（出现"发消息"按钮而非"添加"）
        if self.find_text_safe("发消息", confirm_times=1, require_stable=False):
            self.press_escape()
            time.sleep(0.3)
            return {"status": "already_friend", "detail": f"{phone} 已是好友"}

        # 检查是否有"添加"按钮（使用安全查找）
        # 【调试】保存截图查看 OCR 识别结果
        debug_path = os.path.join(tempfile.gettempdir(), f"debug_add_btn_{phone}.png")
        self.capture_screenshot(debug_path)
        logger.info(f"[调试] 已保存截图: {debug_path}")

        # 【调试】输出所有 OCR 识别结果
        all_items = self.ocr_scan()
        logger.info(f"[调试] OCR 识别到 {len(all_items)} 个文本项:")
        for item in all_items:
            logger.info(f"  - '{item['text']}' at ({item['window_pos']})")

        add_item = self.find_text_safe("添加", confirm_times=2)
        if not add_item:
            self.press_escape()
            time.sleep(0.3)
            return {"status": "failed", "detail": "未找到'添加'按钮，可能无法添加该联系人"}

        # 验证"添加"按钮位置合理性（应在右侧联系人详情区域）
        if not self._is_position_reasonable(add_item["window_pos"], {"x_min": 200, "y_min": 150}):
            self.press_escape()
            time.sleep(0.3)
            return {"status": "failed", "detail": "'添加'按钮位置异常，可能识别错误"}

        # 6. 点击"添加"按钮，弹出"发送添加邀请"弹窗
        ax, ay = add_item["screen_pos"]
        logger.info(f"点击'添加'按钮 at ({ax:.0f}, {ay:.0f})")
        self.click(int(ax), int(ay))
        time.sleep(1)

        # 7. 等待弹窗出现，确认弹窗标题"发送添加邀请"
        if not self.verify_action_result("发送添加邀请", timeout=3, should_exist=True):
            self.press_escape()
            time.sleep(0.3)
            return {"status": "failed", "detail": "点击添加后未出现弹窗"}

        # 8. 点击输入框并输入邀请信息（使用多重检查机制）
        try:
            input_x, input_y, method_used = self.locate_input_box_multi_check(phone, verify_msg)
            logger.info(f"使用 {method_used} 定位输入框，点击 ({input_x:.0f}, {input_y:.0f})")
            self.click(int(input_x), int(input_y))
            time.sleep(0.3)
        except RuntimeError as e:
            self.press_escape()
            time.sleep(0.3)
            return {"status": "failed", "detail": f"定位输入框失败: {str(e)}"}

        # 清空输入框原有内容
        self.ctrl_a()
        time.sleep(0.1)
        self.press_backspace()
        time.sleep(0.1)

        if verify_msg:
            self.type_text(verify_msg)
            time.sleep(0.3)

            # 9. 验证输入是否成功（OCR检查，只做一次验证）
            items = self.ocr_scan()
            input_verified = False
            for item in items:
                if verify_msg in item["text"]:
                    input_verified = True
                    logger.info(f"输入验证通过，找到文字: {item['text']}")
                    break

            if not input_verified:
                logger.warning("输入验证失败，但继续执行")
                # 不返回错误，继续尝试点击发送

        # 10. 点击"发送"按钮（找弹窗内下方的"发送"，不是标题）
        # 弹窗内有两个"发送"相关文字：标题"发送添加邀请"和按钮"发送"
        # 按钮在下方，y 坐标更大

        # 【测试模式】只对测试手机号执行真实发送
        TEST_PHONE = "16670239176"
        if phone != TEST_PHONE:
            logger.info(f"[测试模式] 非测试手机号 {phone}，跳过发送")
            # 关闭弹窗
            self.press_escape()
            time.sleep(0.3)
            self.press_escape()
            time.sleep(0.3)
            return {"status": "success", "detail": f"[测试模式] 已填写验证消息，未发送给 {phone}"}

        # 测试手机号：执行真实发送流程
        logger.info(f"[测试模式] 测试手机号 {TEST_PHONE}，执行真实发送")
        send_items = self.find_all_text("发送")
        if len(send_items) >= 2:
            # 按 y 坐标排序，找最下方的（y 最大的）
            send_items.sort(key=lambda x: x["window_pos"][1])
            send_btn = send_items[-1]  # 最后一个就是 y 最大的
            bx, by = send_btn["screen_pos"]
            self.click(int(bx), int(by))
            time.sleep(1)
        elif len(send_items) == 1:
            # 只有一个，检查 y 坐标是否在下方（> 300）
            if send_items[0]["window_pos"][1] > 300:
                send_btn = send_items[0]
                bx, by = send_btn["screen_pos"]
                self.click(int(bx), int(by))
                time.sleep(1)
            else:
                return {"status": "failed", "detail": "找到的发送文字位置异常，可能是标题而非按钮"}
        else:
            return {"status": "failed", "detail": "未找到发送按钮"}

        # 11. 验证发送结果（弹窗应消失）
        if not self.verify_action_result("发送添加邀请", timeout=2, should_exist=False):
            logger.warning("弹窗可能未正常关闭")

        # 12. 关闭搜索，回到消息页面（只按一次Escape）
        self.press_escape()
        time.sleep(0.3)

        return {"status": "success", "detail": f"已向 {phone} 发送添加邀请"}

    def add_contacts_batch(self, phones, verify_msg=None, interval=2):
        """批量通过手机号添加联系人

        Args:
            phones: 手机号列表
            verify_msg: 好友验证消息
            interval: 每次添加之间的间隔时间(秒)

        Returns:
            list[dict]: 每个手机号的添加结果
        """
        results = []
        for phone in phones:
            try:
                result = self.add_contact_by_phone(phone, verify_msg)
            except Exception as e:
                result = {"status": "failed", "detail": str(e)}
            result["phone"] = phone
            results.append(result)
            logger.info(f"添加 {phone}: {result['status']} - {result['detail']}")
            if interval > 0:
                time.sleep(interval)
        return results

    def test_phones_batch(self, phones, verify_msg=None, interval=3):
        """批量测试手机号，分类结果

        Args:
            phones: 手机号列表
            verify_msg: 验证消息
            interval: 每次测试间隔(秒)

        Returns:
            dict: {
                "exists": [],      # 存在的手机号
                "not_exist": [],   # 不存在的手机号
                "already_friend": [],  # 已是好友
                "failed": [],      # 其他失败
                "details": [],     # 详细结果
                "summary": {}      # 统计信息
            }
        """
        results = {
            "exists": [],
            "not_exist": [],
            "already_friend": [],
            "failed": [],
            "details": []
        }

        total = len(phones)
        for i, phone in enumerate(phones, 1):
            logger.info(f"[{i}/{total}] 测试手机号: {phone}")
            print(f"[{i}/{total}] 测试手机号: {phone}")

            # 执行添加
            result = self.add_contact_by_phone(phone, verify_msg)
            result["phone"] = phone
            result["index"] = i

            # 分类结果
            status = result["status"]
            if status == "success":
                results["exists"].append(phone)
                logger.info(f"  [OK] 存在，添加成功")
                print(f"  [OK] 存在，添加成功")
            elif status == "phone_not_exist":
                results["not_exist"].append(phone)
                logger.info(f"  [NO] 不存在")
                print(f"  [NO] 不存在")
            elif status == "already_friend":
                results["already_friend"].append(phone)
                logger.info(f"  [FRIEND] 已是好友")
                print(f"  [FRIEND] 已是好友")
            else:
                results["failed"].append(phone)
                logger.warning(f"  [FAIL] 失败: {result['detail']}")
                print(f"  [FAIL] 失败: {result['detail']}")

            results["details"].append(result)

            # 间隔
            if i < total and interval > 0:
                time.sleep(interval)

        # 统计
        results["summary"] = {
            "total": total,
            "exists": len(results["exists"]),
            "not_exist": len(results["not_exist"]),
            "already_friend": len(results["already_friend"]),
            "failed": len(results["failed"])
        }

        return results

    def save_not_exist_phones(self, results, filepath="not_exist_phones.txt"):
        """保存不存在的手机号到文件

        Args:
            results: test_phones_batch 返回的结果
            filepath: 保存路径
        """
        not_exist = results.get("not_exist", [])
        with open(filepath, "w", encoding="utf-8") as f:
            for phone in not_exist:
                f.write(phone + "\n")
        logger.info(f"已保存 {len(not_exist)} 个不存在的手机号到 {filepath}")
        print(f"已保存 {len(not_exist)} 个不存在的手机号到 {filepath}")
        return filepath