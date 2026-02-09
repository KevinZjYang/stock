# app.py
import os
from flask import Flask, render_template, jsonify, request
from datetime import datetime, timedelta
import threading
import json
import sqlite3
import pandas as pd
import requests
import time
from collections import deque
from typing import List, Dict, Any, Optional
import logging

# ==================== 数据库初始化 ====================
# 从 models 模块导入数据库初始化函数
from modules.models import (
    init_db, update_database_structure, finalize_database_structure, load_excel_data_to_db,
    check_if_needs_update, check_if_final_structure_needed, check_if_excel_needs_import,
    get_db_connection, app_logger
)

# ==================== 工具函数 ====================
# 从 models 模块导入工具函数
from modules.models import get_market_type, get_xueqiu_market_prefix, excel_date_to_str, normalize_stock_code

# ==================== 数据服务函数 ====================
# 从 models 模块导入数据服务函数
from modules.models import (
    load_stock_watchlist, add_stock_to_watchlist, remove_stock_from_watchlist,
    search_stock_by_code, get_stock_realtime_data, get_stock_realtime_data_batch,
    normalize_stock_code
)

# ==================== 指数管理功能 ====================
# 从 models 模块导入指数管理函数
from modules.models import (
    load_index_watchlist, add_index_to_watchlist, remove_index_from_watchlist,
    fetch_fund_price_batch_sync
)


# 从 models 模块导入基金交易相关函数
from modules.models import (
    load_fund_transactions, add_fund_transaction, update_fund_transaction,
    delete_fund_transaction, clear_all_fund_transactions,
    import_excel_transactions, export_excel_transactions
)

# 标记是否已初始化
_initialized = False

def initialize_app():
    global _initialized
    if _initialized:
        return

    # 初始化数据库
    init_db()
    app_logger.info("数据库初始化完成")

    # 更新数据库结构
    update_database_structure()

    # 完成数据库结构调整
    finalize_database_structure()


    # 将Excel数据导入数据库
    load_excel_data_to_db()

    _initialized = True

app = Flask(__name__)

# 在应用上下文中执行初始化
with app.app_context():
    initialize_app()

# ==================== 主页面路由 ====================
@app.route('/')
def index():
    return render_template('master.html')


# 注册API蓝图
try:
    from modules.stock_module import stock_bp
    app.register_blueprint(stock_bp, url_prefix='/api/stock')
    print("Successfully imported stock_module blueprint")
except ImportError as e:
    print(f"Warning: Could not import stock_module blueprint: {e}")

try:
    from modules.fund import fund_bp
    app.register_blueprint(fund_bp, url_prefix='/api/fund')
    print("Successfully imported fund blueprint")
except ImportError as e:
    print(f"Warning: Could not import fund blueprint: {e}")

try:
    from modules.fund_trans import fund_trans_bp
    app.register_blueprint(fund_trans_bp, url_prefix='/api/fund_trans')
    print("Successfully imported fund_trans blueprint")
except ImportError as e:
    print(f"Warning: Could not import fund_trans blueprint: {e}")

try:
    from modules.log import log_bp
    app.register_blueprint(log_bp, url_prefix='/api/log')
    print("Successfully imported log blueprint")
except ImportError as e:
    print(f"Warning: Could not import log blueprint: {e}")

try:
    from modules.notify import notify_bp
    app.register_blueprint(notify_bp)
    print("Successfully imported notify blueprint")
except ImportError as e:
    print(f"Warning: Could not import notify blueprint: {e}")

# 注册页面路由
try:
    from modules.stock_module import stock_page
    app.add_url_rule('/stock_page', 'stock_page', stock_page)
    print("Successfully imported stock_page route")
except ImportError as e:
    print(f"Warning: Could not import stock_page route: {e}")

try:
    from modules.fund import fund_page
    app.add_url_rule('/fund_page', 'fund_page', fund_page)
    print("Successfully imported fund_page route")
except ImportError as e:
    print(f"Warning: Could not import fund_page route: {e}")

try:
    from modules.fund_trans import fund_trans_page
    app.add_url_rule('/fund_trans_page', 'fund_trans_page', fund_trans_page)
    print("Successfully imported fund_trans_page route")
except ImportError as e:
    print(f"Warning: Could not import fund_trans_page route: {e}")

try:
    from modules.notify import notification_page
    app.add_url_rule('/notification_page', 'notification_page', notification_page)
    print("Successfully imported notification_page route")
except ImportError as e:
    print(f"Warning: Could not import notification_page route: {e}")


# ==================== 更新功能路由 ====================
try:
    from modules.update_system import check_for_updates, perform_update, restart_application, perform_safe_update

    @app.route('/api/update/check', methods=['GET'])
    def api_check_update():
        """检查是否有更新"""
        result = check_for_updates()
        return jsonify(result)

    @app.route('/api/update/perform', methods=['POST'])
    def api_perform_update():
        """执行更新"""
        result = perform_safe_update()  # 使用安全更新函数
        return jsonify(result)

    @app.route('/api/update/restart', methods=['POST'])
    def api_restart_app():
        """重启应用"""
        result = restart_application()
        return jsonify(result)

    @app.route('/update')
    def update_page():
        """更新页面"""
        return render_template('update.html')

except ImportError as e:
    print(f"Warning: Could not import update functions: {e}")


# ==================== 基金缓存定时任务 ====================
try:
    from modules.fund_trans import start_cache_scheduler
    cache_scheduler = start_cache_scheduler()
    print("Successfully started fund cache scheduler")
except ImportError as e:
    print(f"Warning: Could not start fund cache scheduler: {e}")


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=3333)
