#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试股票API数据获取
"""

import requests
import json

def test_api_call():
    # 测试API调用
    api_url = 'https://stock.xueqiu.com/v5/stock/realtime/quotec.json'
    
    # 测试港股代码
    test_symbol = '01810'  # 小米集团-W
    
    # 根据雪球规则转换代码
    if len(test_symbol) == 5 and test_symbol.isdigit():
        # 港股代码通常是5位数字，直接使用
        xueqiu_symbol = test_symbol
    else:
        xueqiu_symbol = test_symbol
    
    params = {"symbol": xueqiu_symbol}
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Cookie': 'xq_a_token=;'  # 可能需要有效的token
    }
    
    try:
        print(f"请求参数: {params}")
        response = requests.get(api_url, params=params, headers=headers, timeout=10)
        print(f"API响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("API返回的完整数据:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            
            if 'data' in data and data['data']:
                items = data['data']
                print(f"\n返回 {len(items)} 个数据项:")
                
                for item in items:
                    print(f"  Symbol: {item.get('symbol', 'N/A')}")
                    print(f"  Current: {item.get('current', 'N/A')}")
                    print(f"  Chg: {item.get('chg', 'N/A')}")
                    print(f"  Percent: {item.get('percent', 'N/A')}")
                    print(f"  Name: {item.get('name', 'N/A')}")
                    print("---")
            else:
                print("未找到有效数据")
        else:
            print(f"API请求失败: {response.text}")
            
    except Exception as e:
        print(f"请求失败: {e}")

if __name__ == "__main__":
    test_api_call()