# app.py
import os
from flask import Flask, render_template, jsonify, request
from datetime import datetime
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
def init_db():
    """初始化数据库表"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 创建股票数据表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT,
            market_type TEXT,
            market_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 创建股票关注列表表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT,
            type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 为已存在的表添加新字段（如果尚未添加）
    try:
        cursor.execute('ALTER TABLE stock_watchlist ADD COLUMN name TEXT')
        app_logger.info("为stock_watchlist表添加name字段")
    except sqlite3.OperationalError:
        app_logger.debug("stock_watchlist表的name字段已存在")  # 如果字段已存在，则忽略错误

    try:
        cursor.execute('ALTER TABLE stock_watchlist ADD COLUMN type TEXT')
        app_logger.info("为stock_watchlist表添加type字段")
    except sqlite3.OperationalError:
        app_logger.debug("stock_watchlist表的type字段已存在")  # 如果字段已存在，则忽略错误

    # 创建基金关注列表表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fund_watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 创建基金交易记录表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fund_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            name TEXT,
            code TEXT,
            actual_amount REAL,
            trade_amount REAL,
            shares REAL,
            price REAL,
            fee REAL,
            type TEXT,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

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

    # 创建系统设置表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 创建索引以提高查询性能
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_stocks_code ON stocks(code)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fund_transactions_code ON fund_transactions(code)')

    conn.commit()
    conn.close()

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


def get_market_type(symbol):
    """判断股票市场类型"""
    if len(symbol) == 6 and symbol.isdigit():
        return 'A股'
    elif len(symbol) == 5 and symbol.isdigit():
        return '港股'
    else:
        return '未知'

def get_xueqiu_market_prefix(symbol):
    """根据雪球API规则转换代码"""
    # 如果代码已经包含前缀，则直接返回
    if symbol.startswith(('SH', 'SZ', 'HK', 'US')):
        return symbol

    # 特殊处理某些指数代码
    if symbol in ['000001', '399001']:
        return f"SH{symbol}"
    elif symbol in ['.IXIC', '.DJI', '.SPX', '.INX']:
        return symbol  # 这些美股指数代码不需要额外前缀

    if len(symbol) == 6 and symbol.isdigit():
        if symbol.startswith('6'):
            return f"SH{symbol}"
        else:
            return f"SZ{symbol}"
    elif len(symbol) == 5 and symbol.isdigit():
        return symbol
    return symbol

def excel_date_to_str(excel_date):
    try:
        date = pd.to_datetime(excel_date, unit='D', origin='1900-01-01')
        return date.strftime('%Y/%m/%d')
    except (ValueError, TypeError):
        return excel_date

# ==================== 数据服务函数 ====================
def load_stock_watchlist() -> List[Dict[str, Any]]:
    """加载股票关注列表"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT code, name, type FROM stock_watchlist ORDER BY created_at')
    result = [{'code': row['code'], 'name': row['name'], 'type': row['type']} for row in cursor.fetchall()]
    conn.close()
    return result

def add_stock_to_watchlist(code: str, name: str = '', type_val: str = '') -> bool:
    """添加股票到关注列表"""
    app_logger.info(f"尝试添加股票到关注列表: 代码={code}, 名称={name}, 类型={type_val}")

    conn = get_db_connection()
    cursor = conn.cursor()

    # 如果没有提供类型值，从stocks表中获取market_type
    if not type_val:
        cursor.execute('SELECT market_type FROM stocks WHERE code = ?', (code,))
        stock_row = cursor.fetchone()
        if stock_row:
            type_val = stock_row['market_type'] or ''
            app_logger.debug(f"从stocks表获取类型值: {type_val}")

    try:
        cursor.execute('INSERT INTO stock_watchlist (code, name, type) VALUES (?, ?, ?)', (code, name, type_val))
        conn.commit()
        conn.close()
        app_logger.info(f"成功添加股票到关注列表: {code}")
        return True
    except sqlite3.IntegrityError:
        # 代码已存在
        conn.close()
        app_logger.warning(f"股票已在关注列表中，无法重复添加: {code}")
        return False

