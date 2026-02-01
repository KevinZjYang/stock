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

# ==================== 配置 ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 数据库路径
DATABASE_PATH = os.path.join(BASE_DIR, 'data', 'stock_fund.db')

# 数据文件路径
STOCK_DATA_FILE = os.path.join(BASE_DIR, 'data', 'code.xlsx')

# 缓存配置
CACHE_EXPIRY = 300  # 缓存过期时间（秒），5分钟

# 日志配置
LOG_DIR = os.path.join(BASE_DIR, 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'app.log')

# 确保数据目录存在
os.makedirs(os.path.dirname(STOCK_DATA_FILE), exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# API配置
STOCK_API_URL = 'https://stock.xueqiu.com/v5/stock/realtime/quotec.json'
FUND_BATCH_API_URL = 'https://api.autostock.cn/v1/fund/detail/list'

# ==================== 数据库初始化 ====================
# 从 models 模块导入数据库初始化函数
from modules.models import init_db, update_database_structure, finalize_database_structure, load_excel_data_to_db

# ==================== 日志系统 ====================
import logging.handlers

# 确保日志目录存在
os.makedirs(LOG_DIR, exist_ok=True)

# 全局日志存储
MAX_LOGS = 1000
log_storage = deque(maxlen=MAX_LOGS)
log_lock = threading.Lock()

class MemoryLogHandler(logging.Handler):
    """自定义日志处理器，将日志存入内存"""
    def emit(self, record):
        try:
            # 检查是否在请求上下文中
            try:
                page = request.path if request else "System"
            except RuntimeError:
                # 如果不在请求上下文中，使用默认值
                page = "System"

            func_name = getattr(record, 'funcName', '')
            module_name = getattr(record, 'module', '')

            log_entry = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'page': page,
                'function': func_name,
                'module': module_name,
                'level': record.levelname,
                'message': record.getMessage(),
                'lineno': getattr(record, 'lineno', 0)
            }

            with log_lock:
                log_storage.append(log_entry)
        except Exception as e:
            # 记录内部错误
            print(f"MemoryLogHandler内部错误: {e}")

# 配置日志记录器
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 创建文件日志处理器，按天轮转
file_handler = logging.handlers.TimedRotatingFileHandler(
    LOG_FILE,
    when="midnight",
    interval=1,
    backupCount=30,  # 保留30天的日志
    encoding='utf-8'
)
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO)

# 创建内存日志处理器
memory_handler = MemoryLogHandler()

# 创建控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)

# 获取根日志记录器并配置处理器
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# 清除任何已有的处理器，避免重复
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# 添加我们的处理器
root_logger.addHandler(file_handler)
root_logger.addHandler(memory_handler)
root_logger.addHandler(console_handler)

app_logger = logging.getLogger(__name__)

def get_logs():
    """获取所有日志"""
    with log_lock:
        return list(log_storage)

def clear_logs():
    """清空日志"""
    with log_lock:
        log_storage.clear()

# ==================== 数据库操作函数 ====================
def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # 使结果可以通过列名访问
    return conn

