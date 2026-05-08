# AI 读取提示词 - 企业微信自动化项目

## 项目简介

这是一个基于 Python 的企业微信自动化工具，通过 OCR + SendInput 实现无需管理员权限的自动化操作。

**GitHub**: https://github.com/joey2001q-create/wxauto

---

## 必读文件（按优先级）

### 1. IMPLEMENTATION.md ⭐⭐⭐（最重要）
**必须首先阅读**

包含：
- 核心原理（截图 + OCR + SendInput）
- 完整实现步骤（5个阶段）
- OCR 安全防护机制（白名单、多次确认、位置检查）
- 输入框定位难题及解决方案（轮廓检测 + 多重检查）
- 加好友完整流程代码
- 常见问题解答

### 2. v1.2_DESIGN.md ⭐⭐⭐
**版本设计文档**

包含：
- v1.2 批量测试功能设计
- `test_phones_batch()` 方法设计
- 结果分类逻辑（exists/not_exist/already_friend/failed）
- 使用示例和测试数据

### 3. v1.1_DESIGN.md ⭐⭐
**版本设计文档**

包含：
- v1.1 手机号不存在检测
- `phone_not_exist` 状态设计
- 错误提示检测逻辑

### 4. wxwork_auto.py ⭐⭐⭐
**核心代码文件**

关键类：
- `WXWorkAutomation` - 主自动化类
- 方法：`add_contact_by_phone()`, `test_phones_batch()`
- 输入框定位：`find_input_box_by_contour()`, `locate_input_box_multi_check()`

### 5. demo_batch_test.py ⭐⭐
**批量测试示例**

实际使用示例，展示如何调用批量测试功能。

---

## 快速理解

### 核心架构
```
mss截图 → RapidOCR识别 → SendInput操作
                ↓
        OpenCV轮廓检测（可选增强）
```

### 关键流程
```python
add_contact_by_phone(phone, verify_msg):
    1. 点击搜索框
    2. 输入手机号
    3. 点击"网络查找"结果
    4. 点击"添加"按钮
    5. 轮廓检测定位输入框
    6. 输入验证消息
    7. 点击"发送"按钮
```

### 状态码
- `success` - 添加成功
- `already_friend` - 已是好友
- `phone_not_exist` - 手机号不存在
- `rate_limited` - 添加过于频繁
- `failed` - 其他失败

---

## 当前状态

**Git 分支：**
- `master` - v1.2 稳定版本
- `v1.3-dev` - 开发版本（当前工作分支）

**版本历史：**
- v1.0 - 基础单条添加
- v1.1 - 手机号不存在检测
- v1.2 - 批量测试与结果分类

**待完善（v1.3）：**
- 返回对象结构优化（使用 dataclass）
- LeadProcessor 类封装
- 更多错误状态细化
- API 接口规范化

---

## 关键问题

### 1. 输入框定位
**问题：** 输入框没有文字标签，OCR 识别不到

**解决方案：**
- 优先级1：OpenCV 轮廓检测（找白色矩形）
- 优先级2：模板匹配叉号图标
- 优先级3：从"发送"按钮相对坐标推算

### 2. OCR 错误防护
**问题：** OCR 可能识别错误导致乱操作

**解决方案：**
- 文字白名单过滤
- 多次扫描确认位置稳定性
- 位置合理性检查
- 操作前后验证

### 3. 窗口关闭问题
**问题：** 按两次 Escape 会关闭企业微信窗口

**解决方案：** 所有退出点只按一次 Escape

---

## 依赖

```
mss>=9.0.0
rapidocr-onnxruntime>=1.2.0
opencv-python>=4.8.0  # 可选
numpy>=1.24.0         # 可选
```

---

## 测试数据

```python
phones = [
    "16670239176",    # 存在（可添加）
    "13611111111",    # 不存在
    "13611111122",    # 不存在
    "13682416565"     # 存在（可添加）
]
```

---

## 注意事项

1. **企业微信窗口类名**：`WeWorkWindow`
2. **不要频繁添加**：会触发 `rate_limited`
3. **轮廓检测需要 OpenCV**：但会降级到相对坐标
4. **窗口在前台时操作**：避免被遮挡
5. **Git 分支管理**：在 `v1.3-dev` 开发，稳定后合并到 `master`

---

## 联系上下文

如果用户提到：
- "返回对象优化" → 参考 v1.3 设计，使用 dataclass
- "LeadProcessor" → 封装批量处理逻辑的类
- "API 接口" → 之前讨论过 HTTP API 和本地类接口两种方案
- "版本管理" → 使用 Git 分支，`master` 稳定版，`v1.3-dev` 开发版

---

**最后更新**：2026-05-08
**当前分支**：v1.3-dev
**下一版本**：v1.3（返回对象优化 + LeadProcessor）
