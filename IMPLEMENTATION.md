# 企业微信自动化实现文档

## 项目简介

基于 OCR + SendInput 实现的企业微信自动化工具，无需管理员权限，不依赖 Accessibility API，通过屏幕文字识别和硬件级输入模拟实现自动化操作。

GitHub: https://github.com/joey2001q-create/wxauto

---

## 核心原理

### 看到
- **mss**: 截取企业微信窗口截图
- **RapidOCR**: 识别屏幕上的文字和位置坐标

### 操作
- **SendInput**: Windows API 硬件级输入模拟，兼容性最好

### 不依赖
- Accessibility Tree（企业微信无子控件）
- 固定坐标（通过 OCR 动态定位）
- 管理员权限

---

## 实现步骤

### 第一步：基础架构搭建

#### 1.1 窗口管理
```python
# 查找企业微信窗口句柄
hwnd = user32.FindWindowW("WeWorkWindow", None)

# 获取窗口位置和大小
user32.GetWindowRect(hwnd, ctypes.byref(rect))

# 窗口截图（仅截取企业微信区域）
with mss.MSS() as sct:
    monitor = {
        "left": rect.left,
        "top": rect.top,
        "width": rect.right - rect.left,
        "height": rect.bottom - rect.top,
    }
    img = sct.grab(monitor)
```

#### 1.2 OCR 文字识别
```python
from rapidocr_onnxruntime import RapidOCR

ocr = RapidOCR()
result, elapse = ocr(screenshot_path)

# 解析结果获取文字和坐标
for box, text, confidence in result:
    x1, y1 = box[0]
    x2, y2 = box[2]
    center_x = (x1 + x2) / 2
    center_y = (y1 + y2) / 2
```

#### 1.3 鼠标键盘模拟
```python
# SendInput 模拟点击
user32.SetCursorPos(screen_x, screen_y)

# 发送鼠标事件
inp = INPUT()
inp.type = INPUT_MOUSE
inp.union.mi.dwFlags = MOUSEEVENTF_LEFTDOWN
user32.SendInput(1, ctypes.pointer(inp), ctypes.sizeof(INPUT))

# 发送键盘事件（支持中文）
inp.type = INPUT_KEYBOARD
inp.union.ki.wScan = ord(char)
inp.union.ki.dwFlags = KEYEVENTF_UNICODE
```

---

### 第二步：OCR 安全防护机制

#### 2.1 问题识别
OCR 可能出错：
- 识别到错误文字（"发送"识别成"发途"）
- 位置偏差
- 漏识别/误识别

#### 2.2 解决方案

**文字白名单**
```python
UI_TEXT_WHITELIST = {
    "发送", "添加", "搜索", "消息",
    "发送添加邀请", "网络查找", ...
}

def _is_text_in_whitelist(self, text):
    if text in UI_TEXT_WHITELIST:
        return True
    if text.isdigit():  # 允许纯数字（手机号）
        return True
    return False
```

**多次扫描确认**
```python
def find_text_safe(self, target, confirm_times=2):
    positions = []
    for i in range(confirm_times):
        item = self.find_text(target)
        if item:
            positions.append(item["window_pos"])
        time.sleep(0.2)
    
    # 检查位置稳定性
    variance = calculate_variance(positions)
    if variance > threshold:
        return None  # 位置波动大，可能识别错误
```

**位置合理性检查**
```python
def _is_position_reasonable(self, window_pos, expected_region=None):
    # 检查是否在窗口范围内
    if x < margin or x > width - margin:
        return False
    
    # 检查是否在预期区域内
    if expected_region:
        if not (x_min <= x <= x_max):
            return False
```

**操作前后验证**
```python
def click_text_safe(self, target):
    # 点击前验证
    item = self.find_text_safe(target)
    if not item:
        raise RuntimeError(f"未找到: {target}")
    
    # 执行点击
    self.click(item["screen_pos"])
    
    # 点击后验证
    time.sleep(0.3)
    if self.find_text(target):
        logger.warning(f"点击后 {target} 仍在，可能未点中")
```

---

### 第三步：输入框定位难题

#### 3.1 问题
加好友弹窗中的输入框：
- 没有文字标签
- 叉号图标太小，模板匹配不稳定
- 相对坐标随窗口大小变化

#### 3.2 解决方案：多重检查机制

