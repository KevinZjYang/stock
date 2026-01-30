# notify.py
from flask import Blueprint, request, jsonify, render_template, make_response
import sys
import os
# 添加上级目录到路径，以便导入 app.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import (
    init_notification_db, add_price_notification, get_price_notifications,
    remove_notification, set_webhook_url, get_webhook_url,
    check_price_notifications, notification_monitor, app_logger, get_db_connection
)
import threading
import time
from datetime import datetime
import requests as req

notify_bp = Blueprint('notify', __name__)

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