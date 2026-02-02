#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
详细测试版本检查功能，包括GitHub API回退逻辑
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_github_api_fallback():
    """测试GitHub API回退逻辑"""
    import requests
    from modules.update_system import get_setting, set_setting
    
    print("测试GitHub API回退逻辑...")
    
    repo_owner = "KevinZjYang"
    repo_name = "stock"
    
    # 测试获取最新提交
    repo_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/commits/main"
    print(f"请求URL: {repo_url}")
    
    try:
        response = requests.get(repo_url, timeout=10)
        print(f"HTTP状态码: {response.status_code}")
        
        if response.status_code == 200:
            remote_data = response.json()
            remote_commit_sha = remote_data.get('sha', '')[:8]  # 获取前8位作为版本标识
            print(f"远程提交SHA: {remote_commit_sha}")
            
            # 检查本地是否有记录的最新远程commit SHA
            last_remote_commit = get_setting('last_remote_commit', '')
            print(f"上次记录的远程提交SHA: {last_remote_commit}")
            
            # 比较远程commit SHA与本地记录的SHA
            has_update = remote_commit_sha != last_remote_commit
            print(f"基于提交SHA判断是否有更新: {has_update}")
        else:
            print(f"GitHub API请求失败: {response.text}")
            
    except Exception as e:
        print(f"GitHub API请求过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

def test_version_file_directly():
    """直接测试版本文件获取"""
    import requests
    
    print("\n直接测试版本文件获取...")
    
    repo_owner = "KevinZjYang"
    repo_name = "stock"
    
    # 测试直接请求版本文件
    version_url = f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/main/VERSION"
    print(f"请求URL: {version_url}")
    
    # 添加headers以避免某些CDN缓存问题
    headers = {
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache'
    }
    
    try:
        response = requests.get(version_url, timeout=10, headers=headers)
        print(f"HTTP状态码: {response.status_code}")
        print(f"响应头: {dict(response.headers)}")
        
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
                
                return local_version, remote_version, has_update
            else:
                print("本地VERSION文件不存在")
                return None, None, None
        else:
            print(f"请求失败: {response.text}")
            return None, None, None
            
    except Exception as e:
        print(f"请求过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None

def simulate_original_problem():
    """模拟原始问题场景"""
    print("\n模拟原始问题场景...")
    print("假设之前本地版本是 0.1.0 或更低，远程版本是 0.1.1")
    
    from modules.update_system import compare_versions
    
    # 模拟旧场景
    old_local_versions = ["0.1.0", "0.0.9", "0.1.1"]
    remote_version = "0.1.1"
    
    for local_ver in old_local_versions:
        has_update = compare_versions(local_ver, remote_version)
        print(f"  本地版本 {local_ver} vs 远程版本 {remote_version} -> 需要更新: {has_update}")
    
    print("\n当前状态：")
    print(f"  本地版本: 0.1.2")
    print(f"  远程版本: 0.1.2 (根据curl)")
    
    # 测试当前状态
    current_local = "0.1.2"
    current_remote = "0.1.2"  # 假设真实远程版本是0.1.2
    has_update = compare_versions(current_local, current_remote)
    print(f"  当前比较结果: 需要更新: {has_update}")

if __name__ == "__main__":
    print("开始详细测试版本检查功能...\n")
    
    local_ver, remote_ver, update_needed = test_version_file_directly()
    test_github_api_fallback()
    simulate_original_problem()
    
    print(f"\n总结:")
    print(f"- 本地版本: {local_ver or '未知'}")
    print(f"- 远程版本: {remote_ver or '未知'}")
    print(f"- 需要更新: {update_needed if update_needed is not None else '未知'}")
    print(f"- 当前应该是最新版本")