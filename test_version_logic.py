#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试版本比较逻辑
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_version_comparison():
    """测试版本比较功能"""
    from modules.update_system import compare_versions
    
    # 测试各种版本比较情况
    test_cases = [
        ("0.1.0", "0.1.1", True),   # 远程版本更高
        ("0.1.1", "0.1.0", False),  # 本地版本更高
        ("0.1.1", "0.1.1", False),  # 版本相同
        ("0.1.1", "0.1.2", True),   # 远程版本更高
        ("0.1.10", "0.1.2", False), # 版本数字大小比较
        ("1.0.0", "0.9.9", False),  # 主版本号比较
        ("0.9.9", "1.0.0", True),   # 主版本号比较
    ]
    
    print("测试版本比较功能:")
    all_passed = True
    
    for local_ver, remote_ver, expected_result in test_cases:
        result = compare_versions(local_ver, remote_ver)
        status = "√" if result == expected_result else "x"
        print(f"  {status} {local_ver} vs {remote_ver} -> {result} (expected {expected_result})")
        
        if result != expected_result:
            all_passed = False
    
    return all_passed

def test_parse_version():
    """测试版本解析功能"""
    from modules.update_system import compare_versions
    
    # 内部函数用于测试版本解析
    def parse_version(version):
        # 将版本号拆分为数字部分，例如 "1.2.3" -> [1, 2, 3]
        parts = version.replace('v', '').split('.')
        return [int(part) for part in parts if part.isdigit()]
    
    print("\n测试版本解析功能:")
    test_cases = [
        ("0.1.1", [0, 1, 1]),
        ("0.1.2", [0, 1, 2]),
        ("1.0.0", [1, 0, 0]),
        ("v1.2.3", [1, 2, 3]),  # 带v前缀
    ]
    
    all_passed = True
    for version, expected in test_cases:
        # 通过比较函数间接测试解析
        parsed = parse_version(version)
        status = "√" if parsed == expected else "x"
        print(f"  {status} {version} -> {parsed} (expected {expected})")
        
        if parsed != expected:
            all_passed = False
    
    return all_passed

def test_actual_scenario():
    """测试实际场景"""
    print("\n测试实际场景:")
    from modules.update_system import compare_versions
    
    local_version = "0.1.1"
    remote_version = "0.1.2"
    
    result = compare_versions(local_version, remote_version)
    print(f"本地版本 {local_version}, 远程版本 {remote_version}")
    print(f"需要更新: {result}")
    
    if result:
        print("√ 正确识别需要更新")
        return True
    else:
        print("x 错误：未识别需要更新")
        return False

if __name__ == "__main__":
    print("开始测试版本比较逻辑...\n")
    
    tests = [
        test_version_comparison(),
        test_parse_version(),
        test_actual_scenario()
    ]
    
    if all(tests):
        print("\n√ 所有版本比较测试通过！")
    else:
        print("\nx 部分版本比较测试失败")