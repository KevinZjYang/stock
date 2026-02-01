# fund.py
from flask import Blueprint, request, jsonify, make_response, render_template
from datetime import datetime, timedelta
import sys
import os
import requests
import time
import sqlite3
from typing import List, Dict, Any
# 添加上级目录到路径，以便导入 models.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.models import (
    load_fund_watchlist, fetch_fund_price_batch_sync,
    CACHE_EXPIRY, get_setting, set_setting, app_logger, get_db_connection
)

fund_bp = Blueprint('fund', __name__)

def search_fund(query: str) -> List[Dict[str, Any]]:
    """
    搜索基金
    直接通过API获取基金信息
    """
    results = []

    # 基金代码通常是6位数字
    fund_codes = []

    # 如果查询是6位数字，直接当作基金代码尝试
    if query.isdigit() and len(query) == 6:
        fund_codes.append(query)
    # 如果查询是5位数字，在前面补0
    elif query.isdigit() and len(query) == 5:
        fund_codes.append(f"0{query}")

    # 如果没有找到可能的基金代码，返回空列表
    if not fund_codes:
        return []

    # 尝试获取基金信息
    # 从app.py导入fetch_fund_price_batch_sync函数
    from app import fetch_fund_price_batch_sync
    fund_data_list = fetch_fund_price_batch_sync(fund_codes)

    # 格式化结果以匹配股票搜索的格式
    for fund_data in fund_data_list:
        results.append({
            'code': fund_data.get('code', ''),
            'name': fund_data.get('name', ''),
            'type': 'fund'
        })

    return results

