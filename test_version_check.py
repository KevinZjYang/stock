#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试版本检查功能
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_check_for_updates():
    """测试检查更新功能"""
    try:
        from modules.update_system import check_for_updates
        
        print("调用 check_for_updates()...")
        result = check_for_updates()
        
        print(f"检查结果: {result}")
        
        if 'has_update' in result:
            print(f"是否有更新: {result['has_update']}")
            print(f"当前版本: {result['current_version']}")
            print(f"远程版本: {result['remote_version']}")
            print(f"消息: {result['message']}")
            
            return True
        else:
            print("返回结果缺少必要字段")
            return result.get('has_update', False)  # 即使缺少字段，也返回has_update的值
            
    except Exception as e:
        print(f"检查更新时发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_manual_version_request():
    """手动测试版本请求"""
    import requests
    
    print("\n手动测试版本请求...")
    
    repo_owner = "KevinZjYang"
    repo_name = "stock"
    
    # 测试直接请求版本文件
    version_url = f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/main/VERSION"
    print(f"请求URL: {version_url}")
    
    try:
        response = requests.get(version_url, timeout=10)
        print(f"HTTP状态码: {response.status_code}")
        
        if response.status_code == 200:
            remote_version = response.text.strip()
            print(f"远程版本: '{remote_version}'")
            
            # 读取本地版本
            local_version_file = os.path.join(os.getcwd(), 'VERSION')
            if os.path.exists(local_version_file):
                with open(local_version_file, 'r', encoding='utf-8') as f:
                    local_version = f.read().strip()
                print(f"本地版本: '{local_version}'")
                
                # 使用比较函数
                from modules.update_system import compare_versions
                has_update = compare_versions(local_version, remote_version)
                print(f"需要更新: {has_update}")
            else:
                print("本地VERSION文件不存在")
        else:
            print(f"请求失败: {response.text}")
            
    except Exception as e:
        print(f"请求过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("开始测试版本检查功能...\n")
    
    success1 = test_manual_version_request()
    success2 = test_check_for_updates()
    
    print(f"\n手动请求测试: {'成功' if success1 else '失败'}")
    print(f"完整功能测试: {'成功' if success2 else '失败'}")
    
    if success1 and success2:
        print("\n√ 版本检查功能正常")
    else:
        print("\nx 版本检查功能存在问题")