def remove_stock_from_watchlist(code: str) -> bool:
    """从关注列表中移除股票"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM stock_watchlist WHERE code = ?', (code,))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    return rows_affected > 0

def search_stock_by_code(code: str) -> List[Dict[str, Any]]:
    """在数据库中搜索指定股票代码"""
    conn = get_db_connection()
    cursor = conn.cursor()

    clean_code = str(code).strip()

    # 首先尝试精确匹配原始代码
    cursor.execute('''
        SELECT code, name, market_type, market_name FROM stocks
        WHERE code = ?
    ''', (clean_code,))

    exact_match_rows = cursor.fetchall()

    # 如果没有精确匹配，尝试多种可能的标准化形式
    if not exact_match_rows and clean_code.isdigit():
        # 尝试补零到5位（港股）
        if len(clean_code) < 5:
            padded_5 = clean_code.zfill(5)
            cursor.execute('''
                SELECT code, name, market_type, market_name FROM stocks
                WHERE code = ?
            ''', (padded_5,))
            exact_match_rows = cursor.fetchall()

        # 如果还没找到，尝试补零到6位（A股）
        if not exact_match_rows and len(clean_code) < 6:
            padded_6 = clean_code.zfill(6)
            cursor.execute('''
                SELECT code, name, market_type, market_name FROM stocks
                WHERE code = ?
            ''', (padded_6,))
            exact_match_rows = cursor.fetchall()

        # 如果还没找到，尝试去掉前导零（从6位到5位）
        if not exact_match_rows and len(clean_code) == 6 and clean_code.startswith('0'):
            stripped = clean_code[1:]
            cursor.execute('''
                SELECT code, name, market_type, market_name FROM stocks
                WHERE code = ?
            ''', (stripped,))
            exact_match_rows = cursor.fetchall()

    # 模糊匹配代码和名称
    cursor.execute('''
        SELECT code, name, market_type, market_name FROM stocks
        WHERE code LIKE ? OR name LIKE ?
        LIMIT 20
    ''', (f'%{clean_code}%', f'%{clean_code}%'))

    fuzzy_match_rows = cursor.fetchall()

    conn.close()

    # 合并结果，避免重复
    seen_codes = set()
    results = []

    # 先添加精确匹配的结果
    for row in exact_match_rows:
        result = dict(row)
        if result['code'] not in seen_codes:
            # 根据市场类型确定类型标识
            if result['market_name'] == '大盘指数' or result['code'] in ['000001', '399001', '399006']:
                result['type'] = 'index'
            elif result['market_type'] == 'SH':
                result['type'] = 'sh_stock'
            elif result['market_type'] == 'SZ':
                result['type'] = 'sz_stock'
            elif result['market_type'] == 'HK':
                result['type'] = 'hk_stock'
            elif result['market_type'] == 'US':
                result['type'] = 'us_stock'
            else:
                result['type'] = 'stock'
            results.append(result)
            seen_codes.add(result['code'])

    # 再添加模糊匹配的结果
    for row in fuzzy_match_rows:
        result = dict(row)
        if result['code'] not in seen_codes:
            # 根据市场类型确定类型标识
            if result['market_name'] == '大盘指数' or result['code'] in ['000001', '399001', '399006']:
                result['type'] = 'index'
            elif result['market_type'] == 'SH':
                result['type'] = 'sh_stock'
            elif result['market_type'] == 'SZ':
                result['type'] = 'sz_stock'
            elif result['market_type'] == 'HK':
                result['type'] = 'hk_stock'
            elif result['market_type'] == 'US':
                result['type'] = 'us_stock'
            else:
                result['type'] = 'stock'
            results.append(result)
            seen_codes.add(result['code'])

    return results

def normalize_stock_code(code: str, market_type: str = None) -> str:
    """
    标准化股票代码，确保A股为6位数，港股为5位数
    """
    # 检查是否为特殊的指数代码格式，如果是则直接返回
    special_indices = ['.IXIC', '.DJI', '.SPX', '.INX']  # 美股指数
    if code in special_indices:
        return code

    # 检查是否为带前缀的指数代码格式
    if code.startswith(('SH', 'SZ', 'HK', 'US')):
        # 对于带前缀的代码，检查是否是特殊格式
        suffix = code[2:]  # 去掉前缀
        if suffix in special_indices:
            return code  # 保持原样返回

    # 移除交易所后缀
    clean_code = code.split('.')[0] if '.' in code else code

    # 如果已经有后缀，获取市场类型
    if '.' in code and market_type is None:
        suffix = code.split('.')[-1].upper()
        if suffix in ['SH', 'SZ']:
            market_type = 'A股'
        elif suffix == 'HK':
            market_type = '港股'
        elif suffix == 'US':
            market_type = '美股'

    # 根据市场类型补充前导零
    if market_type == '美股':
        # 美股代码不补零，直接返回
        normalized_code = clean_code
    elif market_type == '港股' or len(clean_code) == 5:
        # 港股代码为5位数
        normalized_code = clean_code.zfill(5)
    elif market_type == 'A股' or len(clean_code) == 6:
        # A股代码为6位数
        normalized_code = clean_code.zfill(6)
    else:
        # 默认按A股处理，但要保留特殊格式
        normalized_code = clean_code.zfill(6) if clean_code.isdigit() else clean_code

    return normalized_code

def get_stock_realtime_data(code: str) -> Optional[Dict[str, Any]]:
    """获取单个股票实时数据（保留此函数用于兼容性）"""
    try:
        # 标准化代码
        normalized_code = normalize_stock_code(code)

        # 调用批量获取函数，但只传入单个代码
        result = get_stock_realtime_data_batch([normalized_code])
        if result and len(result) > 0:
            return result[0]
        return None
    except Exception as e:
        app_logger.error(f"获取 {code} (雪球) 价格时发生错误: {e}")
        return None

def get_stock_realtime_data_batch(codes: List[str]) -> List[Dict[str, Any]]:
    """批量获取股票实时数据"""
    if not codes:
        return []

    try:
        # 标准化所有代码
        normalized_codes = [normalize_stock_code(code) for code in codes]

        # 获取对应的雪球符号
        xueqiu_symbols = [get_xueqiu_market_prefix(code) for code in normalized_codes]

        # 打印日志，注意只打印一次
        app_logger.info(f"开始批量获取股票实时数据: 数量={len(normalized_codes)}, 代码={','.join(normalized_codes[:5])}{'...' if len(normalized_codes) > 5 else ''}")

        # 构建参数，将所有symbol用逗号连接
        params = {"symbol": ",".join(xueqiu_symbols)}

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Cookie': 'xq_a_token=;'
        }

        start_time = time.time()
        response = requests.get(STOCK_API_URL, params=params, headers=headers, timeout=10)
        response_time = time.time() - start_time

        app_logger.info(f"股票API批量响应时间: {response_time:.2f}s, 状态码: {response.status_code}, 代码数量: {len(normalized_codes)}")

        response.raise_for_status()

        data = response.json()

        if not data or 'data' not in data or not data['data']:
            app_logger.warning(f"股票API批量返回数据为空")
            return []

        # 为特殊指数代码定义名称映射
        index_name_map = {
            'SH000001': '上证指数',
            'SZ399001': '深证成指',
            'SZ399006': '创业板指',
            'SH000300': '沪深300',
            'SH000016': '上证50',
            'SZ399905': '中证500',
            'SZ399005': '中小板指',
            'HKHSI': '恒生指数',
            'HKHSCEI': '国企指数',
            'HKHSTECH': '恒生科技',
            '.IXIC': '纳斯达克',
            '.DJI': '道琼斯',
            '.INX': '标普500'
        }

        # 一次性从数据库获取所有股票信息
        conn = get_db_connection()
        cursor = conn.cursor()

        # 构建SQL查询，使用占位符
        placeholders = ','.join(['?' for _ in normalized_codes])
        cursor.execute(f'SELECT code, name, market_type, market_name FROM stocks WHERE code IN ({placeholders})', normalized_codes)
        stock_rows = {row['code']: dict(row) for row in cursor.fetchall()}
        conn.close()

        results = []
        # 注意：API返回的数据结构是 {"data": [...]}，而不是 {"data": {"items": [...]}}
        for stock_data in data['data']:
            symbol = stock_data.get('symbol')

            # 尝试匹配返回的symbol到我们的标准化代码
            matched_code = None
            for norm_code in normalized_codes:
                if symbol == get_xueqiu_market_prefix(norm_code):
                    matched_code = norm_code
                    break

            if not matched_code:
                continue  # 如果找不到匹配的代码，跳过这条数据

            price = stock_data.get('current')
            change = stock_data.get('chg', 0)
            change_percent = stock_data.get('percent', 0)
            open_price = stock_data.get('open')
            high_price = stock_data.get('high')
            low_price = stock_data.get('low')

            # 获取股票详细信息
            row = stock_rows.get(matched_code)

            # 优先使用数据库中的名称，如果没有则使用映射，最后使用代码本身
            name = row['name'] if row and row['name'] else index_name_map.get(matched_code, matched_code)

            # 根据市场类型确定类型标识
            type_identifier = 'stock'  # 默认类型
            if row:
                if row['market_name'] == '大盘指数' or matched_code in ['000001', '399001', '399006']:
                    type_identifier = 'index'
                elif row['market_type'] == 'SH':
                    type_identifier = 'sh_stock'
                elif row['market_type'] == 'SZ':
                    type_identifier = 'sz_stock'
                elif row['market_type'] == 'HK':
                    type_identifier = 'hk_stock'
                elif row['market_type'] == 'US':
                    type_identifier = 'us_stock'
                else:
                    type_identifier = 'stock'

            results.append({
                'symbol': matched_code,
                'name': name,
                'market': get_market_type(matched_code),
                'type': type_identifier,  # 添加类型字段
                'price': price,
                'change': change,
                'change_percent': change_percent,
                'open_price': open_price,
                'high_price': high_price,
                'low_price': low_price,
                'currency': 'HKD' if len(matched_code) == 5 else 'CNY'
            })

        return results

    except Exception as e:
        app_logger.error(f"批量获取股票价格时发生错误: {e}")
        return []

# ==================== 指数管理功能 ====================
def load_index_watchlist() -> List[str]:
    """加载指数关注列表 - 从股票关注列表中筛选指数"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT sw.code
        FROM stock_watchlist sw
        JOIN stocks s ON sw.code = s.code
        WHERE s.market_name = '大盘指数'
        OR s.code IN ('000001', '399001', '399006')
    ''')
    result = [row['code'] for row in cursor.fetchall()]
    conn.close()
    return result

def add_index_to_watchlist(code: str) -> bool:
    """添加指数到关注列表"""
    # 首先检查该代码是否是指数
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT code FROM stocks WHERE code = ? AND (market_name = "大盘指数" OR code IN ("000001", "399001", "399006"))', (code,))
    is_index = cursor.fetchone() is not None
    conn.close()

    if not is_index:
        return False  # 不是指数，不能添加

    # 尝试添加到股票关注列表（指数也是股票的一种）
    return add_stock_to_watchlist(code)

def remove_index_from_watchlist(code: str) -> bool:
    """从指数关注列表移除"""
    # 从股票关注列表中移除
    return remove_stock_from_watchlist(code)

def fetch_fund_price_batch_sync(codes):
    """同步获取多个基金的价格数据"""
    try:
        if not isinstance(codes, list):
            codes = [codes]

        code_str = ','.join(codes)
        today = time.strftime('%Y-%m-%d')
        params = {'code': code_str, 'startDate': today}
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

        app_logger.info(f"开始批量获取基金数据: 数量={len(codes)}, 代码={code_str}")

        start_time = time.time()
        response = requests.get(FUND_BATCH_API_URL, params=params, headers=headers, timeout=20)
        response_time = time.time() - start_time

        app_logger.info(f"基金API响应时间: {response_time:.2f}s, 状态码: {response.status_code}, 请求代码: {code_str}")

        response.raise_for_status()

        data = response.json()

        if not data or 'data' not in data:
            app_logger.error(f"基金API返回数据为空或格式错误: {code_str}")
            return []

        def to_float(value):
            if value is None: return None
            try:
                if isinstance(value, str): value = value.replace('%', '').strip()
                return float(value)
            except (ValueError, TypeError): return None

        fund_data_list = []
        for fund_data in data['data']:
            code = str(fund_data.get('code', ''))

            fund_info = {
                'code': code,
                'name': fund_data.get('name', '--'),
                'type': fund_data.get('type', '--'),
                'netWorth': to_float(fund_data.get('netWorth')),
                'expectWorth': to_float(fund_data.get('expectWorth')),
                'totalWorth': to_float(fund_data.get('totalWorth')),
                'expectGrowth': to_float(fund_data.get('expectGrowth')),
                'dayGrowth': to_float(fund_data.get('dayGrowth')),
                'lastWeekGrowth': to_float(fund_data.get('lastWeekGrowth')),
                'lastMonthGrowth': to_float(fund_data.get('lastMonthGrowth')),
                'lastThreeMonthsGrowth': to_float(fund_data.get('lastThreeMonthsGrowth')),
                'lastSixMonthsGrowth': to_float(fund_data.get('lastSixMonthsGrowth')),
                'lastYearGrowth': to_float(fund_data.get('lastYearGrowth')),
                'buyMin': fund_data.get('buyMin'),
                'buySourceRate': fund_data.get('buySourceRate'),
                'buyRate': fund_data.get('buyRate'),
                'manager': fund_data.get('manager'),
                'fundScale': fund_data.get('fundScale'),
                'netWorthDate': fund_data.get('netWorthDate'),
                'expectWorthDate': fund_data.get('expectWorthDate'),
                # 添加格式化的日期信息，便于前端显示
                'netWorthDisplay': f"{to_float(fund_data.get('netWorth'))}<br><small>{fund_data.get('netWorthDate', '')}</small>" if fund_data.get('netWorth') else "--",
                'expectWorthDisplay': f"{to_float(fund_data.get('expectWorth'))}<br><small>{fund_data.get('expectWorthDate', '')}</small>" if fund_data.get('expectWorth') else "--"
            }
            fund_data_list.append(fund_info)
        return fund_data_list

    except requests.exceptions.Timeout:
        app_logger.error(f"批量获取基金错误: 请求超时 (20秒)")
        return []
    except Exception as e:
        app_logger.error(f"批量获取基金错误: {e}")
        return []


def load_fund_transactions():
    """加载基金交易记录"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM fund_transactions ORDER BY date DESC, id DESC')
    rows = cursor.fetchall()
    transactions = []
    for row in rows:
        transaction = dict(row)
        # 将数据库中的值转换为适当的类型
        for key in ['actual_amount', 'trade_amount', 'shares', 'price', 'fee']:
            if transaction[key] is not None:
                transaction[key] = float(transaction[key])
        transactions.append(transaction)
    conn.close()
    return transactions

def add_fund_transaction(transaction):
    """添加基金交易记录"""
    app_logger.info(f"尝试添加基金交易记录: 代码={transaction.get('code', 'N/A')}, 类型={transaction.get('type', 'N/A')}, 金额={transaction.get('actual_amount', 0)}")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO fund_transactions
            (date, name, code, actual_amount, trade_amount, shares, price, fee, type, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            transaction.get('date'), transaction.get('name'), transaction.get('code'),
            transaction.get('actual_amount'), transaction.get('trade_amount'), transaction.get('shares'),
            transaction.get('price'), transaction.get('fee'), transaction.get('type'), transaction.get('note')
        ))
        conn.commit()
        transaction_id = cursor.lastrowid
        conn.close()
        app_logger.info(f"成功添加基金交易记录: ID={transaction_id}, 代码={transaction.get('code', 'N/A')}")
        return transaction_id
    except Exception as e:
        conn.close()
        app_logger.error(f"添加基金交易记录失败: 代码={transaction.get('code', 'N/A')}, 错误={e}")
        return None

def update_fund_transaction(transaction_id, transaction):
    """更新基金交易记录"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE fund_transactions
            SET date=?, name=?, code=?, actual_amount=?, trade_amount=?, shares=?, price=?, fee=?, type=?, note=?
            WHERE id=?
        ''', (
            transaction.get('date'), transaction.get('name'), transaction.get('code'),
            transaction.get('actual_amount'), transaction.get('trade_amount'), transaction.get('shares'),
            transaction.get('price'), transaction.get('fee'), transaction.get('type'), transaction.get('note'),
            transaction_id
        ))
        conn.commit()
        rows_affected = cursor.rowcount
        conn.close()
        return rows_affected > 0
    except Exception as e:
        conn.close()
        app_logger.error(f"更新基金交易记录失败: {e}")
        return False

