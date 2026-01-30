# stock.py
from flask import Blueprint, request, jsonify, make_response
import sys
import os
# 添加上级目录到路径，以便导入 app.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import (
    load_stock_watchlist, add_stock_to_watchlist, remove_stock_from_watchlist,
    search_stock_by_code, get_stock_realtime_data, get_stock_realtime_data_batch,
    app_logger, get_db_connection, set_setting
)
import json
import sqlite3


stock_bp = Blueprint('stock', __name__)

@stock_bp.route('/watchlist', methods=['GET', 'POST', 'DELETE'])
def manage_watchlist():
    if request.method == 'GET':
        app_logger.info(f"获取股票关注列表请求来自: {request.remote_addr}")
        watchlist = load_stock_watchlist()
        response = make_response(jsonify({'watchlist': watchlist}))
        app_logger.info(f"返回股票关注列表，共 {len(watchlist)} 个项目")

    elif request.method == 'POST':
        # 添加调试信息
        app_logger.info(f"添加股票到关注列表请求来自: {request.remote_addr}")
        app_logger.debug(f"接收到的请求数据: {request.data}")
        app_logger.debug(f"请求头: {request.headers}")

        data = request.get_json()
        if not data:
            app_logger.error(f"请求体为空或无法解析JSON: {request.data}")
            return jsonify({'error': '缺少请求数据或JSON格式错误'}), 400

        app_logger.debug(f"解析后的数据: {data}")

        # 尝试从code或symbol字段获取代码
        code = None
        if isinstance(data, dict):
            if 'code' in data:
                code = data['code']
                app_logger.debug(f"从code字段获取代码: {code}")
            elif 'symbol' in data:  # 兼容旧版本前端
                code = data['symbol']
                app_logger.debug(f"从symbol字段获取代码: {code}")
        else:
            app_logger.error(f"数据格式错误，期望字典类型，实际类型: {type(data)}")
            return jsonify({'error': '数据格式错误'}), 400

        if not code:
            app_logger.warning(f"未找到股票代码，数据内容: {data}")
            return jsonify({'error': '缺少股票代码'}), 400

        # 确保代码是字符串并去除空白
        code = str(code).strip()
        if not code:
            app_logger.warning(f"股票代码为空字符串")
            return jsonify({'error': '股票代码不能为空'}), 400

        # 获取名称和类型参数（如果提供）
        name = data.get('name', '')
        type_val = data.get('type', '')

        if add_stock_to_watchlist(code, name, type_val):
            app_logger.info(f"成功添加股票到关注列表: {code}")
            # 返回更新后的关注列表
            updated_watchlist = load_stock_watchlist()
            response = make_response(jsonify({'watchlist': updated_watchlist, 'success': True, 'code': code}))
        else:
            app_logger.warning(f"股票已在关注列表中，无法重复添加: {code}")
            return jsonify({'error': '股票已在关注列表中'}), 400

    elif request.method == 'DELETE':
        app_logger.info(f"从关注列表移除股票请求来自: {request.remote_addr}")
        data = request.get_json()
        if not data:
            app_logger.error(f"DELETE请求体为空或无法解析JSON: {request.data}")
            return jsonify({'error': '缺少请求数据或JSON格式错误'}), 400

        if not isinstance(data, dict) or 'code' not in data:
            app_logger.warning(f"DELETE请求缺少code字段，数据内容: {data}")
            return jsonify({'error': '缺少股票代码'}), 400

        code = str(data['code']).strip()
        if not code:
            app_logger.warning(f"DELETE请求中股票代码为空")
            return jsonify({'error': '股票代码不能为空'}), 400

        if remove_stock_from_watchlist(code):
            app_logger.info(f"成功从关注列表移除股票: {code}")
            response = make_response(jsonify({'success': True, 'code': code}))
        else:
            app_logger.warning(f"股票不在关注列表中，无法移除: {code}")
            return jsonify({'error': '股票不在关注列表中'}), 400

    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@stock_bp.route('/search', methods=['GET'])
