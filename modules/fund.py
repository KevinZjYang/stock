# fund.py
from flask import Blueprint, request, jsonify, make_response
import sys
import os
# 添加上级目录到路径，以便导入 app.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import (
    load_fund_watchlist, fetch_fund_price_batch_sync,
    CACHE_EXPIRY, get_setting, set_setting, app_logger
)
import time

fund_bp = Blueprint('fund', __name__)

# 缓存
data_cache = {'funds': None, 'last_update': 0}

@fund_bp.route('/settings', methods=['GET', 'POST'])
def manage_settings():
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

@fund_bp.route('/detail', methods=['GET'])
def get_fund_detail():
    code = request.args.get('code')
    client_ip = request.remote_addr
    app_logger.info(f"获取基金详情请求来自: {client_ip}, 基金代码: {code}")

    if not code:
        app_logger.warning(f"获取基金详情失败: 缺少基金代码, IP: {client_ip}")
        return jsonify({'error': '缺少基金代码'}), 400

    try:
        fund_data_list = fetch_fund_price_batch_sync([code])

        if fund_data_list:
            app_logger.info(f"成功获取基金详情: {code}, IP: {client_ip}")
            return jsonify(fund_data_list[0])
        else:
            app_logger.warning(f"未找到基金详情: {code}, IP: {client_ip}")
            return jsonify({'error': '未找到该基金数据'}), 404

    except Exception as e:
        app_logger.error(f"获取基金详情错误: {code}, IP: {client_ip}, 错误: {e}")
        return jsonify({'error': f'获取基金数据失败: {str(e)}'}), 500

@fund_bp.route('/watchlist', methods=['GET', 'POST', 'DELETE'])
def manage_fund_watchlist():
    if request.method == 'GET':
        watchlist = load_fund_watchlist()
        response = make_response(jsonify(watchlist))

    elif request.method == 'POST':
        data = request.get_json()
        if not data or 'code' not in data:
            app_logger.warning("添加基金关注列表失败: 缺少基金代码")
            return jsonify({'error': '缺少基金代码'}), 400

        code = data['code'].strip()
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO fund_watchlist (code) VALUES (?)', (code,))
            conn.commit()
            conn.close()
            data_cache['funds'] = None
            app_logger.info(f"添加基金关注列表成功: {code}")

            # 返回更新后的列表
            watchlist = load_fund_watchlist()
            response = make_response(jsonify({'watchlist': watchlist}))
        except sqlite3.IntegrityError:
            conn.close()
            app_logger.warning(f"添加基金关注列表失败: {code} 已存在")
            return jsonify({'error': f'{code} 已在关注列表中'}), 400
        except Exception as e:
            conn.close()
            app_logger.error(f"添加基金关注列表失败: {e}")
            return jsonify({'error': '保存到服务器失败'}), 500

    elif request.method == 'DELETE':
        data = request.get_json()
        if not data or 'code' not in data:
            app_logger.warning("删除基金关注列表失败: 缺少基金代码")
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
            app_logger.info(f"删除基金关注列表成功: {code}")

            # 返回更新后的列表
            watchlist = load_fund_watchlist()
            response = make_response(jsonify({'watchlist': watchlist}))
        else:
            conn.close()
            app_logger.warning(f"删除基金关注列表失败: {code} 不存在")
            return jsonify({'error': f'{code} 不在关注列表中'}), 400

    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@fund_bp.route('/prices', methods=['GET'])
def get_fund_prices():
    current_time = time.time()
    if data_cache['funds'] and (current_time - data_cache['last_update'] < CACHE_EXPIRY):
        app_logger.info("获取基金价格: 使用缓存")
        response = make_response(jsonify(data_cache['funds']))
    else:
        watchlist = load_fund_watchlist()
        if not watchlist:
            app_logger.info("获取基金价格: 关注列表为空")
            response = make_response(jsonify([]))
        else:
            app_logger.info(f"获取基金价格: 批量获取 {len(watchlist)} 个基金")
            fund_data_list = fetch_fund_price_batch_sync(watchlist)
            data_cache['funds'] = fund_data_list
            data_cache['last_update'] = current_time
            response = make_response(jsonify(fund_data_list))

    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response