def load_all_funds_to_db():
    """从API获取所有基金基础数据并保存到数据库"""
    try:
        app_logger.info("开始获取所有基金基础数据...")
        response = requests.get('https://api.autostock.cn/v1/fund/all', timeout=30)
        response.raise_for_status()
        data = response.json()

        if data.get('code') != 200:
            app_logger.error(f"获取基金基础数据失败: {data.get('message', '未知错误')}")
            return False

        funds_data = data.get('data', [])
        if not funds_data:
            app_logger.warning("获取到的基金数据为空")
            return False

        conn = get_db_connection()
        cursor = conn.cursor()

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

        # 插入或更新基金数据
        inserted_count = 0
        for fund in funds_data:
            if len(fund) >= 5:  # 确保有足够的字段
                code = fund[0]
                pinyin = fund[1]
                name = fund[2]
                fund_type = fund[3]
                full_pinyin = fund[4]

                try:
                    cursor.execute('''
                        INSERT OR REPLACE INTO fund_base_data
                        (code, pinyin, name, type, full_pinyin)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (code, pinyin, name, fund_type, full_pinyin))
                    inserted_count += 1
                except Exception as e:
                    app_logger.error(f"插入基金数据失败 {code}: {e}")

        conn.commit()
        conn.close()

        app_logger.info(f"成功获取并保存 {inserted_count} 条基金基础数据")
        return True

    except Exception as e:
        app_logger.error(f"获取基金基础数据时发生错误: {e}")
        return False

@fund_bp.route('/detail_page')
def fund_detail_page():
    return render_template('fund_detail.html')

def fund_page():
    return render_template('fund_detail.html')

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

@fund_bp.route('/list', methods=['GET'])
def get_all_indices_main():
    """获取所有指数列表"""
    from modules.models import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT code, name FROM stocks WHERE market_name = "大盘指数" OR code IN ("000001", "399001", "399006") ORDER BY code')
    indices = [{'code': row['code'], 'name': row['name']} for row in cursor.fetchall()]
    conn.close()
    return jsonify(indices)

@fund_bp.route('/watchlist', methods=['GET', 'POST', 'DELETE'])
def manage_fund_watchlist_main():
    """管理基金关注列表"""
    from modules.models import (
        load_fund_watchlist, add_fund_to_watchlist, remove_fund_from_watchlist
    )

    if request.method == 'GET':
        watchlist = load_fund_watchlist()
        return jsonify(watchlist)

    elif request.method == 'POST':
        data = request.get_json()
        if not data or 'code' not in data:
            return jsonify({'error': '缺少基金代码'}), 400

        code = data['code'].strip()
        if add_fund_to_watchlist(code):
            app_logger.info(f"添加基金到关注列表: {code}")
            watchlist = load_fund_watchlist()  # 返回更新后的列表
            return jsonify({'watchlist': watchlist})
        else:
            app_logger.warning(f"添加基金失败，不是有效的基金代码: {code}")
            return jsonify({'error': '不是有效的基金代码'}), 400

    elif request.method == 'DELETE':
        data = request.get_json()
        if not data or 'code' not in data:
            return jsonify({'error': '缺少基金代码'}), 400

        code = data['code'].strip()
        if remove_fund_from_watchlist(code):
            app_logger.info(f"从基金关注列表移除: {code}")
            watchlist = load_fund_watchlist()  # 返回更新后的列表
            return jsonify({'watchlist': watchlist})
        else:
            app_logger.warning(f"移除基金失败，基金不在关注列表中: {code}")
            return jsonify({'error': '基金不在关注列表中'}), 400

@fund_bp.route('/index/watchlist', methods=['GET', 'POST', 'DELETE'])
def manage_index_watchlist_main():
    """管理指数关注列表"""
    from modules.models import (
        load_index_watchlist, add_index_to_watchlist, remove_index_from_watchlist
    )

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

@fund_bp.route('/init_all_funds', methods=['GET'])
def init_all_funds():
    """初始化所有基金基础数据"""
    client_ip = request.remote_addr
    app_logger.info(f"初始化所有基金数据请求来自: {client_ip}")

    try:
        success = load_all_funds_to_db()
        if success:
            app_logger.info("基金基础数据初始化成功")
            return jsonify({'success': True, 'message': '基金基础数据初始化成功'})
        else:
            app_logger.error("基金基础数据初始化失败")
            return jsonify({'success': False, 'message': '基金基础数据初始化失败'}), 500
    except Exception as e:
        app_logger.error(f"初始化基金基础数据时发生错误: {e}")
        return jsonify({'success': False, 'message': f'初始化基金基础数据时发生错误: {str(e)}'}), 500

@fund_bp.route('/search', methods=['GET'])
def search_fund_route():
    query = request.args.get('q', '').strip()
    client_ip = request.remote_addr
    app_logger.info(f"基金搜索请求来自: {client_ip}, 查询: {query}")

    if not query:
        app_logger.warning(f"基金搜索失败: 缺少查询参数, IP: {client_ip}")
        return jsonify({'error': '缺少查询参数'}), 400

    try:
        results = search_fund(query)
        app_logger.info(f"基金搜索完成: {query}, 结果数量: {len(results)}, IP: {client_ip}")
        return jsonify(results)
    except Exception as e:
        app_logger.error(f"基金搜索错误: {query}, IP: {client_ip}, 错误: {e}")
        return jsonify({'error': f'搜索基金失败: {str(e)}'}), 500

@fund_bp.route('/detail', methods=['GET'])
def get_fund_detail():
    code = request.args.get('code')
    start_date = request.args.get('startDate')
    end_date = request.args.get('endDate')
    client_ip = request.remote_addr
    app_logger.info(f"获取基金详情请求来自: {client_ip}, 基金代码: {code}, 开始日期: {start_date}, 结束日期: {end_date}")

    if not code:
        app_logger.warning(f"获取基金详情失败: 缺少基金代码, IP: {client_ip}")
        return jsonify({'error': '缺少基金代码'}), 400

    # 设置默认日期范围：startDate默认为一个月前，endDate为当前时间
    if not start_date or not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date_obj = datetime.now() - timedelta(days=30)
        start_date = start_date_obj.strftime('%Y-%m-%d')
        app_logger.info(f"使用默认日期范围: startDate={start_date}, endDate={end_date}")

    try:
        # 使用fetch_fund_price_batch_sync函数获取基础数据
        fund_data_list = fetch_fund_price_batch_sync([code])

        if fund_data_list:
            fund_detail = fund_data_list[0]

            # 从基金详情API获取完整的基金数据，包括净值走势图
            # 根据API文档，使用正确的API端点
            detail_api_url = 'https://api.autostock.cn/v1/fund/detail/list'
            params = {'code': code, 'startDate': start_date, 'endDate': end_date}
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            app_logger.info(f"请求基金详情数据，基金代码: {code}")
            app_logger.info(f"请求URL: https://api.autostock.cn/v1/fund/detail/list 参数: {params}")

            try:
                detail_response = requests.get('https://api.autostock.cn/v1/fund/detail/list', params=params, headers=headers, timeout=30)
                detail_response.raise_for_status()
                detail_response_data = detail_response.json()

                app_logger.info(f"基金详情API响应: {detail_response_data.get('code', 'NO_CODE')}")

                if detail_response_data.get('code') == 0 and detail_response_data.get('data'):
                    fund_detail_data = detail_response_data['data'][0]

                    # 添加净值走势图数据
                    net_worth_data = fund_detail_data.get('netWorthData', [])
                    total_net_worth_data = fund_detail_data.get('totalNetWorthData', [])

                    app_logger.info(f"获取到净值数据条数: {len(net_worth_data)}, 累计净值数据条数: {len(total_net_worth_data)}")

                    # 将净值走势图数据添加到返回的数据中
                    fund_detail['netWorthData'] = net_worth_data
                    fund_detail['totalNetWorthData'] = total_net_worth_data

                    # 如果是货币基金，也添加相关数据
                    if 'millionCopiesIncomeData' in fund_detail_data:
                        fund_detail['millionCopiesIncomeData'] = fund_detail_data.get('millionCopiesIncomeData', [])
                        fund_detail['sevenDaysYearIncomeData'] = fund_detail_data.get('sevenDaysYearIncomeData', [])
                else:
                    # 如果API调用失败，仍然返回基本数据
                    app_logger.warning(f"获取基金详细数据失败: {code}, 但返回基本数据")
                    app_logger.warning(f"API响应: {detail_response_data}")
                    fund_detail['netWorthData'] = []
                    fund_detail['totalNetWorthData'] = []
            except requests.exceptions.RequestException as e:
                app_logger.error(f"请求基金详情API失败: {e}")
                fund_detail['netWorthData'] = []
                fund_detail['totalNetWorthData'] = []
            except ValueError as e:  # JSON解析错误
                app_logger.error(f"解析基金详情API响应失败: {e}")
                fund_detail['netWorthData'] = []
                fund_detail['totalNetWorthData'] = []

            app_logger.info(f"成功获取基金详情: {code}, IP: {request.remote_addr}")
            return jsonify(fund_detail)
        else:
            app_logger.warning(f"未找到基金详情: {code}, IP: {request.remote_addr}")
            return jsonify({'error': '未找到该基金数据'}), 404

    except Exception as e:
        app_logger.error(f"获取基金详情错误: {code}, IP: {request.remote_addr}, 错误: {e}")
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
