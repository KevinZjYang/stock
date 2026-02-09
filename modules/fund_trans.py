# fund_trans.py
from flask import Blueprint, request, jsonify, make_response, render_template, send_file
import sys
import os
import requests
import time
# 添加上级目录到路径，以便导入 models.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.models import (
    load_fund_transactions,
    import_excel_transactions, export_excel_transactions, app_logger,
    add_fund_transaction, update_fund_transaction, delete_fund_transaction, get_db_connection
)

fund_trans_bp = Blueprint('fund_trans', __name__)

def calculate_fund_summary(transactions):
    """计算基金交易汇总数据 - 改进版本，正确处理成本计算"""
    if not transactions:
        return {
            "total_shares": 0, "total_cost": 0, "realized_profit": 0,
            "dividend_total": 0, "buy_count": 0, "sell_count": 0,
            "dividend_count": 0, "trade_count": 0, "total_fee": 0,
            "market_value": 0  # 添加市值字段
        }

    # 按日期升序排序，确保先处理的买入/分红在卖出之前
    # 如果日期为空或无效，放在最后处理
    def get_sort_key(t):
        date_str = t.get('date', '')
        if not date_str:
            return float('inf')
        try:
            # 处理 YYYY/MM/DD HH:MM:SS 或 YYYY-MM-DD 格式
            # 先去掉时间部分，只保留日期
            date_str = date_str.split(' ')[0]  # 取日期部分
            date_str = date_str.replace('-', '/')
            parts = date_str.split('/')
            if len(parts) == 3:
                year, month, day = parts
                return int(year) * 10000 + int(month) * 100 + int(day)
        except:
            pass
        return float('inf')

    sorted_transactions = sorted(transactions, key=get_sort_key)

    # 调试日志：显示排序后的交易顺序
    app_logger.info(f"[市值计算] 排序后交易记录: {[(t.get('date'), t.get('type'), t.get('code')) for t in sorted_transactions]}")

    holdings = {}
    realized_profit = 0
    dividend_total = 0
    buy_count = 0
    sell_count = 0
    dividend_count = 0
    total_fee = 0

    for t in sorted_transactions:
        code = t.get('code')
        # 确保基金代码是6位格式，不足的前面补0
        formatted_code = str(code).zfill(6)
        t_type = t.get('type')

        shares = float(t.get('shares', 0)) if t.get('shares') is not None else 0
        amount = float(t.get('actual_amount', 0)) if t.get('actual_amount') is not None else 0
        fee = float(t.get('fee', 0)) if t.get('fee') is not None else 0

        total_fee += fee

        if t_type == '买入':
            buy_count += 1
            if formatted_code not in holdings:
                holdings[formatted_code] = {'shares': 0, 'cost': 0}

            holdings[formatted_code]['shares'] += shares
            # 买入时增加成本，成本为实际交易金额（手续费已包含在内）
            holdings[formatted_code]['cost'] += abs(amount)

        elif t_type == '卖出':
            sell_count += 1
            # 确保持仓记录存在，如果不存在则初始化为0
            if formatted_code not in holdings:
                holdings[formatted_code] = {'shares': 0, 'cost': 0}

            if holdings[formatted_code]['shares'] > 0:
                # 计算平均成本单价
                avg_cost_per_share = holdings[formatted_code]['cost'] / holdings[formatted_code]['shares']

                # 计算卖出份额对应的成本
                sell_cost = shares * avg_cost_per_share

                # 计算卖出收益（扣除手续费）
                sell_income = abs(amount) - fee

                # 计算已实现盈亏
                realized_profit += (sell_income - sell_cost)

                # 减少持仓份额和对应成本
                holdings[formatted_code]['shares'] -= shares
                holdings[formatted_code]['cost'] -= sell_cost

                if holdings[formatted_code]['shares'] <= 0.0001:
                    del holdings[formatted_code]
            elif holdings[formatted_code]['shares'] < 0:
                # 份额已经为负数，说明卖出超过持仓，这种异常情况需要特殊处理
                # 只计算已实现盈亏，不修改持仓数据
                avg_cost_per_share = abs(holdings[formatted_code]['cost'] / holdings[formatted_code]['shares'])
                sell_cost = shares * avg_cost_per_share
                sell_income = abs(amount) - fee
                realized_profit += (sell_income - sell_cost)

        elif t_type == '分红':
            dividend_count += 1
            dividend_total += abs(amount)
            # 分红处理：判断是现金分红还是分红再投资
            # 如果 shares > 0 且 actual_amount > 0，视为分红再投资
            if shares > 0:
                # 分红再投资：增加持仓份额和成本
                if formatted_code not in holdings:
                    holdings[formatted_code] = {'shares': 0, 'cost': 0}
                holdings[formatted_code]['shares'] += shares
                holdings[formatted_code]['cost'] += abs(amount)
            else:
                # 现金分红：计入已实现盈亏，不影响持仓成本
                realized_profit += abs(amount)

    total_shares = sum(h['shares'] for h in holdings.values())
    # 持仓成本总额 = 所有持仓基金的成本之和
    total_cost = sum(h['cost'] for h in holdings.values())
    total_cost = abs(total_cost)

    app_logger.info(f"[市值计算] 当前持仓: {holdings}")

    # 计算持仓市值：获取持有基金的实时净值并计算总市值
    market_value = 0
    if holdings:
        # 获取所有持有基金的代码（已经是6位格式）
        holding_codes = list(holdings.keys())
        app_logger.info(f"[市值计算] 持有基金代码: {holding_codes}")
        if holding_codes:
            # 获取基金的实时净值（holding_codes已经是6位格式）
            fund_prices = fetch_fund_price_batch_sync(holding_codes)
            app_logger.info(f"[市值计算] API返回基金数量: {len(fund_prices)}")
            if fund_prices:
                # 根据每只基金的持有份额和当前净值计算市值
                for fund_data in fund_prices:
                    code = fund_data.get('code')
                    app_logger.info(f"[市值计算] 尝试匹配基金代码: {code}")
                    # 由于holdings中的键已经是6位格式，直接匹配即可
                    if code in holdings:
                        # 使用估算净值(expectWorth)或单位净值(netWorth)，优先使用估算净值
                        current_net_worth = fund_data.get('expectWorth') or fund_data.get('netWorth')
                        if current_net_worth:
                            holding_shares = holdings[code]['shares']
                            fund_market_value = holding_shares * current_net_worth
                            app_logger.info(f"[市值计算] {code}: 份额={holding_shares}, 净值={current_net_worth}, 市值={fund_market_value}")
                            market_value += fund_market_value
                        else:
                            app_logger.warning(f"未能获取基金 {code} 的净值数据，跳过市值计算")
                    else:
                        app_logger.warning(f"返回的基金代码 '{code}' 在持仓中找不到匹配项，持仓代码: {holding_codes}")
            else:
                app_logger.warning(f"未能获取基金净值数据，持有基金数量: {len(holding_codes)}, 基金代码: {holding_codes}")
    else:
        app_logger.info("当前无持仓，市值为0")

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

