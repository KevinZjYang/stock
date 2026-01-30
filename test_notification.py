#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
价格通知功能测试脚本
"""

import sqlite3
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import (
    get_price_notifications,
    get_stock_realtime_data_batch,
    check_price_notifications,
    add_price_notification,
    get_webhook_url,
    send_wechat_work_message
)

def test_notification_system():
    print("=== 价格通知系统测试 ===\n")
    
    # 1. 检查通知条件
    print("1. 检查当前通知条件:")
    notifications = get_price_notifications()
    print(f"   找到 {len(notifications)} 个待检查的通知条件")
    for n in notifications:
        print(f"   - ID: {n['id']}, 股票: {n['symbol']} ({n['name']}), 条件: {n['condition_type']}, 阈值: {n['threshold_value']}")
    print()
    
    # 2. 检查webhook设置
    print("2. 检查webhook设置:")
    webhook_url = get_webhook_url()
    print(f"   Webhook URL: {'已设置' if webhook_url else '未设置'}")
    if webhook_url:
        print(f"   URL: {webhook_url[:50]}...")
    print()
    
    # 3. 获取实时数据测试
    if notifications:
        print("3. 获取实时数据测试:")
        symbols = list(set([n['symbol'] for n in notifications]))
        print(f"   需要获取数据的股票: {symbols}")
        
        try:
            price_data_list = get_stock_realtime_data_batch(symbols)
            print(f"   成功获取 {len(price_data_list)} 个股票的实时数据")
            
            for data in price_data_list:
                print(f"   - {data.get('symbol', 'N/A')}: 价格={data.get('current', 0)}, 涨跌额={data.get('chg', 0)}, 涨跌幅={data.get('percent', 0)}%")
        except Exception as e:
            print(f"   获取实时数据失败: {e}")
        print()
    
    # 4. 手动触发检查（忽略交易时间）
    print("4. 手动触发价格通知检查（忽略交易时间限制）:")
    try:
        check_price_notifications(trading_hours_only=False)
        print("   检查完成")
    except Exception as e:
        print(f"   检查过程中出现错误: {e}")
    print()
    
    # 5. 重新检查通知状态
    print("5. 检查通知状态变化:")
    updated_notifications = get_price_notifications()
    print(f"   剩余待检查的通知条件: {len(updated_notifications)}")
    for n in updated_notifications:
        print(f"   - ID: {n['id']}, 股票: {n['symbol']} ({n['name']}), 条件: {n['condition_type']}, 阈值: {n['threshold_value']}")
    print()
    
    if len(updated_notifications) < len(notifications):
        print("v 有通知条件已被触发并移除")
    else:
        print("! 所有通知条件仍在等待中，可能是因为价格条件未满足")
    
    print("\n=== 测试完成 ===")

if __name__ == "__main__":
    test_notification_system()