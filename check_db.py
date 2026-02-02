#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sqlite3
import os

# 获取数据库路径
DATABASE_PATH = os.path.join('data', 'stock_fund.db')

print(f"数据库路径: {os.path.abspath(DATABASE_PATH)}")

if not os.path.exists(DATABASE_PATH):
    print("数据库文件不存在!")
else:
    print("数据库文件存在")
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # 检查表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"数据库中的表: {[table[0] for table in tables]}")
    
    # 检查基金关注列表
    cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='fund_watchlist';")
    table_exists = cursor.fetchone()[0]
    if table_exists:
        print("fund_watchlist 表存在")
        
        # 查询基金关注列表内容
        cursor.execute('SELECT * FROM fund_watchlist')
        rows = cursor.fetchall()
        print(f'fund_watchlist 表中的基金数量: {len(rows)}')
        print('fund_watchlist 表中的基金:')
        for row in rows:
            print(f'  ID: {row[0]}, 代码: {row[1]}')
    else:
        print("fund_watchlist 表不存在")
    
    conn.close()