def check_if_needs_update():
    """检查是否需要更新数据库结构"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # 检查是否存在market_name列
        cursor.execute("PRAGMA table_info(stocks)")
        columns = [column[1] for column in cursor.fetchall()]

        # 如果存在market_name列，说明已经更新过了
        needs_update = 'market_name' not in columns
        return needs_update
    except Exception as e:
        app_logger.error(f"检查数据库结构更新状态失败: {e}")
        return True  # 出错时默认需要更新
    finally:
        conn.close()

def update_database_structure():
    """更新数据库结构和数据"""
    if not check_if_needs_update():
        app_logger.info("数据库结构已是最新，无需更新")
        return

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # 检查是否存在market_name列
        cursor.execute("PRAGMA table_info(stocks)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'market_name' not in columns:
            # 添加market_name列
            cursor.execute('ALTER TABLE stocks ADD COLUMN market_name TEXT')
            app_logger.info("添加market_name列到stocks表")

        # 如果存在sheet_name列，将其值复制到market_name
        if 'sheet_name' in columns:
            cursor.execute('UPDATE stocks SET market_name = sheet_name WHERE market_name IS NULL OR market_name = ""')

        # 创建临时表来存储更新后的数据
        cursor.execute('''
            CREATE TEMPORARY TABLE temp_stocks AS
            SELECT * FROM stocks
        ''')

        # 清空原表
        cursor.execute('DELETE FROM stocks')

        # 读取临时表数据并规范化后重新插入
        cursor.execute('SELECT id, code, name, market_name FROM temp_stocks')
        rows = cursor.fetchall()

        for row in rows:
            stock_id = row[0]
            code = row[1]
            name = row[2]
            market_name = row[3]

            # 提取交易所后缀
            market_type = ''
            if '.' in code:
                suffix = code.split('.')[-1].upper()
                if suffix in ['SH', 'SZ', 'HK', 'US']:
                    market_type = suffix  # 保存交易所后缀
                else:
                    market_type = 'OTHER'
            else:
                # 对于没有后缀的代码，根据代码特征推断
                if code.startswith('6'):
                    market_type = 'SH'  # SH
                elif len(code) == 5 and code.isdigit():
                    market_type = 'HK'  # HK
                elif len(code) == 6 and code.isdigit():
                    market_type = 'SZ'  # SZ
                else:
                    market_type = 'OTHER'

            # 根据market_name确定市场类型，用于代码标准化
            sheet_market_type = ''
            if market_name in ['A股', '大盘指数']:
                sheet_market_type = 'A股'
            elif market_name == '港股':
                sheet_market_type = '港股'
            elif market_name == '美股':
                sheet_market_type = '美股'

            # 标准化代码
            normalized_code = normalize_stock_code(code, sheet_market_type)

            # 插入规范化后的数据
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO stocks (id, code, name, market_type, market_name)
                    VALUES (?, ?, ?, ?, ?)
                ''', (stock_id, normalized_code, name, market_type, market_name))
            except sqlite3.IntegrityError:
                # 如果遇到唯一性约束错误，跳过该记录
                app_logger.warning(f"跳过重复代码: {normalized_code}")
                continue

        conn.commit()
        app_logger.info("数据库结构和数据更新完成")

    except Exception as e:
        app_logger.error(f"更新数据库结构失败: {e}")
        conn.rollback()
    finally:
        conn.close()

def check_if_final_structure_needed():
    """检查是否需要完成数据库结构最终调整"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # 检查是否存在名为stocks_new的临时表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stocks_new'")
        temp_table_exists = cursor.fetchone() is not None

        # 检查stocks表是否已有预期的列结构
        cursor.execute("PRAGMA table_info(stocks)")
        columns = [column[1] for column in cursor.fetchall()]

        # 检查是否还存在旧的字段（如假设的sheet_name）
        # 由于我们不知道原来的字段名，我们可以检查当前表结构是否符合预期
        expected_columns = ['code', 'name', 'market_type', 'market_name']
        has_expected_columns = all(col in columns for col in expected_columns)

        # 如果没有临时表且已有预期列结构，则不需要调整
        needs_adjustment = temp_table_exists or not has_expected_columns
        return needs_adjustment
    except Exception as e:
        app_logger.error(f"检查数据库最终结构调整状态失败: {e}")
        return True  # 出错时默认需要调整
    finally:
        conn.close()

