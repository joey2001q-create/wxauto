# -*- coding: utf-8 -*-
"""
企业微信自动化 v1.2 - 批量测试手机号

测试数据:
- 16670239176: 存在（已验证）
- 13611111111: 不存在（已验证）
- 13611111122: 未知
- 13682416565: 未知
"""

from wxwork_auto import WXWorkAutomation
import json


def main():
    wx = WXWorkAutomation(ocr_confidence=0.8, action_delay=0.3)

    # 测试手机号列表
    phones = [
        "16670239176",    # 存在
        "13611111111",    # 不存在
        "13611111122",    # 未知
        "13682416565"     # 未知
    ]

    verify_msg = "你好"

    print("=" * 50)
    print("企业微信自动化 v1.2 - 批量测试手机号")
    print("=" * 50)
    print()

    # 执行批量测试
    results = wx.test_phones_batch(phones, verify_msg, interval=3)

    # 打印统计
    print()
    print("=" * 50)
    print("测试结果统计")
    print("=" * 50)
    summary = results["summary"]
    print(f"  总数: {summary['total']}")
    print(f"  存在: {summary['exists']}")
    print(f"  不存在: {summary['not_exist']}")
    print(f"  已是好友: {summary['already_friend']}")
    print(f"  失败: {summary['failed']}")
    print()

    # 打印分类结果
    print("存在的手机号:")
    for phone in results["exists"]:
        print(f"  - {phone}")

    print()
    print("不存在的手机号:")
    for phone in results["not_exist"]:
        print(f"  - {phone}")

    if results["already_friend"]:
        print()
        print("已是好友的手机号:")
        for phone in results["already_friend"]:
            print(f"  - {phone}")

    if results["failed"]:
        print()
        print("失败的手机号:")
        for phone in results["failed"]:
            print(f"  - {phone}")

    # 保存不存在的手机号到文件
    print()
    print("=" * 50)
    filepath = wx.save_not_exist_phones(results, "not_exist_phones.txt")
    print("=" * 50)

    # 保存完整结果到 JSON
    with open("batch_test_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"完整结果已保存到 batch_test_results.json")

    print()
    print("测试完成！")


if __name__ == "__main__":
    main()