def search_stock():
    code = request.args.get('code', '').strip()
    client_ip = request.remote_addr
    app_logger.info(f"股票搜索请求来自: {client_ip}, 代码: {code}")

    if not code:
        app_logger.warning(f"股票搜索失败: 缺少股票代码, IP: {client_ip}")
        return jsonify({'error': '缺少股票代码'}), 400

    # 在数据库中搜索
    db_results = search_stock_by_code(code)

    # 从API获取实时数据
    realtime_data = get_stock_realtime_data(code)

    app_logger.info(f"股票搜索完成: {code}, 结果数量: DB={len(db_results)}, 实时数据={'有' if realtime_data else '无'}, IP: {client_ip}")

    response = make_response(jsonify({
        'excel_results': db_results,  # 现在是从数据库获取的股票数据
        'realtime_data': realtime_data
    }))

    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@stock_bp.route('/detail/<code>', methods=['GET'])
def get_stock_detail(code):
    client_ip = request.remote_addr
    app_logger.info(f"获取股票详情请求来自: {client_ip}, 代码: {code}")

    # 在数据库中搜索
    db_results = search_stock_by_code(code)

    # 从API获取实时数据
    realtime_data = get_stock_realtime_data(code)

    app_logger.info(f"股票详情获取完成: {code}, 结果数量: DB={len(db_results)}, 实时数据={'有' if realtime_data else '无'}, IP: {client_ip}")

    response = make_response(jsonify({
        'excel_results': db_results,  # 现在是从数据库获取的股票数据
        'realtime_data': realtime_data
    }))

    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@stock_bp.route('/watchlist/detail', methods=['GET'])
def get_watchlist_detail():
    watchlist = load_stock_watchlist()

    if not watchlist:
        return jsonify({'watchlist_details': []})

    # 收集所有股票代码，然后批量获取
    codes = [item['code'] for item in watchlist]
    realtime_data_list = get_stock_realtime_data_batch(codes)

    # 将批量获取的数据与数据库数据合并
    realtime_data_map = {data['symbol']: data for data in realtime_data_list}

    watchlist_details = []
    for item in watchlist:
        code = item['code']
        # 在数据库中搜索
        db_results = search_stock_by_code(code)

        # 从批量获取的数据中获取实时数据
        realtime_data = realtime_data_map.get(code)

        detail = {
            'code': code,
            'name': item.get('name', ''),
            'type': item.get('type', ''),
            'excel_results': db_results,  # 现在是从数据库获取的股票数据
            'realtime_data': realtime_data
        }
        watchlist_details.append(detail)

    response = make_response(jsonify({'watchlist_details': watchlist_details}))

    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@stock_bp.route('/prices', methods=['GET'])
def get_stock_prices():
    client_ip = request.remote_addr
    app_logger.info(f"获取股票价格请求来自: {client_ip}")

    watchlist = load_stock_watchlist()
    if not watchlist:
        app_logger.info(f"股票关注列表为空, IP: {client_ip}")
        return jsonify([])

    # 收集所有股票代码，然后批量获取
    symbols = [item['code'] for item in watchlist]
    app_logger.info(f"获取 {len(symbols)} 个股票的价格, IP: {client_ip}")

    price_data_list = get_stock_realtime_data_batch(symbols)

    app_logger.info(f"返回 {len(price_data_list)} 个股票价格数据, IP: {client_ip}")
    return jsonify(price_data_list)

@stock_bp.route('/prices_batch', methods=['GET'])
def get_stock_prices_batch():
    symbols = request.args.get('symbols', '').strip()
    if not symbols:
        return jsonify({'error': '缺少股票代码列表'}), 400

    # 分割符号列表
    symbol_list = [s.strip() for s in symbols.split(',') if s.strip()]

    if not symbol_list:
        return jsonify([])

    price_data_list = []
    for symbol in symbol_list:
        # 从API获取实时数据
        realtime_data = get_stock_realtime_data(symbol)
        if realtime_data:
            price_data_list.append(realtime_data)

    return jsonify(price_data_list)