def finalize_database_structure():
    """完成数据库结构调整，删除旧的临时表（如果存在）"""
    if not check_if_final_structure_needed():
        app_logger.info("数据库结构已是最终形态，无需调整")
        return

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # 检查是否存在stocks_new临时表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stocks_new'")
        temp_table_exists = cursor.fetchone() is not None

        if temp_table_exists:
            # 删除旧表
            cursor.execute('DROP TABLE IF EXISTS stocks_old')

            # 重命名当前表为临时备份
            cursor.execute('ALTER TABLE stocks RENAME TO stocks_old')

            # 创建新表结构
            cursor.execute('''
                CREATE TABLE stocks_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    name TEXT,
                    market_type TEXT,
                    market_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 从旧表复制数据到新表
            cursor.execute('''
                INSERT INTO stocks_new (id, code, name, market_type, market_name, created_at)
                SELECT id, code, name, market_type, market_name, created_at
                FROM stocks_old
            ''')

            # 删除旧表
            cursor.execute('DROP TABLE stocks_old')

            # 重命名新表
            cursor.execute('ALTER TABLE stocks_new RENAME TO stocks')
        else:
            # 如果没有临时表，只需确保表结构正确
            # 检查并添加缺失的列
            cursor.execute("PRAGMA table_info(stocks)")
            existing_columns = [column[1] for column in cursor.fetchall()]

            if 'market_type' not in existing_columns:
                cursor.execute('ALTER TABLE stocks ADD COLUMN market_type TEXT')

            if 'market_name' not in existing_columns:
                cursor.execute('ALTER TABLE stocks ADD COLUMN market_name TEXT')

        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_stocks_code ON stocks(code)')

        conn.commit()
        app_logger.info("数据库结构最终调整完成")

    except Exception as e:
        app_logger.error(f"完成数据库结构调整失败: {e}")
        conn.rollback()
    finally:
        conn.close()



def check_if_excel_needs_import():
    """检查Excel文件是否需要导入（基于文件修改时间和数据库记录）"""
    if not os.path.exists(STOCK_DATA_FILE):
        return False

    # 获取Excel文件的修改时间
    excel_mtime = os.path.getmtime(STOCK_DATA_FILE)

    # 检查数据库中是否有导入时间记录
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 检查是否有导入时间记录
        cursor.execute("SELECT value FROM settings WHERE key = 'last_excel_import_time'")
        row = cursor.fetchone()

        if row:
            last_import_time = float(row['value'])
            # 如果Excel文件的修改时间比上次导入时间晚，则需要重新导入
            needs_import = excel_mtime > last_import_time
        else:
            # 如果没有导入记录，则需要导入
            needs_import = True

        return needs_import
    except Exception as e:
        app_logger.error(f"检查Excel导入状态失败: {e}")
        return True  # 出错时默认需要导入
    finally:
        conn.close()

def load_excel_data_to_db():
    """将Excel数据加载到数据库中"""
    if not os.path.exists(STOCK_DATA_FILE):
        app_logger.info("Excel数据文件不存在，跳过导入")
        return

    # 检查是否需要导入
    if not check_if_excel_needs_import():
        app_logger.info("Excel数据已是最新，跳过导入")
        return

    try:
        excel_file = pd.ExcelFile(STOCK_DATA_FILE)
        conn = get_db_connection()
        cursor = conn.cursor()

        total_imported = 0

        for sheet_name in excel_file.sheet_names:
            try:
                df = pd.read_excel(STOCK_DATA_FILE, sheet_name=sheet_name)
                if df.empty:
                    continue

                # 根据不同的sheet名称确定市场类型
                market_type = ''
                if sheet_name in ['A股', '大盘指数']:
                    market_type = 'SH'  # 默认A股使用SH
                elif sheet_name == '港股':
                    market_type = 'HK'
                elif sheet_name == '美股':
                    market_type = 'US'

                # 根据列名映射来获取代码和名称
                code_col = None
                name_col = None

                for col in df.columns:
                    if col.lower() in ['code', '代码', '股票代码']:
                        code_col = col
                    elif col.lower() in ['name', '名称', 'name(产品名称)', '股票名称']:
                        name_col = col

                if not code_col or not name_col:
                    app_logger.warning(f"Sheet '{sheet_name}' 中未找到代码或名称列")
                    continue

                for _, row in df.iterrows():
                    code = str(row[code_col]).strip()
                    name = str(row[name_col]).strip()

                    # 提取交易所后缀
                    original_code = code
                    clean_code = code.split('.')[0] if '.' in code else code
                    exchange_suffix = code.split('.')[-1].upper() if '.' in code else ''

                    # 根据后缀确定市场类型 - 现在market_type保存交易所后缀
                    final_market_type = exchange_suffix if exchange_suffix in ['SH', 'SZ', 'HK', 'US'] else ''

                    # 根据sheet_name确定市场类型，用于代码标准化
                    sheet_market_type = ''
                    if sheet_name in ['A股', '大盘指数']:
                        sheet_market_type = 'A股'
                    elif sheet_name == '港股':
                        sheet_market_type = '港股'
                    elif sheet_name == '美股':
                        sheet_market_type = '美股'

                    # 标准化代码
                    normalized_code = normalize_stock_code(code, sheet_market_type)

                    if normalized_code:  # 只有当代码存在时才插入
                        try:
                            cursor.execute('''
                                INSERT OR REPLACE INTO stocks (code, name, market_type, market_name)
                                VALUES (?, ?, ?, ?)
                            ''', (normalized_code, name, final_market_type, sheet_name))
                            total_imported += 1
                        except Exception as e:
                            app_logger.error(f"插入股票数据失败 {normalized_code}: {e}")

            except Exception as e:
                app_logger.error(f"读取Sheet '{sheet_name}' 失败: {e}")
                continue

        conn.commit()
        conn.close()

        # 记录导入时间
        excel_mtime = os.path.getmtime(STOCK_DATA_FILE)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', ('last_excel_import_time', str(excel_mtime)))
            conn.commit()
        except Exception as e:
            app_logger.error(f"记录Excel导入时间失败: {e}")
        finally:
            conn.close()

        app_logger.info(f"成功导入 {total_imported} 条股票数据到数据库")

    except Exception as e:
        app_logger.error(f"导入Excel数据到数据库失败: {e}")

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
    delete_fund_transaction, clear_all_fund_transactions, calculate_fund_summary,
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



# ==================== 基金模块路由 ====================
data_cache = {'funds': None, 'last_update': 0}

def load_fund_watchlist():
    """加载基金关注列表"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT code FROM fund_watchlist ORDER BY created_at')
    result = [row['code'] for row in cursor.fetchall()]
    conn.close()
    return result

# 从 models 模块导入设置相关函数
from modules.models import get_setting, set_setting

@app.route('/api/fund/settings', methods=['GET', 'POST'])
def manage_fund_settings():
    if request.method == 'GET':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT key, value FROM settings')
        rows = cursor.fetchall()
        settings = {}
        for row in rows:
            try:
                settings[row['key']] = json.loads(row['value'])
            except:
                settings[row['key']] = row['value']
        conn.close()
        app_logger.info("获取基金设置")
        return jsonify(settings)

    elif request.method == 'POST':
        data = request.get_json()
        if not data:
            app_logger.warning("尝试保存设置但缺少数据")
            return jsonify({'error': '缺少数据'}), 400

        for key, value in data.items():
            if not set_setting(key, value):
                app_logger.error("保存基金设置失败")
                return jsonify({'error': '保存设置失败'}), 500

        app_logger.info(f"保存基金设置成功: {data}")
        return jsonify({'success': True, 'settings': data})


@app.route('/api/fund/watchlist', methods=['GET', 'POST', 'DELETE'])
def manage_fund_watchlist():
    client_ip = request.remote_addr

    if request.method == 'GET':
        app_logger.info(f"获取基金关注列表请求来自: {client_ip}")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT code FROM fund_watchlist ORDER BY created_at')
        watchlist = [row['code'] for row in cursor.fetchall()]
        conn.close()
        app_logger.info(f"返回基金关注列表，共 {len(watchlist)} 个项目, IP: {client_ip}")
        return jsonify(watchlist)

    elif request.method == 'POST':
        app_logger.info(f"添加基金到关注列表请求来自: {client_ip}")
        data = request.get_json()
        if not data or 'code' not in data:
            app_logger.warning(f"添加基金关注列表失败: 缺少基金代码, IP: {client_ip}")
            return jsonify({'error': '缺少基金代码'}), 400

        code = data['code'].strip()
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO fund_watchlist (code) VALUES (?)', (code,))
            conn.commit()
            conn.close()
            data_cache['funds'] = None
            app_logger.info(f"成功添加基金到关注列表: {code}, IP: {client_ip}")

            # 返回更新后的列表
            watchlist = load_fund_watchlist()
            return jsonify({'watchlist': watchlist})
        except sqlite3.IntegrityError:
            conn.close()
            app_logger.warning(f"添加基金关注列表失败: {code} 已存在, IP: {client_ip}")
            return jsonify({'error': f'{code} 已在关注列表中'}), 400
        except Exception as e:
            conn.close()
            app_logger.error(f"添加基金关注列表失败, IP: {client_ip}, 错误: {e}")
            return jsonify({'error': '保存到服务器失败'}), 500

    elif request.method == 'DELETE':
        app_logger.info(f"从基金关注列表移除请求来自: {client_ip}")
        data = request.get_json()
        if not data or 'code' not in data:
            app_logger.warning(f"删除基金关注列表失败: 缺少基金代码, IP: {client_ip}")
            return jsonify({'error': '缺少基金代码'}), 400

        code = data['code'].strip()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM fund_watchlist WHERE code = ?', (code,))
        rows_affected = cursor.rowcount
        if rows_affected > 0:
            conn.commit()
            conn.close()
            data_cache['funds'] = None
            app_logger.info(f"成功从基金关注列表移除: {code}, IP: {client_ip}")

            # 返回更新后的列表
            watchlist = load_fund_watchlist()
            return jsonify({'watchlist': watchlist})
        else:
            conn.close()
            app_logger.warning(f"删除基金关注列表失败: {code} 不存在, IP: {client_ip}")
            return jsonify({'error': f'{code} 不在关注列表中'}), 400

@app.route('/api/fund/prices', methods=['GET'])
def get_fund_prices():
    client_ip = request.remote_addr
    current_time = time.time()

    if data_cache['funds'] and (current_time - data_cache['last_update'] < CACHE_EXPIRY):
        app_logger.info(f"获取基金价格: 使用缓存, IP: {client_ip}")
        return jsonify(data_cache['funds'])
    else:
        app_logger.info(f"获取基金价格请求来自: {client_ip}")
        watchlist = load_fund_watchlist()
        if not watchlist:
            app_logger.info(f"获取基金价格: 关注列表为空, IP: {client_ip}")
            return jsonify([])
        else:
            app_logger.info(f"获取基金价格: 批��获取 {len(watchlist)} 个基金, IP: {client_ip}")
            fund_data_list = fetch_fund_price_batch_sync(watchlist)
            data_cache['funds'] = fund_data_list
            data_cache['last_update'] = current_time
            app_logger.info(f"返回 {len(fund_data_list)} 个基金价格数据, IP: {client_ip}")
            return jsonify(fund_data_list)

# ==================== 指数模块路由 ====================
@app.route('/api/index/list', methods=['GET'])
def get_all_indices():
    """获取所有指数列表"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT code, name FROM stocks WHERE market_name = "大盘指数" OR code IN ("000001", "399001", "399006") ORDER BY code')
    indices = [{'code': row['code'], 'name': row['name']} for row in cursor.fetchall()]
    conn.close()
    return jsonify(indices)

@app.route('/api/index/watchlist', methods=['GET', 'POST', 'DELETE'])
def manage_index_watchlist():
    """管理指数关注列表"""
    if request.method == 'GET':
        watchlist = load_index_watchlist()
        return jsonify(watchlist)

    elif request.method == 'POST':
        data = request.get_json()
        if not data or 'code' not in data:
            return jsonify({'error': '缺少指数代码'}), 400

        code = data['code'].strip()
        if add_index_to_watchlist(code):
            app_logger.info(f"添加指数到关注列表: {code}")
            watchlist = load_index_watchlist()  # 返回更新后的列表
            return jsonify({'watchlist': watchlist})
        else:
            app_logger.warning(f"添加指数失败，不是有效的指数代码: {code}")
            return jsonify({'error': '不是有效的指数代码'}), 400

    elif request.method == 'DELETE':
        data = request.get_json()
        if not data or 'code' not in data:
            return jsonify({'error': '缺少指数代码'}), 400

        code = data['code'].strip()
        if remove_index_from_watchlist(code):
            app_logger.info(f"从指数关注列表移除: {code}")
            watchlist = load_index_watchlist()  # 返回更新后的列表
            return jsonify({'watchlist': watchlist})
        else:
            app_logger.warning(f"移除指数失败，指数不在关注列表中: {code}")
            return jsonify({'error': '指数不在关注列表中'}), 400

# ==================== 基金交易模块路由 ====================
@app.route('/api/fund_trans/transactions', methods=['GET', 'POST', 'DELETE'])
def manage_transactions():
    if request.method == 'GET':
        transactions = load_fund_transactions()
        summary = calculate_fund_summary(transactions)
        
        return jsonify({
            'transactions': transactions,
            'summary': summary
        })
    
    elif request.method == 'POST':
        data = request.get_json()
        if not data:
            app_logger.warning("添加基金交易记录失败: 缺少数据")
            return jsonify({'error': '缺少数据'}), 400

        # 确保必要的字段存在
        data.setdefault('date', '')
        data.setdefault('name', '')
        data.setdefault('code', '')
        data.setdefault('actual_amount', 0)
        data.setdefault('trade_amount', 0)
        data.setdefault('shares', 0)
        data.setdefault('price', 0)
        data.setdefault('fee', 0)
        data.setdefault('type', '买入')
        data.setdefault('note', '')

        transaction_id = add_fund_transaction(data)
        if transaction_id:
            # 获取刚插入的记录
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM fund_transactions WHERE id = ?', (transaction_id,))
            new_transaction = dict(cursor.fetchone())
            conn.close()

            app_logger.info(f"添加基金交易记录成功: ID {transaction_id}")
            return jsonify({'success': True, 'transaction': new_transaction})
        else:
            app_logger.error("保存基金交易记录失败")
            return jsonify({'error': '保存失败'}), 500

    elif request.method == 'DELETE':
        data = request.get_json()
        if not data:
            app_logger.warning("删除基金交易记录失败: �����少数据")
            return jsonify({'error': '缺少数据'}), 400

        # 检查是否是清空所有记录的请求
        if data.get('clear_all'):
            clear_all_fund_transactions()
            app_logger.info("清空所有基金交易记录成功")
            return jsonify({'success': True})

        # 否则是删除特定记录
        if 'id' not in data:
            app_logger.warning("删除基金交易记录失败: 缺少ID")
            return jsonify({'error': '缺少ID'}), 400

        transaction_id = data['id']
        success = delete_fund_transaction(transaction_id)
        if success:
            app_logger.info(f"删除���金交易记录成功: ID {transaction_id}")
            return jsonify({'success': True})
        else:
            app_logger.warning(f"删除基金交易记录失败: ID {transaction_id} 不存在")
            return jsonify({'error': '记录不存在'}), 400

@app.route('/api/fund_trans/summary', methods=['GET'])
def get_summary():
    transactions = load_fund_transactions()
    summary = calculate_fund_summary(transactions)
    
    return jsonify(summary)

@app.route('/api/fund_trans/import', methods=['POST'])
def import_transactions():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有选择文件'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '没有选择文件'}), 400
    
    if not (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        return jsonify({'success': False, 'message': '只支持 Excel 文件 (.xlsx, .xls)'}), 400
    
    result = import_excel_transactions(file)
    
    if result['success']:
        app_logger.info(f"导入基金交易记录成功: {result['message']}")
        return jsonify(result)
    else:
        app_logger.error(f"导入基金交易记录失败: {result['message']}")
        return jsonify(result), 400

@app.route('/api/fund_trans/export', methods=['GET'])
def export_transactions():
    output, filename = export_excel_transactions()
    
    if output is None:
        app_logger.error(f"导出基金交易记录失败: {filename}")
        return jsonify({'success': False, 'message': filename}), 400
    
    app_logger.info(f"导出基金交易记录成功: {filename}")
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )

# ==================== 日志模块路由 ====================
@app.route('/api/log/list', methods=['GET'])
def get_log_list():
    """获取日志列表"""
    client_ip = request.remote_addr
    app_logger.info(f"获取系统日志请求来自: {client_ip}")
    logs = get_logs()
    app_logger.info(f"返回 {len(logs)} 条系统日志, IP: {client_ip}")
    return jsonify(logs)

@app.route('/api/log/clear', methods=['POST'])
def clear_log_list():
    """清空日志"""
    client_ip = request.remote_addr
    app_logger.info(f"清空系统日志请求来自: {client_ip}")
    clear_logs()
    app_logger.info(f"系统日志已清空, IP: {client_ip}")
    return jsonify({'success': True, 'message': '日志已清空'})

# ==================== ����面路由 ====================
@app.route('/')
def index():
    return render_template('master.html')


# ==================== 价格变��通知功能 ====================
# 通知条件表
def init_notification_db():
    """初始化通知条件表"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 创建通知条件表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS price_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            condition_type TEXT NOT NULL,  -- 'above_price', 'below_price', 'change_percent', 'change_amount'
            threshold_value REAL NOT NULL, -- 阈值
            name TEXT, -- 股票名称
            notification_sent BOOLEAN DEFAULT 0, -- 是否已发送通知
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 创建企业微信机器人设置表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS webhook_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 检查是否已存在name字段，如果不存在则添加
    cursor.execute("PRAGMA table_info(price_notifications)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'name' not in columns:
        cursor.execute('ALTER TABLE price_notifications ADD COLUMN name TEXT')

    conn.commit()
    conn.close()


def add_price_notification(symbol, condition_type, threshold_value, name=''):
    """添加价格变动通知条件"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO price_notifications (symbol, condition_type, threshold_value, name)
            VALUES (?, ?, ?, ?)
        ''', (symbol, condition_type, threshold_value, name))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        app_logger.error(f"添加价格通知条件失败: {e}")
        conn.close()
        return False


