# -*- coding: utf-8 -*-
"""
企业微信自动化 - 通过手机号添加联系人

改进版：
  - 支持验证消息
  - 自动判断添加结果（成功/已是好友/未找到/失败）
  - 支持批量添加
"""

from wxwork_auto import WXWorkAutomation
import time


def add_single():
    """单个添加联系人"""
    wx = WXWorkAutomation(ocr_confidence=0.8, action_delay=0.3)

    phone = "16670239176"
    result = wx.add_contact_by_phone(phone, verify_msg="你好，我是XX")

    print(f"手机号: {phone}")
    print(f"状态: {result['status']}")
    print(f"详情: {result['detail']}")


def add_batch():
    """批量添加联系人"""
    wx = WXWorkAutomation(ocr_confidence=0.8, action_delay=0.3)

    phones = [
        "16670239176",
        "13800138000",
    ]
    results = wx.add_contacts_batch(phones, verify_msg="你好，我是XX", interval=3)

    print("\n=== 批量添加结果 ===")
    for r in results:
        print(f"  {r['phone']}: {r['status']} - {r['detail']}")


if __name__ == "__main__":
    add_single()
    # add_batch()
