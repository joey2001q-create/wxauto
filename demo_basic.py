# -*- coding: utf-8 -*-
"""
企业微信自动化工具 - 快速入门示例
"""

from wxwork_auto import WXWorkAutomation
import time

def main():
    wx = WXWorkAutomation(ocr_confidence=0.8, action_delay=0.3)

    # ─── 基础操作演示 ───

    print("1. 扫描当前界面所有文字")
    items = wx.ocr_scan()
    for item in items:
        print(f"  [{item['confidence']:.2f}] \"{item['text']}\" at ({item['screen_pos'][0]:.0f}, {item['screen_pos'][1]:.0f})")

    print("\n2. 导航到日程页面")
    wx.navigate_to("日程")
    time.sleep(1)

    print("\n3. 验证日程页面已打开")
    result = wx.wait_for_text("新建日程", timeout=5)
    print(f"  找到: {result['text']}")

    print("\n4. 回到消息页面")
    wx.navigate_to("消息")
    time.sleep(1)

    print("\n5. 搜索功能测试")
    wx.click_text("搜索")
    time.sleep(0.5)
    wx.type_text("测试")
    time.sleep(1)

    # 查看搜索结果
    items = wx.ocr_scan()
    for item in items:
        if "测试" in item["text"] or "搜索" in item["text"]:
            print(f"  [{item['confidence']:.2f}] \"{item['text']}\"")

    wx.press_escape()
    time.sleep(0.5)

    print("\n=== 所有基础操作验证成功 ===")


if __name__ == "__main__":
    main()