def get_price_notifications():
    """获取所有未发送通知的条件"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, symbol, condition_type, threshold_value, name, notification_sent, created_at
        FROM price_notifications WHERE notification_sent = 0
    ''')

    results = cursor.fetchall()
    conn.close()

    # 转换为字典列表
    notifications = []
    for row in results:
        notifications.append({
            'id': row[0],
            'symbol': row[1],
            'condition_type': row[2],
            'threshold_value': row[3],
            'name': row[4],  # 股票名称
            'notification_sent': row[5],
            'created_at': row[6]
        })

    return notifications


def mark_notification_sent(notification_id):
    """标记通知已发送"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute('''
            UPDATE price_notifications SET notification_sent = 1 WHERE id = ?
        ''', (notification_id,))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        app_logger.error(f"标记通知已发送失败: {e}")
        conn.close()
        return False


def remove_notification(notification_id):
    """删除通知条件"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute('DELETE FROM price_notifications WHERE id = ?', (notification_id,))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        app_logger.error(f"删除通知条件失败: {e}")
        conn.close()
        return False


def set_webhook_url(webhook_url):
    """设置企业微信机器人webhook地址"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT OR REPLACE INTO webhook_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', ('webhook_url', webhook_url))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        app_logger.error(f"设置webhook地址失败: {e}")
        conn.close()
        return False


def get_webhook_url():
    """获取企业微信机器人webhook地址"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT value FROM webhook_settings WHERE key = ?', ('webhook_url',))
    row = cursor.fetchone()
    conn.close()

    return row[0] if row else None


def send_wechat_work_message(message):
    """发送企业微信消息"""
    webhook_url = get_webhook_url()
    if not webhook_url:
        app_logger.warning("未设置企业微信机器人webhook地址")
        return False

    try:
        payload = {
            "msgtype": "text",
            "text": {
                "content": message
            }
        }

        response = req.post(webhook_url, json=payload, timeout=10)
        if response.status_code == 200 and response.json().get('errcode') == 0:
            app_logger.info("企业微信消息发送成功")
            return True
        else:
            app_logger.error(f"企业微信消息发送失败: {response.text}")
            return False
    except Exception as e:
        app_logger.error(f"发送企业微信消息异常: {e}")
        return False


def is_trading_time():
    """判断是否为交易时间"""
    now = datetime.now()
    day = now.weekday()  # 0是周一，6是周日
    hour = now.hour
    minute = now.minute
    time_in_minutes = hour * 60 + minute

    # A股交易时间: 9:30-11:30, 13:00-15:00
    # 港股交易时间: 9:30-12:00, 13:00-16:00
    # 这里简化为工作日9:00-17:00
    if day >= 5:  # 周六、周日
        return False

    if time_in_minutes < 9*60 or time_in_minutes >= 17*60:  # 9:00之前或17:00之后
        return False

    return True


def check_price_notifications(trading_hours_only=True):
    """检查价格通知条件"""
    app_logger.info("开始检查价格通知条件")

    if trading_hours_only and not is_trading_time():
        app_logger.info("非交易时间，跳过检查")
        return

    notifications = get_price_notifications()
    if not notifications:
        app_logger.info("没有需要检查的通知条件")
        return

    app_logger.info(f"发现 {len(notifications)} 个待检查的通知条件")

    # 获取所有需要检查的股票代码
    symbols = list(set([n['symbol'] for n in notifications]))
    app_logger.info(f"需要检查的股票代码: {symbols}")

    # 批量获取实时数据
    try:
        # 使用现有的批量获取方法，与股票页面使用相同的方法
        price_data_list = get_stock_realtime_data_batch(symbols)
        app_logger.info(f"获取到 {len(price_data_list)} 个股票的实时数据")

        # 直接使用返回的数据构建映射，使用symbol字段作为key
        price_data_map = {data['symbol']: data for data in price_data_list}
        app_logger.info(f"构建价格数据映射: {list(price_data_map.keys())}")
    except Exception as e:
        app_logger.error(f"获取实时数据失败: {e}")
        return

    # 检查每个通知条件
    for notification in notifications:
        symbol = notification['symbol']
        condition_type = notification['condition_type']
        threshold_value = notification['threshold_value']
        name = notification['name']

        app_logger.info(f"检查通知条件: {symbol} ({name}), 类型: {condition_type}, 阈值: {threshold_value}")

        # 直接使用原始代码进行匹配，因为API返回的就是原始代码格式
        if symbol not in price_data_map:
            app_logger.warning(f"无法获取 {symbol} 的实时数据")
            continue

        current_data = price_data_map[symbol]
        current_price = current_data.get('price', 0)
        current_chg = current_data.get('change', 0)
        current_percent = current_data.get('change_percent', 0)

        app_logger.info(f"股票 {symbol} 当前价格: {current_price}, 涨跌额: {current_chg}, 涨跌幅: {current_percent}%")

        # 检查是否满足条件
        condition_met = False
        condition_desc = ""

        if condition_type == 'above_price':
            app_logger.info(f"检查价格条件: {current_price} >= {threshold_value}? {current_price >= threshold_value}")
            if current_price >= threshold_value:
                condition_met = True
                condition_desc = f"价格达到或超过 {threshold_value} 元"
        elif condition_type == 'below_price':
            app_logger.info(f"检查价格条件: {current_price} <= {threshold_value}? {current_price <= threshold_value}")
            if current_price <= threshold_value:
                condition_met = True
                condition_desc = f"价格跌至或低于 {threshold_value} 元"
        elif condition_type == 'change_percent':
            app_logger.info(f"检查涨跌幅条件: abs({current_percent}) >= abs({threshold_value})? {abs(current_percent)} >= {abs(threshold_value)}")
            if abs(current_percent) >= abs(threshold_value):
                condition_satisfied = (threshold_value > 0 and current_percent >= threshold_value) or \
                                     (threshold_value < 0 and current_percent <= threshold_value)
                app_logger.info(f"方向判断: ({threshold_value} > 0 and {current_percent} >= {threshold_value}) or ({threshold_value} < 0 and {current_percent} <= {threshold_value}) = {condition_satisfied}")
                if condition_satisfied:
                    condition_met = True
                    direction = "上涨" if threshold_value > 0 else "下跌"
                    condition_desc = f"{direction}{abs(threshold_value)}%"
        elif condition_type == 'change_amount':
            app_logger.info(f"检查涨跌额条件: abs({current_chg}) >= abs({threshold_value})? {abs(current_chg)} >= {abs(threshold_value)}")
            if abs(current_chg) >= abs(threshold_value):
                condition_satisfied = (threshold_value > 0 and current_chg >= threshold_value) or \
                                     (threshold_value < 0 and current_chg <= threshold_value)
                app_logger.info(f"方向判断: ({threshold_value} > 0 and {current_chg} >= {threshold_value}) or ({threshold_value} < 0 and {current_chg} <= {threshold_value}) = {condition_satisfied}")
                if condition_satisfied:
                    condition_met = True
                    direction = "上涨" if threshold_value > 0 else "下跌"
                    condition_desc = f"{direction}{abs(threshold_value)} 元"

        if condition_met:
            app_logger.info(f"条件满足！准备发送通知: {symbol}")
            # 发送通知
            stock_name = current_data.get('name', symbol)
            message = f"【价格提醒】{stock_name} ({symbol})\n" \
                     f"条件: {condition_desc}\n" \
                     f"当前价格: {current_price}\n" \
                     f"涨跌额: {current_data.get('chg', 0)}\n" \
                     f"涨跌幅: {current_data.get('percent', 0)}%\n" \
                     f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

            app_logger.info(f"准备发送消息: {message}")

            if send_wechat_work_message(message):
                # 标记通知已发送并删除监控
                mark_notification_sent(notification['id'])
                app_logger.info(f"价格通知已发送并标记完成: {symbol}")
            else:
                app_logger.error(f"价格通知发送失败: {symbol}")
        else:
            app_logger.info(f"条件未满足，继续下一个: {symbol}")

            # 特别处理价格为0的情况，这可能表示数据不可用
            if current_price == 0 and condition_type in ['above_price', 'below_price']:
                app_logger.warning(f"股票 {symbol} 的价格为0，可能是非交易时间或数据不可用")


def notification_monitor():
    """价格通知监控线程"""
    app_logger.info("价格通知监控线程启动")

    while True:
        try:
            check_price_notifications()
        except Exception as e:
            app_logger.error(f"价格通知检查过程中出现异常: {e}")

        # 每5分钟检查一次
        time.sleep(300)


# 初始化通知数据库表
init_notification_db()

# 添加API路由

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


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=3333)
