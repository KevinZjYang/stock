# notify.py
from flask import Blueprint, request, jsonify, render_template, make_response
import sys
import os
# 添加上级目录到路径，以便导入 models.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.models import (
    app_logger, get_db_connection
)
import threading
import time
from datetime import datetime
import requests as req
import sqlite3
from datetime import datetime, timedelta

notify_bp = Blueprint('notify', __name__)

# ==================== 价格变动通知功能 ====================
# 从 models 模块导入数据库连接函数
from modules.models import get_db_connection, DATABASE_PATH

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
        from modules.models import get_stock_realtime_data_batch
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

# 启动价格通知监控线程
def start_notification_monitor():
    notification_thread = threading.Thread(target=notification_monitor, daemon=True)
    notification_thread.start()

# 立即启动监控
start_notification_monitor()

@notify_bp.route('/notification_page')
def notification_page():
    return render_template('notification.html')

@notify_bp.route('/api/notifications', methods=['GET', 'POST', 'DELETE'])
def manage_notifications():
    if request.method == 'GET':
        notifications = get_price_notifications()
        return jsonify(notifications)

    elif request.method == 'POST':
        data = request.get_json()
        if not data or 'symbol' not in data or 'condition_type' not in data or 'threshold_value' not in data:
            return jsonify({'error': '缺少必要参数'}), 400

        symbol = data['symbol']
        condition_type = data['condition_type']
        threshold_value = data['threshold_value']

        # 尝试获取股票名称
        stock_name = symbol  # 默认使用代码作为名称
        try:
            from app import search_stock_by_code
            results = search_stock_by_code(symbol)
            if results:
                stock_name = results[0]['name']  # 使用第一个匹配结果的名称
        except:
            pass  # 如果获取名称失败，继续使用代码作为名称

        if add_price_notification(symbol, condition_type, threshold_value, stock_name):
            app_logger.info(f"添加价格通知成功: {symbol} {condition_type} {threshold_value}")
            return jsonify({'success': True})
        else:
            return jsonify({'error': '添加通知失败'}), 500

    elif request.method == 'DELETE':
        data = request.get_json()
        if not data or 'id' not in data:
            return jsonify({'error': '缺少通知ID'}), 400

        notification_id = data['id']
        if remove_notification(notification_id):
            app_logger.info(f"删除价格通知成功: ID {notification_id}")
            return jsonify({'success': True})
        else:
            return jsonify({'error': '删除通知失败'}), 500

@notify_bp.route('/api/webhook', methods=['GET', 'POST'])
def manage_webhook():
    if request.method == 'GET':
        webhook_url = get_webhook_url()
        return jsonify({'webhook_url': webhook_url})

    elif request.method == 'POST':
        data = request.get_json()
        if not data or 'webhook_url' not in data:
            return jsonify({'error': '缺少webhook地址'}), 400

        webhook_url = data['webhook_url']
        if set_webhook_url(webhook_url):
            app_logger.info("设置webhook地址成功")
            return jsonify({'success': True})
        else:
            return jsonify({'error': '设置webhook地址失败'}), 500

@notify_bp.route('/api/notifications/check_now', methods=['POST'])
def manual_check_notifications():
    try:
        check_price_notifications(trading_hours_only=False)
        app_logger.info("手动触发价格通知检查完成")
        return jsonify({'success': True, 'message': '已触发检查，请稍后查看结果'})
    except Exception as e:
        app_logger.error(f"手动检查价格通知失败: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500