def fetch_fund_price_batch_sync(codes):
    """同步获取多个基金的价格数据 - 从models.py复制过来"""
    try:
        if not isinstance(codes, list):
            codes = [codes]

        # 确保基金代码是6位格式，不足的前面补0
        formatted_codes = []
        for code in codes:
            formatted_code = str(code).zfill(6)  # 补齐到6位
            formatted_codes.append(formatted_code)

        code_str = ','.join(formatted_codes)
        today = time.strftime('%Y-%m-%d')
        params = {'code': code_str, 'startDate': today}
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

        app_logger.info(f"开始批量获取基金数据: 数量={len(codes)}, 代码={code_str}")

        start_time = time.time()
        response = requests.get('https://api.autostock.cn/v1/fund/detail/list', params=params, headers=headers, timeout=20)
        response_time = time.time() - start_time

        app_logger.info(f"基金API响应时间: {response_time:.2f}s, 状态码: {response.status_code}, 请求代码: {code_str}")

        response.raise_for_status()

        data = response.json()

        app_logger.info(f"基金API返回的原始数据结构: {list(data.keys()) if isinstance(data, dict) else type(data)}")

        if not data:
            app_logger.error(f"基金API返回数据为空: {code_str}")
            return []

        # 检查数据结构，可能API返回的格式与预期不同
        if 'data' not in data:
            app_logger.error(f"基金API返回数据中没有 'data' 字段，实际返回: {data}")

            # 检查是否是错误响应
            if data.get('code') == 500 or data.get('code') == 400:
                app_logger.error(f"基金API返回错误: {data.get('message', '未知错误')}, traceId: {data.get('traceId')}")
                return []  # 返回空列表，表示无法获取数据

            # 尝试其他可能的字段名
            possible_data_fields = ['result', 'list', 'items', 'funds', 'records', 'Data', 'RESULT', 'LIST']
            for field in possible_data_fields:
                if field in data:
                    app_logger.info(f"使用替代字段 '{field}' 作为数据源")
                    data['data'] = data[field]
                    break

        # 再次检查，如果还是没有data字段，尝试其他可能的数据格式
        if 'data' not in data:
            # 检查是否直接返回了数组
            if isinstance(data, list):
                app_logger.info("API直接返回了数组格式，将其作为数据源")
                data = {'data': data}
            elif isinstance(data, dict) and len(data) == 1:
                # 如果只有一个键值对，可能那个值就是数据
                first_key = next(iter(data))
                if isinstance(data[first_key], list):
                    app_logger.info(f"使用唯一键 '{first_key}' 的值作为数据源")
                    data = {'data': data[first_key]}
            else:
                app_logger.error(f"基金API返回数据格式错误，缺少数据字段: {code_str}, 返回: {data}")
                return []

        def to_float(value):
            if value is None: return None
            try:
                if isinstance(value, str): value = value.replace('%', '').strip()
                return float(value)
            except (ValueError, TypeError): return None

        # 创建一个字典来存储API返回的数据，以便快速查找
        api_data_dict = {}
        for fund_data in data['data']:
            # 确保基金代码是6位格式，与holdings中的键保持一致
            raw_code = str(fund_data.get('code', ''))
            formatted_code = raw_code.zfill(6)  # 补齐到6位
            fund_info = {
                'code': formatted_code,
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
            api_data_dict[formatted_code] = fund_info

        # 确保返回的数据包含所有请求的基金代码，对于API未返回的基金，返回默认值
        fund_data_list = []
        for code in codes:
            if code in api_data_dict:
                fund_data_list.append(api_data_dict[code])
            else:
                # 如果API没有返回该基金的数据，返回一个默认结构
                fund_info = {
                    'code': code,
                    'name': '--',
                    'type': 'fund',
                    'netWorth': None,
                    'expectWorth': None,
                    'totalWorth': None,
                    'expectGrowth': None,
                    'dayGrowth': None,
                    'lastWeekGrowth': None,
                    'lastMonthGrowth': None,
                    'lastThreeMonthsGrowth': None,
                    'lastSixMonthsGrowth': None,
                    'lastYearGrowth': None,
                    'buyMin': None,
                    'buySourceRate': None,
                    'buyRate': None,
                    'manager': None,
                    'fundScale': None,
                    'netWorthDate': None,
                    'expectWorthDate': None,
                    'netWorthDisplay': '--',
                    'expectWorthDisplay': '--'
                }
                fund_data_list.append(fund_info)

        return fund_data_list

    except requests.exceptions.Timeout:
        app_logger.error(f"批量获取基金错误: 请求超时 (20秒)")
        return []
    except Exception as e:
        app_logger.error(f"批量获取基金错误: {e}")
        return []

@fund_trans_bp.route('/detail_page')
def fund_trans_detail_page():
    return render_template('fund_trans_detail.html')

def fund_trans_page():
    return render_template('fund_trans_detail.html')

@fund_trans_bp.route('/transactions', methods=['GET', 'POST', 'PUT', 'DELETE'])
def manage_transactions():
    client_ip = request.remote_addr

    if request.method == 'GET':
        app_logger.info(f"获取基金交易记录请求来自: {client_ip}")
        transactions = load_fund_transactions()
        summary = calculate_fund_summary(transactions)

        response = make_response(jsonify({
            'transactions': transactions,
            'summary': summary
        }))
        app_logger.info(f"返回基金交易记录，共 {len(transactions)} 条记录, IP: {client_ip}")

    elif request.method == 'POST':
        app_logger.info(f"添加基金交易记录请求来自: {client_ip}")
        data = request.get_json()
        if not data:
            app_logger.warning(f"添加基金交易记录失败: 缺少数据, IP: {client_ip}")
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

            app_logger.info(f"成功添加基金交易记录: ID {transaction_id}, 代码: {data.get('code', 'N/A')}, IP: {client_ip}")
            response = make_response(jsonify({'success': True, 'transaction': new_transaction}))
        else:
            app_logger.error(f"保存基金交易记录失败, IP: {client_ip}")
            return jsonify({'error': '保存失败'}), 500

    elif request.method == 'PUT':  # 更新交易记录
        app_logger.info(f"更新基金交易记录请求来自: {client_ip}")
        data = request.get_json()
        if not data or 'id' not in data:
            app_logger.warning(f"更新基金交易记录失败: 缺少ID, IP: {client_ip}")
            return jsonify({'error': '缺少ID'}), 400

        transaction_id = data['id']
        success = update_fund_transaction(transaction_id, data)
        if success:
            app_logger.info(f"成功更新基金交易记录: ID {transaction_id}, IP: {client_ip}")
            response = make_response(jsonify({'success': True}))
        else:
            app_logger.error(f"更新基金交易记录失败: ID {transaction_id}, IP: {client_ip}")
            return jsonify({'error': '更新失败'}), 500

    elif request.method == 'DELETE':
        app_logger.info(f"删除基金交易记录请求来自: {client_ip}")
        data = request.get_json()
        if not data:
            app_logger.warning(f"删除基金交易记录失败: 缺少数据, IP: {client_ip}")
            return jsonify({'error': '缺少数据'}), 400

        # 检查是否是清空所有记录的请求
        if data.get('clear_all'):
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('DELETE FROM fund_transactions')
            conn.commit()
            conn.close()
            app_logger.info(f"清空所有基金交易记录成功, IP: {client_ip}")
            return jsonify({'success': True})

        # 否则是删除特定记录
        if 'id' not in data:
            app_logger.warning(f"删除基金交易记录失败: 缺少ID, IP: {client_ip}")
            return jsonify({'error': '缺少ID'}), 400

        transaction_id = data['id']
        success = delete_fund_transaction(transaction_id)
        if success:
            app_logger.info(f"成功删除基金交易记录: ID {transaction_id}, IP: {client_ip}")
            response = make_response(jsonify({'success': True}))
        else:
            app_logger.warning(f"删除基金交易记录失败: ID {transaction_id} 不存在, IP: {client_ip}")
            return jsonify({'error': '记录不存在'}), 400

    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@fund_trans_bp.route('/summary', methods=['GET'])
def get_summary():
    transactions = load_fund_transactions()
    summary = calculate_fund_summary(transactions)

    response = make_response(jsonify(summary))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@fund_trans_bp.route('/import', methods=['POST'])
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

@fund_trans_bp.route('/export', methods=['GET'])
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