def delete_fund_transaction(transaction_id):
    """删除基金交易记录"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM fund_transactions WHERE id = ?', (transaction_id,))
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    return rows_affected > 0

def clear_all_fund_transactions():
    """清空所有基金交易记录"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM fund_transactions')
    conn.commit()
    conn.close()

def calculate_fund_summary(transactions):
    """计算基金交易汇总数据"""
    if not transactions:
        return {
            "total_shares": 0, "total_cost": 0, "realized_profit": 0,
            "dividend_total": 0, "buy_count": 0, "sell_count": 0,
            "dividend_count": 0, "trade_count": 0, "total_fee": 0,
            "market_value": 0  # 添加市值字段
        }

    holdings = {}
    realized_profit = 0
    dividend_total = 0
    buy_count = 0
    sell_count = 0
    dividend_count = 0
    total_fee = 0

    for t in transactions:
        code = t.get('code')
        t_type = t.get('type')

        shares = float(t.get('shares', 0)) if t.get('shares') is not None else 0
        amount = float(t.get('actual_amount', 0)) if t.get('actual_amount') is not None else 0
        fee = float(t.get('fee', 0)) if t.get('fee') is not None else 0

        total_fee += fee

        if t_type == '买入':
            buy_count += 1
            if code not in holdings:
                holdings[code] = {'shares': 0, 'cost': 0}

            holdings[code]['shares'] += shares
            holdings[code]['cost'] += (abs(amount) + fee)

        elif t_type == '卖出':
            sell_count += 1
            if code in holdings and holdings[code]['shares'] > 0:
                avg_cost_per_share = holdings[code]['cost'] / holdings[code]['shares']
                sell_cost = shares * avg_cost_per_share
                sell_income = abs(amount) - fee
                realized_profit += (sell_income - sell_cost)
                holdings[code]['shares'] -= shares
                holdings[code]['cost'] -= sell_cost

                if holdings[code]['shares'] <= 0.0001:
                    del holdings[code]

        elif t_type == '分红':
            dividend_count += 1
            dividend_total += abs(amount)
            realized_profit += abs(amount)

    total_shares = sum(h['shares'] for h in holdings.values())
    total_cost = sum(h['cost'] for h in holdings.values())
    total_cost = abs(total_cost)

    # 注意：market_value需要通过实时API获取，这里暂时设为0
    # 在实际应用中，可能需要调用基金API获取当前净值来计算市值
    market_value = 0

    return {
        "total_shares": round(total_shares, 2),
        "total_cost": round(total_cost, 2),
        "realized_profit": round(realized_profit, 2),
        "dividend_total": round(dividend_total, 2),
        "total_fee": round(total_fee, 2),
        "market_value": round(market_value, 2),  # 添加市值
        "buy_count": buy_count,
        "sell_count": sell_count,
        "dividend_count": dividend_count,
        "trade_count": len(transactions)
    }

