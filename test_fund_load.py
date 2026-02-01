#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
测试基金基础数据加载功能
"""

import sys
import os
import requests
import sqlite3

# 添加项目路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入必要的模块
from app import get_db_connection, app_logger

def load_all_funds_to_db_test():
    """测试版本的基金基础数据加载函数"""
    try:
        print("开始获取所有基金基础数据...")
        print("API URL: https://api.autostock.cn/v1/fund/all")

        # 添加更多调试信息
        response = requests.get('https://api.autostock.cn/v1/fund/all', timeout=30)
        print(f"HTTP状态码: {response.status_code}")

        if response.status_code != 200:
            print(f"HTTP请求失败，状态码: {response.status_code}")
            return False

        print(f"响应内容长度: {len(response.content)}")

        try:
            data = response.json()
            print(f"JSON解析成功，响应代码: {data.get('code', 'N/A')}")
        except Exception as json_error:
            print(f"JSON解析失败: {json_error}")
            print(f"原始响应内容: {response.text[:500]}...")
            return False

        if data.get('code') != 200:
            print(f"获取基金基础数据失败: {data.get('message', '未知错误')}")
            return False

        funds_data = data.get('data', [])
        if not funds_data:
            print("获取到的基金数据为空")
            return False

        print(f"获取到 {len(funds_data)} 条基金数据")

        conn = get_db_connection()
        cursor = conn.cursor()

        # 创建基金基础数据表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fund_base_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                pinyin TEXT,
                name TEXT,
                type TEXT,
                full_pinyin TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 插入或更新基金数据
        inserted_count = 0
        for fund in funds_data:
            if len(fund) >= 5:  # 确保有足够的字段
                code = fund[0]
                pinyin = fund[1]
                name = fund[2]
                fund_type = fund[3]
                full_pinyin = fund[4]

                try:
                    cursor.execute('''
                        INSERT OR REPLACE INTO fund_base_data
                        (code, pinyin, name, type, full_pinyin)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (code, pinyin, name, fund_type, full_pinyin))
                    inserted_count += 1
                    if inserted_count % 1000 == 0:  # 每1000条记录打印一次进度
                        print(f"已处理 {inserted_count} 条记录...")
                except Exception as e:
                    print(f"插入基金数据失败 {code}: {e}")

        conn.commit()
        conn.close()

        print(f"成功获取并保存 {inserted_count} 条基金基础数据")
        return True

    except Exception as e:
        print(f"获取基金基础数据时发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("开始测试基金基础数据加载...")
    success = load_all_funds_to_db_test()
    print(f"测试结果: {'成功' if success else '失败'}")

    # 检查数据库中的记录数
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM fund_base_data')
    count = cursor.fetchone()[0]
    print(f"数据库中fund_base_data表的记录数: {count}")
    conn.close()