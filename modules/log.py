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
    # 不再记录日志获取请求，避免循环
    logs = get_logs()
    return jsonify(logs)

@log_bp.route('/clear', methods=['POST'])
def clear_log_list():
    """清空日志"""
    from flask import request
    client_ip = request.remote_addr
    # 不再记录日志清除请求，避免循环
    clear_logs()
    return jsonify({'success': True, 'message': '日志已清空'})