def import_excel_transactions(file_stream):
    try:
        df = pd.read_excel(file_stream, header=0)
        
        if df.empty:
            return {"success": False, "message": "Excel 文件为空"}
        
        transactions = load_fund_transactions()
        new_records = []
        
        current_max_id = max([t.get('id', 0) for t in transactions], default=0)
        
        column_map = {
            '日期': 'date', '名称': 'name', '基金代码': 'code',
            '实际金额': 'actual_amount', '买入/卖出/分红金额': 'trade_amount',
            '买入/卖出份额': 'shares', '确认价格': 'price', '手续费': 'fee', '备注': 'note'
        }
        
        missing_cols = [col for col in column_map.keys() if col not in df.columns]
        if missing_cols:
            return {"success": False, "message": f"Excel 缺少必要列: {', '.join(missing_cols)}"}
        
        df.rename(columns=column_map, inplace=True)
        
        for index, row in df.iterrows():
            try:
                raw_date = row['date']
                if pd.isna(raw_date):
                    date_str = ""
                elif isinstance(raw_date, (int, float)):
                    date_str = excel_date_to_str(raw_date)
                else:
                    date_str = str(raw_date).replace('-', '/')
                
                actual_amount = abs(float(row['actual_amount']) if pd.notna(row['actual_amount']) else 0.0)
                shares = abs(float(row['shares']) if pd.notna(row['shares']) else 0.0)
                fee = abs(float(row['fee']) if pd.notna(row['fee']) else 0.0)
                
                trade_type = '买入'
                note = str(row['note']) if pd.notna(row['note']) else ""
                
                if note:
                    note_lower = note.lower()
                    if '卖出' in note_lower:
                        trade_type = '卖出'
                    elif '分红' in note_lower:
                        trade_type = '分红'
                    elif '买入' in note_lower:
                        trade_type = '买入'
                
                if trade_type == '买入' and shares == 0 and actual_amount > 0:
                    trade_type = '分红'
                
                record = {
                    "id": current_max_id + index + 1,
                    "date": date_str,
                    "name": str(row['name']) if pd.notna(row['name']) else "",
                    "code": str(row['code']) if pd.notna(row['code']) else "",
                    "actual_amount": actual_amount,
                    "trade_amount": float(row['trade_amount']) if pd.notna(row['trade_amount']) else 0.0,
                    "shares": shares,
                    "price": float(row['price']) if pd.notna(row['price']) else 0.0,
                    "fee": fee,
                    "type": trade_type,
                    "note": note
                }
                new_records.append(record)
            except Exception as e:
                app_logger.error(f"跳过第 {index + 2} 行（Excel行号），解析错误: {e}")
                continue
        
        if not new_records:
            return {"success": False, "message": "未解析到有效数据"}
            
        transactions.extend(new_records)
        if save_fund_transactions(transactions):
            return {"success": True, "message": f"成功导入 {len(new_records)} 条记录"}
        else:
            return {"success": False, "message": "保存数据失败"}
            
    except ImportError:
        return {"success": False, "message": "缺少 pandas 库，请安装: pip install pandas openpyxl"}
    except Exception as e:
        app_logger.error(f"导入失败: {str(e)}")
        return {"success": False, "message": f"导入失败: {str(e)}"}

