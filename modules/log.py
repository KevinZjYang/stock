# log.py
from flask import Blueprint, jsonify, make_response
import sys
import os
# 添加上级目录到路径，以便导入 models.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.models import app_logger, get_logs, clear_logs

log_bp = Blueprint('log', __name__)

@log_bp.route('/list', methods=['GET'])
def get_log_list():
    """获取日志列表"""
    from flask import request
    client_ip = request.remote_addr
    app_logger.info(f"获取系统日志请求来自: {client_ip}")
    logs = get_logs()
    app_logger.info(f"返回 {len(logs)} 条系统日志, IP: {client_ip}")
    return jsonify(logs)

@log_bp.route('/clear', methods=['POST'])
def clear_log_list():
    """清空日志"""
    from flask import request
    client_ip = request.remote_addr
    app_logger.info(f"清空系统日志请求来自: {client_ip}")
    clear_logs()
    app_logger.info(f"系统日志已清空, IP: {client_ip}")
    return jsonify({'success': True, 'message': '日志已清空'})