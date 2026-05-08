# -*- coding: utf-8 -*-
"""
企业微信自动化 v1.2 - 健壮性测试

测试目标：
1. 多次运行，验证稳定性
2. 打乱顺序，验证适应性
3. 记录每次结果，对比一致性
"""

from wxwork_auto import WXWorkAutomation
import random
import json
import time


def test_with_order(wx, phones, order_name):
    """测试指定顺序"""
    print(f"\n{'='*50}")
    print(f"测试顺序: {order_name}")
    print(f"号码列表: {phones}")
    print('='*50)

    results = wx.test_phones_batch(phones, verify_msg="你好", interval=2)

    # 简化输出
    print(f"\n结果:")
    print(f"  存在: {results['exists']}")
    print(f"  不存在: {results['not_exist']}")
    print(f"  已是好友: {results['already_friend']}")
    print(f"  失败: {results['failed']}")

    return results


def main():
    wx = WXWorkAutomation(ocr_confidence=0.8, action_delay=0.3)

    # 测试号码
    phones = [
        "16670239176",    # 存在
        "13611111111",    # 不存在
        "13611111122",    # 不存在
        "13682416565"     # 存在
    ]

    all_results = []

    # 测试1: 原始顺序
    r1 = test_with_order(wx, phones[:], "原始顺序")
    all_results.append({"order": "original", "phones": phones[:], "result": r1})
    time.sleep(3)

    # 测试2: 完全逆序
    reversed_phones = phones[::-1]
    r2 = test_with_order(wx, reversed_phones, "完全逆序")
    all_results.append({"order": "reversed", "phones": reversed_phones, "result": r2})
    time.sleep(3)

    # 测试3: 随机打乱1
    random.seed(42)
    shuffled1 = phones[:]
    random.shuffle(shuffled1)
    r3 = test_with_order(wx, shuffled1, "随机打乱1")
    all_results.append({"order": "shuffled1", "phones": shuffled1, "result": r3})
    time.sleep(3)

    # 测试4: 随机打乱2
    random.seed(123)
    shuffled2 = phones[:]
    random.shuffle(shuffled2)
    r4 = test_with_order(wx, shuffled2, "随机打乱2")
    all_results.append({"order": "shuffled2", "phones": shuffled2, "result": r4})
    time.sleep(3)

    # 测试5: 交替顺序 (存在, 不存在, 存在, 不存在)
    alternate = ["16670239176", "13611111111", "13682416565", "13611111122"]
    r5 = test_with_order(wx, alternate, "交替顺序")
    all_results.append({"order": "alternate", "phones": alternate, "result": r5})

    # 汇总分析
    print(f"\n{'='*50}")
    print("汇总分析")
    print('='*50)

    # 检查一致性
    expected_exists = {"16670239176", "13682416565"}
    expected_not_exist = {"13611111111", "13611111122"}

    all_consistent = True
    for test in all_results:
        exists = set(test["result"]["exists"])
        not_exist = set(test["result"]["not_exist"])

        consistent = (exists == expected_exists and not_exist == expected_not_exist)
        status = "✓" if consistent else "✗"
        print(f"{status} {test['order']}: 存在={len(exists)}, 不存在={len(not_exist)}")

        if not consistent:
            all_consistent = False
            print(f"    期望存在: {expected_exists}, 实际: {exists}")
            print(f"    期望不存在: {expected_not_exist}, 实际: {not_exist}")

    print(f"\n{'='*50}")
    if all_consistent:
        print("✓ 所有测试结果一致，健壮性良好！")
    else:
        print("✗ 存在不一致结果，需要检查")
    print('='*50)

    # 保存详细结果
    with open("robustness_test_results.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存到 robustness_test_results.json")


if __name__ == "__main__":
    main()