def export_excel_transactions():
    try:
        transactions = load_fund_transactions()
        if not transactions:
            return None, "没有数据可导出"
        
        df = pd.DataFrame(transactions)
        
        columns = ['date', 'name', 'code', 'actual_amount', 'trade_amount', 'shares', 'price', 'fee', 'type', 'note']
        existing_columns = [col for col in columns if col in df.columns]
        df = df[existing_columns]
        
        column_map = {
            'date': '日期', 'name': '名称', 'code': '代码', 'actual_amount': '实际金额',
            'trade_amount': '交易金额', 'shares': '份额', 'price': '价格', 'fee': '手续费',
            'type': '类型', 'note': '备注'
        }
        df.rename(columns=column_map, inplace=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"fund_transactions_{timestamp}.xlsx"
        
        from io import BytesIO
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='交易记录')
        
        output.seek(0)
        return output, filename
        
    except ImportError:
        return None, "缺少 pandas 库，请安装: pip install pandas openpyxl"
    except Exception as e:
        app_logger.error(f"导出失败: {str(e)}")
        return None, f"导出失败: {str(e)}"

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

def get_setting(key, default=None):
    """获取设置值"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row['value'])
        except:
            return row['value']
    return default

def set_setting(key, value):
    """设置值"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (key, json.dumps(value)))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        conn.close()
        app_logger.error(f"保存设置失败 {key}: {e}")
        return False

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