**优先级 1：OpenCV 轮廓检测（推荐）**
```python
def find_input_box_by_contour(self):
    # 1. 找到弹窗标题
    popup_title = self.find_text("发送添加邀请")
    tx, ty = popup_title["window_pos"]
    
    # 2. 截取标题下方 ROI 区域
    roi = screenshot[ty+60:ty+180, tx-200:tx+200]
    
    # 3. 图像处理找输入框
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # 4. 筛选轮廓
    for contour in contours:
        # 四边形（矩形）
        approx = cv2.approxPolyDP(contour, epsilon, True)
        if len(approx) != 4:
            continue
        
        # 宽高比合理（横向输入框）
        aspect_ratio = w / h
        if not (3 < aspect_ratio < 15):
            continue
        
        # 白色区域占比高
        white_ratio = np.sum(binary == 255) / (w * h)
        if white_ratio < 0.7:
            continue
        
        return center_x, center_y
```

**优先级 2：OpenCV 模板匹配（叉号图标）**
```python
def find_input_box_by_clear_button(self):
    template = cv2.imread("clear_button.png")
    result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
    
    if max_val > threshold:
        # 找到叉号，向左偏移就是输入框
        return (cx - 60, cy)
```

**优先级 3：OCR + 相对坐标（兜底）**
```python
# 从"发送"按钮推算输入框位置
send_btn = self.find_text("发送")
input_x = send_btn["window_pos"][0] - 110
input_y = send_btn["window_pos"][1] - 76
```

**交叉验证**
```python
def locate_input_box_multi_check(self):
    results = []
    
    # 方法1: 轮廓检测
    r1 = self.find_input_box_by_contour()
    if r1: results.append(r1)
    
    # 方法2: 叉号图标
    r2 = self.find_input_box_by_clear_button()
    if r2: results.append(r2)
    
    # 方法3: 相对坐标
    r3 = self.find_input_box_by_relative()
    if r3: results.append(r3)
    
    # 交叉验证
    if len(results) >= 2:
        # 计算结果间距离
        distance = calculate_distance(results[0], results[1])
        if distance < 50:
            return average(results)  # 验证通过，取平均
    
    # 选择置信度最高的
    return max(results, key=lambda x: x["confidence"])
```

---

### 第四步：加好友完整流程

```python
def add_contact_by_phone(self, phone, verify_msg):
    # 1. 点击搜索框
    self.click_text_safe("搜索")
    
    # 2. 输入手机号
    self.type_text(phone)
    time.sleep(2)
    
    # 3. 点击搜索结果
    self.click_text_safe("网络查找")
    
    # 4. 点击添加按钮
    self.click_text_safe("添加", expected_region={"x_min": 200})
    
    # 5. 定位输入框（多重检查）
    x, y, method = self.locate_input_box_multi_check()
    self.click(x, y)
    
    # 6. 输入验证消息
    self.type_text(verify_msg)
    
    # 7. 点击发送按钮（注意区分标题和按钮）
    send_items = self.find_all_text("发送")
    send_items.sort(key=lambda x: x["window_pos"][1])  # 按 y 排序
    send_btn = send_items[-1]  # 取最下方的（按钮）
    self.click(send_btn["screen_pos"])
```

---

### 第五步：测试与调试

#### 5.1 单元测试
```python
# 测试轮廓检测
result = wx.find_input_box_by_contour()
print(f"找到输入框: {result}")
wx.click(result["screen_pos"])
```

#### 5.2 截图调试
```python
# 关键步骤截图保存
path = wx.screenshot(save_path=f"debug_step{step}.png")
```

#### 5.3 日志记录
```python
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("wxwork_automation")
```

---

## 常见问题

### Q: OCR 识别率低怎么办？
A: 
- 提高置信度阈值 `ocr_confidence`
- 增加截图清晰度
- 考虑升级到 PaddleOCR（中文更准但体积大）

### Q: 窗口被遮挡怎么办？
A:
- 避免使用 `bring_to_front()` 可能导致黑屏
- 手动确保窗口在前台
- 截图前检查窗口状态

### Q: 点击位置不准怎么办？
A:
- 使用 `click_text_safe()` 带验证
- 增加 `expected_region` 限制
- 使用轮廓检测替代相对坐标

### Q: 如何支持其他分辨率？
A:
- 使用窗口相对坐标而非屏幕绝对坐标
- 基于文字定位而非固定坐标
- 图像识别使用比例而非固定像素

---

## 扩展建议

1. **多分辨率适配**: 根据窗口大小动态计算 ROI
2. **异常恢复**: 增加状态机，异常时自动重置
3. **批量操作**: 支持手机号列表批量添加
4. **日志记录**: 保存操作日志和截图用于追溯
5. **配置化**: 支持 JSON/YAML 配置不同场景

---

## 参考

- [RapidOCR](https://github.com/RapidAI/RapidOCR)
- [MSS](https://github.com/BoboTiG/python-mss)
- [OpenCV](https://opencv.org/)
- Windows SendInput API
