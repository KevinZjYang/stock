#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
调试API返回数据格式
"""

import requests
import json

def debug_api_response():
    # 测试API响应
    api_url = 'https://stock.xueqiu.com/v5/stock/realtime/quotec.json'
    
    # 测试股票代码
    test_symbol = '000001'
    
    # 获取雪球市场前缀
    if test_symbol.startswith(('SH', 'SZ', 'HK', 'US')):
        xueqiu_symbol = test_symbol
    elif len(test_symbol) == 6 and test_symbol.isdigit():
        if test_symbol.startswith('6'):
            xueqiu_symbol = f"SH{test_symbol}"
        else:
            xueqiu_symbol = f"SZ{test_symbol}"
    elif len(test_symbol) == 5 and test_symbol.isdigit():
        xueqiu_symbol = test_symbol
    else:
        xueqiu_symbol = test_symbol
    
    params = {"symbol": xueqiu_symbol}
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Cookie': 'xq_a_token=;'
    }
    
    try:
        response = requests.get(api_url, params=params, headers=headers, timeout=10)
        print(f"API响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("API返回的完整数据:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            
            if 'data' in data and 'items' in data['data']:
                items = data['data']['items']
                print(f"\n数据项数量: {len(items)}")
                
                for i, item in enumerate(items):
                    print(f"\n数据项 {i+1}:")
                    print(json.dumps(item, indent=2, ensure_ascii=False))
                    
                    # 检查关键字段
                    print(f"  symbol: {item.get('symbol', 'N/A')}")
                    print(f"  current: {item.get('current', 'N/A')}")
                    print(f"  chg: {item.get('chg', 'N/A')}")
                    print(f"  percent: {item.get('percent', 'N/A')}")
            else:
                print("未找到数据项")
        else:
            print(f"API请求失败: {response.text}")
            
    except Exception as e:
        print(f"请求失败: {e}")

if __name__ == "__main__":
    debug_api_response()