@app.route('/api/fund/detail', methods=['GET'])
def get_fund_detail():
    code = request.args.get('code')
    if not code:
        app_logger.warning("获取基金详情失败: 缺少基金代码")
        return jsonify({'error': '缺少基金代码'}), 400
    
    try:
        fund_data_list = fetch_fund_price_batch_sync([code])
        
        if fund_data_list:
            app_logger.info(f"获取基金详情成功: {code}")
            return jsonify(fund_data_list[0])
        else:
            app_logger.warning(f"未找到基金详情: {code}")
            return jsonify({'error': '未找到该基金数据'}), 404
            
    except Exception as e:
        app_logger.error(f"获取基金详情错误: {e}")
        return jsonify({'error': f'获取基金数据失败: {str(e)}'}), 500

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

# ==================== ���面路由 ====================
@app.route('/')
def index():
    return render_template('master.html')


# ==================== 价格变动通知功能 ====================
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
except ImportError:
    print("Warning: Could not import stock_module blueprint")

try:
    from modules.fund import fund_bp
    app.register_blueprint(fund_bp, url_prefix='/api/fund')
except ImportError:
    print("Warning: Could not import fund blueprint")

try:
    from modules.fund_trans import fund_trans_bp
    app.register_blueprint(fund_trans_bp, url_prefix='/api/fund_trans')
except ImportError:
    print("Warning: Could not import fund_trans blueprint")

try:
    from modules.notify import notify_bp
    app.register_blueprint(notify_bp)
except ImportError:
    print("Warning: Could not import notify blueprint")

# 注册页面路由
try:
    from modules.stock_module import stock_page
    app.add_url_rule('/stock_page', 'stock_page', stock_page)
except ImportError:
    print("Warning: Could not import stock_page route")

try:
    from modules.fund import fund_page
    app.add_url_rule('/fund_page', 'fund_page', fund_page)
except ImportError:
    print("Warning: Could not import fund_page route")

try:
    from modules.fund_trans import fund_trans_page
    app.add_url_rule('/fund_trans_page', 'fund_trans_page', fund_trans_page)
except ImportError:
    print("Warning: Could not import fund_trans_page route")

try:
    from modules.notify import notification_page
    app.add_url_rule('/notification_page', 'notification_page', notification_page)
except ImportError:
    print("Warning: Could not import notification_page route")


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=3333)
