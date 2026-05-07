# -*- coding: utf-8 -*-
"""
模板图片截取工具

用于截取企业微信弹窗中输入框右侧的叉号图标，供OpenCV模板匹配使用。

使用方法：
1. 打开企业微信，进入添加联系人弹窗
2. 运行此脚本: python capture_template.py
3. 脚本会自动截取当前窗口并保存到 templates/clear_button.png
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

from wxwork_auto import WXWorkAutomation
import os
import time


def capture_clear_button_template():
    """截取输入框叉号图标模板"""
    wx = WXWorkAutomation(ocr_confidence=0.8, action_delay=0.3)

    # 确保弹窗打开
    print("请确保企业微信的'发送添加邀请'弹窗已打开")
    print("3秒后开始截取...")
    time.sleep(3)

    # 截图
    rect = wx.get_window_rect()
    screenshot_path = wx.screenshot(save_path="templates/clear_button_area.png")
    print(f"已截取区域截图: {screenshot_path}")
    print(f"窗口大小: {rect.right - rect.left}x{rect.bottom - rect.top}")

    # 提示用户手动裁剪
    print("\n请手动从 templates/clear_button_area.png 中裁剪出叉号图标")
    print("保存为 templates/clear_button.png")
    print("\n叉号图标位置参考：")
    print("- 在输入框右侧")
    print("- 是一个小的圆形或方形的 × 图标")
    print("- 建议裁剪大小约 20x20 像素")


def auto_capture_with_guide():
    """引导式自动截取"""
    wx = WXWorkAutomation(ocr_confidence=0.8, action_delay=0.3)

    print("=== 叉号图标模板截取工具 ===")
    print("\n步骤1: 确保企业微信窗口可见")
    wx.bring_to_front()
    time.sleep(1)

    print("\n步骤2: 请手动打开添加联系人弹窗")
    print("  - 搜索一个手机号")
    print("  - 点击'网络查找'结果")
    print("  - 点击'添加'按钮")
    print("  - 出现'发送添加邀请'弹窗")
    input("\n弹窗打开后按回车继续...")

    # 验证弹窗存在
    popup = wx.find_text("发送添加邀请")
    if not popup:
        print("未检测到弹窗，请重试")
        return

    print(f"检测到弹窗: {popup['text']} at {popup['window_pos']}")

    # 截图
    screenshot_path = wx.screenshot(save_path="templates/clear_button_area.png")
    print(f"\n已保存截图: {screenshot_path}")

    # 尝试自动定位叉号位置（基于相对位置）
    # 叉号在输入框右侧，输入框在发送按钮上方
    send_btn = wx.find_text("发送")
    if send_btn:
        sx, sy = send_btn["window_pos"]
        # 估算叉号位置：发送按钮上方偏右
        clear_x = sx + 50
        clear_y = sy - 76
        print(f"\n估算叉号位置: window({clear_x:.0f}, {clear_y:.0f})")
        print("请在此位置附近查找叉号图标")

    print("\n下一步：")
    print("1. 打开 templates/clear_button_area.png")
    print("2. 裁剪叉号图标区域（约20x20像素）")
    print("3. 保存为 templates/clear_button.png")


if __name__ == "__main__":
    # 创建templates目录
    os.makedirs("templates", exist_ok=True)

    print("选择模式:")
    print("1. 自动引导模式（推荐）")
    print("2. 简单截图模式")
    choice = input("请输入 (1/2): ").strip()

    if choice == "1":
        auto_capture_with_guide()
    else:
        capture_clear_button_template()