@stock_bp.route('/index_config', methods=['GET', 'POST'])
def get_set_index_config():
    if request.method == 'GET':
        # 获取当前配置的指数列表
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'index_display_config'")
        row = cursor.fetchone()
        conn.close()

        if row:
            import json
            config = json.loads(row['value'])
            return jsonify(config)
        else:
            # 默认配置
            default_config = {
                'enabled_indices': [
                    {'code': 'SH000001', 'name': '上证指数'},
                    {'code': 'SZ399001', 'name': '深证成指'},
                    {'code': 'SZ399006', 'name': '创业板指'}
                ]
            }
            return jsonify(default_config)

    elif request.method == 'POST':
        # 设置指数配置
        data = request.get_json()
        if not data or 'enabled_indices' not in data:
            return jsonify({'error': '缺少指数配置数据'}), 400

        import json
        config_json = json.dumps(data)

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES ('index_display_config', ?, CURRENT_TIMESTAMP)
            """, (config_json,))
            conn.commit()
            conn.close()
            return jsonify({'success': True})
        except Exception as e:
            conn.close()
            return jsonify({'error': str(e)}), 500

@stock_bp.route('/index_prices', methods=['GET'])
def get_index_prices():
    # 获取配置的指数列表
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'index_display_config'")
    row = cursor.fetchone()
    conn.close()

    if row:
        import json
        config = json.loads(row['value'])
        index_codes = [item['code'] for item in config.get('enabled_indices', [])]
    else:
        # 默认显示上证指数、深证成指和创业板指
        index_codes = ['SH000001', 'SZ399001', 'SZ399006']

    # 批量获取指数数据
    price_data_list = get_stock_realtime_data_batch(index_codes)

    # 按照设置的顺序重新排序数据
    price_data_map = {item['symbol']: item for item in price_data_list}
    ordered_data = [price_data_map[code] for code in index_codes if code in price_data_map]

    return jsonify(ordered_data)


@stock_bp.route('/settings', methods=['GET', 'POST'])
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
        app_logger.info("获取股票设置")
        return jsonify(settings)

    elif request.method == 'POST':
        data = request.get_json()
        if not data:
            app_logger.warning("尝试保存股票设置但缺少数据")
            return jsonify({'error': '缺少数据'}), 400

        for key, value in data.items():
            if not set_setting(key, value):
                app_logger.error("保存股票设置失败")
                return jsonify({'error': '保存设置失败'}), 500

        app_logger.info(f"保存股票设置成功: {data}")
        return jsonify({'success': True, 'settings': data})


@stock_bp.route('/batch_data', methods=['GET'])
def get_batch_data():
    """批量获取指数和股票数据"""
    # 获取配置的指数列表
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'index_display_config'")
    row = cursor.fetchone()

    if row:
        import json
        config = json.loads(row['value'])
        index_codes = [item['code'] for item in config.get('enabled_indices', [])]
    else:
        # 默认显示上证指数、深证成指和创业板指
        index_codes = ['SH000001', 'SZ399001', 'SZ399006']

    # 获取股票关注列表
    # 由于我们已经修改了load_stock_watchlist函数，这里直接使用它
    conn.close()
    stock_list = load_stock_watchlist()
    stock_codes = [item['code'] for item in stock_list]

    # 合并所有代码
    all_codes = index_codes + stock_codes

    # 批量获取所有数据
    price_data_list = get_stock_realtime_data_batch(all_codes)

    # 按照设置的顺序重新排序指数数据
    price_data_map = {item['symbol']: item for item in price_data_list}
    index_data = [price_data_map[code] for code in index_codes if code in price_data_map]
    stock_data = [item for item in price_data_list if item['symbol'] in stock_codes]

    return jsonify({
        'index_data': index_data,
        'stock_data': stock_data
    })
