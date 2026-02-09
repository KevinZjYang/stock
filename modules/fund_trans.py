# fund_trans.py
from flask import Blueprint, request, jsonify, make_response, render_template, send_file
import sys
import os
import requests
import time
import math
from datetime import datetime
from typing import Dict, List, Optional  # 添加类型注解导入
# 添加上级目录到路径，以便导入 models.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.models import (
    load_fund_transactions,
    import_excel_transactions, export_excel_transactions, app_logger,
    add_fund_transaction, update_fund_transaction, delete_fund_transaction, get_db_connection,
    get_fund_cache, set_fund_cache, get_fund_cache_date
)

fund_trans_bp = Blueprint('fund_trans', __name__)


def xirr(cashflows, dates, guess=0.1, tol=1e-6, max_iter=1000):
    """
    计算内部收益率（XIRR）- 使用二分查找法，更稳定
    cashflows: 现金流列表（正数为收入，负数为支出）
    dates: 对应的日期列表
    返回: 年化收益率
    """
    if len(cashflows) != len(dates) or len(cashflows) < 2:
        return None

    # 转换为相对于起始日期的天数
    start_date = min(dates)
    days = [(d - start_date).days / 365.0 for d in dates]  # 转换为年

    # 现金流总和应该为正（最终价值 > 投入）
    total_cf = sum(cashflows)
    if total_cf <= 0:
        app_logger.info(f"[XIRR失败] 总现金流为{total_cf:.2f}，无法计算（需要正值）")
        return None

    def xnpv(rate, cashflows, days):
        """计算净现值"""
        return sum(cf * ((1 + rate) ** -d) for cf, d in zip(cashflows, days))

    # 使用二分查找，在 [-99%, 1000%] 范围内查找
    rate_low = -0.99  # -99%
    rate_high = 10.0   # 1000%

    npv_low = xnpv(rate_low, cashflows, days)
    npv_high = xnpv(rate_high, cashflows, days)

    # 如果端点已经足够接近0，直接返回
    if abs(npv_low) < tol:
        return rate_low
    if abs(npv_high) < tol:
        return rate_high

    # 确保在搜索范围内有解
    if npv_low * npv_high > 0:
        # 尝试扩大搜索范围
        rate_low = -0.9999
        rate_high = 1000.0
        npv_low = xnpv(rate_low, cashflows, days)
        npv_high = xnpv(rate_high, cashflows, days)
        if npv_low * npv_high > 0:
            app_logger.info(f"[XIRR失败] 无法在扩展范围({rate_low}, {rate_high})内找到解，NPV范围: [{npv_low:.2f}, {npv_high:.2f}]")
            return None  # 无法找到解

    # 二分查找
    for _ in range(max_iter):
        rate_mid = (rate_low + rate_high) / 2
        npv_mid = xnpv(rate_mid, cashflows, days)

        if abs(npv_mid) < tol:
            return rate_mid

        if npv_low * npv_mid <= 0:
            rate_high = rate_mid
            npv_high = npv_mid
        else:
            rate_low = rate_mid
            npv_low = npv_mid

        if (rate_high - rate_low) < tol:
            return rate_mid

    return (rate_low + rate_high) / 2


def parse_date(date_str):
    """解析日期字符串为 datetime 对象"""
    if not date_str:
        return None
    try:
        date_str = str(date_str).split(' ')[0]  # 去掉时间部分
        if '-' in date_str:
            return datetime.strptime(date_str, '%Y-%m-%d')
        elif '/' in date_str:
            return datetime.strptime(date_str, '%Y/%m/%d')
    except:
        pass
    return None


def calculate_simple_return(fund_trans, current_net_worth, current_market_value, is_sold=False):
    """
    计算简单年化收益率（备用方法，当XIRR无法计算时使用）
    适用于亏损的基金
    fund_trans: 交易记录列表
    current_net_worth: 当前净值
    current_market_value: 当前市值金额（持仓基金）或最终卖出金额（已清仓基金）
    is_sold: 是否已清仓
    """
    if not fund_trans:
        return None

    total_invested = 0  # 总投入
    total_sells = 0  # 卖出总额（扣除手续费）
    total_dividends = 0  # 分红总额
    first_date = None
    last_date = None

    for t in fund_trans:
        date = parse_date(t.get('date', ''))
        if not date:
            continue

        if not first_date:
            first_date = date
        last_date = date

        t_type = t.get('type')
        amount = float(t.get('actual_amount', 0) or 0)
        shares = float(t.get('shares', 0) or 0)
        fee = float(t.get('fee', 0) or 0)

        if t_type == '买入':
            total_invested += abs(amount) + fee
        elif t_type == '卖出':
            total_sells += amount - fee
        elif t_type == '分红' and shares == 0:
            total_dividends += amount

    if not first_date or total_invested <= 0:
        return None

    # 计算年化收益率
    years = (last_date - first_date).days / 365.0
    if years <= 0:
        return None

    # 总收益计算
    if is_sold:
        # 已清仓基金：收益 = 卖出总额 + 分红 - 总投入
        total_return = total_sells + total_dividends - total_invested
    else:
        # 持仓基金：收益 = 当前市值 + 分红 - 总投入（不重复计算卖出）
        # 注意：买入时投入已计算，卖出时收益已计入total_sells
        # 简化模型：收益 = 当前市值 + 卖出总额 + 分红 - 总投入
        total_return = current_market_value + total_sells + total_dividends - total_invested

    # 简单年化收益率: (1 + 收益率)^(1/年) - 1
    if total_return >= 0:
        annualized_return = (1 + total_return / total_invested) ** (1 / years) - 1
    else:
        # 亏损情况：使用绝对值计算负收益
        annualized_return = -((1 + abs(total_return) / total_invested) ** (1 / years) - 1)

    app_logger.info(f"[简单年化] 投入={total_invested:.2f}, 卖出={total_sells:.2f}, 当前市值={current_market_value:.2f}, 分红={total_dividends:.2f}, 总收益={total_return:.2f}, 年份={years:.2f}, 年化={annualized_return:.4f}, 已清仓={is_sold}")

    return annualized_return


def calculate_fund_xirr(fund_trans, current_net_worth):
    """
    计算单个基金的年化收益率（XIRR）
    fund_trans: 该基金的所有交易记录（已按日期排序）
    current_net_worth: 当前净值
    """
    app_logger.info(f"[XIRR函数] fund_trans数量={len(fund_trans) if fund_trans else 0}, current_net_worth={current_net_worth}")
    if not fund_trans or not current_net_worth:
        app_logger.info(f"[XIRR函数] 参数不满足条件，返回None")
        return None

    cashflows = []
    dates = []
    total_shares = 0
    total_cost = 0  # 记录总投入成本

    for t in fund_trans:
        date = parse_date(t.get('date', ''))
        if not date:
            continue

        t_type = t.get('type')
        amount = float(t.get('actual_amount', 0) or 0)
        shares = float(t.get('shares', 0) or 0)
        fee = float(t.get('fee', 0) or 0)

        if t_type == '买入':
            # 买入是资金支出（负）
            cf = -(amount + fee)
            cashflows.append(cf)
            dates.append(date)
            total_shares += shares
            total_cost += abs(amount) + fee
            app_logger.info(f"[XIRR调试] {date.strftime('%Y-%m-%d')} 买入: {cf}")
        elif t_type == '卖出':
            # 卖出是资金收入（正），扣除手续费
            cf = amount - fee
            cashflows.append(cf)
            dates.append(date)
            total_shares -= shares
            app_logger.info(f"[XIRR调试] {date.strftime('%Y-%m-%d')} 卖出: {cf}")
        elif t_type == '分红':
            # 现金分红是收入（正）
            if shares == 0:  # 现金分红
                cashflows.append(amount)
                dates.append(date)
                app_logger.info(f"[XIRR调试] {date.strftime('%Y-%m-%d')} 分红: {amount}")

    app_logger.info(f"[XIRR函数] 处理后: total_shares={total_shares}, cashflows数量={len(cashflows)}")

    # 添加当前市值作为最终收入（只有持仓大于0时才添加）
    if total_shares > 0:
        final_value = total_shares * current_net_worth
        cashflows.append(final_value)
        dates.append(datetime.now())
        app_logger.info(f"[XIRR调试] {datetime.now().strftime('%Y-%m-%d')} 当前市值: {final_value:.2f} (份额={total_shares:.2f})")
    else:
        app_logger.info(f"[XIRR函数] total_shares={total_shares} <= 0，不添加市值现金流")

    if len(cashflows) < 2:
        app_logger.info(f"[XIRR调试] 现金流不足2笔，返回None")
        return None

    # 计算天数
    if dates:
        start_date = min(dates)
        day_list = [(d - start_date).days for d in dates]
        app_logger.info(f"[XIRR调试] 现金流: {cashflows}, 天数: {day_list}")

    # 计算 XIRR
    try:
        result = xirr(cashflows, dates)
        app_logger.info(f"[XIRR调试] XIRR结果: {result}")
        return result
    except Exception as e:
        app_logger.info(f"[XIRR调试] XIRR计算异常: {e}")
        return None

def calculate_fund_summary(transactions):
    """计算基金交易汇总数据 - 改进版本，正确处理成本计算"""
    if not transactions:
        return {
            "total_shares": 0, "total_cost": 0, "realized_profit": 0,
            "dividend_total": 0, "buy_count": 0, "sell_count": 0,
            "dividend_count": 0, "trade_count": 0, "total_fee": 0,
            "market_value": 0, "fund_performance": []
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

    # 按基金代码分组记录，用于XIRR计算
    fund_transactions = {}  # {code: [transactions...]}

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

        # 记录该基金的交易用于XIRR计算
        if formatted_code not in fund_transactions:
            fund_transactions[formatted_code] = []
        fund_transactions[formatted_code].append(t)

        shares = float(t.get('shares', 0)) if t.get('shares') is not None else 0
        amount = float(t.get('actual_amount', 0)) if t.get('actual_amount') is not None else 0
        fee = float(t.get('fee', 0)) if t.get('fee') is not None else 0

        total_fee += fee

        if t_type == '买入':
            buy_count += 1
            if formatted_code not in holdings:
                holdings[formatted_code] = {'shares': 0, 'cost': 0}

            holdings[formatted_code]['shares'] += shares
            holdings[formatted_code]['cost'] += abs(amount)

        elif t_type == '卖出':
            sell_count += 1
            if formatted_code not in holdings:
                holdings[formatted_code] = {'shares': 0, 'cost': 0}

            if holdings[formatted_code]['shares'] > 0:
                avg_cost_per_share = holdings[formatted_code]['cost'] / holdings[formatted_code]['shares']
                sell_cost = shares * avg_cost_per_share
                sell_income = abs(amount) - fee
                realized_profit += (sell_income - sell_cost)
                holdings[formatted_code]['shares'] -= shares
                holdings[formatted_code]['cost'] -= sell_cost

                if holdings[formatted_code]['shares'] <= 0.0001:
                    del holdings[formatted_code]
            elif holdings[formatted_code]['shares'] < 0:
                avg_cost_per_share = abs(holdings[formatted_code]['cost'] / holdings[formatted_code]['shares'])
                sell_cost = shares * avg_cost_per_share
                sell_income = abs(amount) - fee
                realized_profit += (sell_income - sell_cost)

        elif t_type == '分红':
            dividend_count += 1
            dividend_total += abs(amount)
            if shares > 0:
                # 分红再投资
                if formatted_code not in holdings:
                    holdings[formatted_code] = {'shares': 0, 'cost': 0}
                holdings[formatted_code]['shares'] += shares
                holdings[formatted_code]['cost'] += abs(amount)
            else:
                # 现金分红
                realized_profit += abs(amount)

    total_shares = sum(h['shares'] for h in holdings.values())
    total_cost = sum(h['cost'] for h in holdings.values())
    total_cost = abs(total_cost)

    # 计算持仓市值和单基金收益率
    market_value = 0
    fund_performance = []
    fund_names = {}  # 用于获取基金名称
    sold_funds_xirr = {}  # 已清仓基金的年化收益

    # 从交易记录中提取基金名称
    for t in transactions:
        code = str(t.get('code', '')).zfill(6)
        name = t.get('name', '')
        if code and name:
            fund_names[code] = name

    # 计算已完全卖出基金的XIRR（它们不在holdings中）
    sold_fund_codes = set(fund_transactions.keys()) - set(holdings.keys())
    if sold_fund_codes:
        holding_codes = list(holdings.keys())
        all_codes_for_price = list(holding_codes) + list(sold_fund_codes)
        fund_prices_all = fetch_fund_price_batch_sync(all_codes_for_price) if all_codes_for_price else []
        fund_price_dict = {f['code']: f for f in fund_prices_all} if fund_prices_all else {}

        for code in sold_fund_codes:
            if code in fund_transactions and len(fund_transactions[code]) >= 1:
                # 获取当前净值用于计算最终价值
                fund_info = fund_price_dict.get(code, {})
                current_net_worth = fund_info.get('expectWorth') or fund_info.get('netWorth') or 1.0

                # 计算已清仓基金的卖出总额
                total_sells = 0
                for t in fund_transactions[code]:
                    t_type = t.get('type')
                    if t_type == '卖出':
                        amount = float(t.get('actual_amount', 0) or 0)
                        fee = float(t.get('fee', 0) or 0)
                        total_sells += amount - fee

                xirr_result = calculate_fund_xirr(fund_transactions[code], current_net_worth)

                # 如果XIRR无法计算，使用简单年化收益率作为备选
                if xirr_result is None:
                    simple_result = calculate_simple_return(fund_transactions[code], current_net_worth, total_sells, is_sold=True)
                    if simple_result is not None:
                        xirr_result = simple_result
                        app_logger.info(f"[已清仓基金年化] {code}: XIRR=None, 使用简单年化={simple_result}")
                    else:
                        app_logger.info(f"[已清仓基金年化] {code}: XIRR=None, 简单年化也无法计算")
                name = fund_names.get(code, code)
                sold_funds_xirr[code] = {
                    "code": code,
                    "name": name,
                    "xirr": round(xirr_result * 100, 2) if xirr_result else None,
                    "status": "已清仓"
                }
                app_logger.info(f"[已清仓基金年化] {code}: 最终结果={xirr_result}")

    if holdings:
        holding_codes = list(holdings.keys())
        fund_prices = fetch_fund_price_batch_sync(holding_codes)

        if fund_prices:
            for fund_data in fund_prices:
                code = fund_data.get('code')
                current_net_worth = fund_data.get('expectWorth') or fund_data.get('netWorth')
                name = fund_data.get('name', fund_names.get(code, code))

                if code in holdings:
                    holding_shares = holdings[code]['shares']
                    holding_cost = holdings[code]['cost']

                    if current_net_worth:
                        fund_mv = holding_shares * current_net_worth
                        market_value += fund_mv

                        # 计算XIRR（使用该基金的交易记录）
                        xirr_result = None
                        if code in fund_transactions:
                            xirr_result = calculate_fund_xirr(fund_transactions[code], current_net_worth)
                            app_logger.info(f"[年化收益] {code}: XIRR结果={xirr_result}, 当前净值={current_net_worth}")

                            # 如果XIRR无法计算，使用简单年化收益率作为备选
                            if xirr_result is None:
                                simple_result = calculate_simple_return(fund_transactions[code], current_net_worth, fund_mv, is_sold=False)
                                if simple_result is not None:
                                    xirr_result = simple_result
                                    app_logger.info(f"[年化收益] {code}: XIRR=None, 使用简单年化={simple_result}")

                        fund_performance.append({
                            "code": code,
                            "name": name,
                            "shares": round(holding_shares, 2),
                            "cost": round(abs(holding_cost), 2),
                            "market_value": round(fund_mv, 2),
                            "xirr": round(xirr_result * 100, 2) if xirr_result else None
                        })

    # 计算整体年化收益率（使用所有交易记录）
    overall_xirr = None
    if holdings:
        # 获取所有持仓基金的净值
        holding_codes = list(holdings.keys())
        fund_prices = fetch_fund_price_batch_sync(holding_codes)
        fund_net_worths = {}
        for fd in fund_prices:
            code = fd.get('code')
            nw = fd.get('expectWorth') or fd.get('netWorth')
            if nw:
                fund_net_worths[code] = nw

        # 构建整体现金流的交易记录
        all_cashflows = []
        all_dates = []
        total_shares_check = 0

        for t in sorted_transactions:
            date = parse_date(t.get('date', ''))
            if not date:
                continue

            t_type = t.get('type')
            code = str(t.get('code', '')).zfill(6)
            amount = float(t.get('actual_amount', 0) or 0)
            shares = float(t.get('shares', 0) or 0)
            fee = float(t.get('fee', 0) or 0)

            if t_type == '买入':
                all_cashflows.append(-(amount + fee))
                all_dates.append(date)
                total_shares_check += shares
            elif t_type == '卖出':
                all_cashflows.append(amount - fee)
                all_dates.append(date)
                total_shares_check -= shares
            elif t_type == '分红' and shares == 0:
                all_cashflows.append(amount)
                all_dates.append(date)

        # 添加当前所有持仓的市值
        if total_shares_check > 0:
            total_current_value = 0
            for code, shares in holdings.items():
                nw = fund_net_worths.get(code, 0)
                total_current_value += shares['shares'] * nw
            if total_current_value > 0:
                all_cashflows.append(total_current_value)
                all_dates.append(datetime.now())

        if len(all_cashflows) >= 2:
            overall_xirr = xirr(all_cashflows, all_dates)
            app_logger.info(f"[整体年化] 现金流数量={len(all_cashflows)}, XIRR={overall_xirr}")

    return {
        "total_shares": round(total_shares, 2),
        "total_cost": round(total_cost, 2),
        "realized_profit": round(realized_profit, 2),
        "dividend_total": round(dividend_total, 2),
        "total_fee": round(total_fee, 2),
        "market_value": round(market_value, 2),
        "buy_count": buy_count,
        "sell_count": sell_count,
        "dividend_count": dividend_count,
        "trade_count": len(transactions),
        "fund_performance": fund_performance,
        "sold_funds_xirr": list(sold_funds_xirr.values()),
        "overall_xirr": round(overall_xirr * 100, 2) if overall_xirr else None
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

        # 尝试使用缓存的汇总数据
        summary = get_cached_summary(use_cache=True)

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


# ==================== 缓存相关函数 ====================

def get_cached_summary(use_cache: bool = True) -> Dict:
    """
    获取缓存的汇总数据
    use_cache: 是否使用缓存
    返回: 汇总数据字典
    """
    today = datetime.now().strftime('%Y-%m-%d')
    cache_key = 'fund_summary'

    if use_cache:
        # 尝试从缓存读取
        cached = get_fund_cache(cache_key, today)
        if cached:
            app_logger.info(f"[缓存] 使用缓存的基金汇总数据 ({today})")
            return cached

    # 没有缓存，重新计算
    app_logger.info(f"[缓存] 重新计算基金汇总数据")
    transactions = load_fund_transactions()
    summary = calculate_fund_summary(transactions)

    # 更新缓存
    set_fund_cache(cache_key, summary, today)

    return summary


def refresh_fund_cache(force: bool = False) -> Dict:
    """
    刷新基金缓存
    force: 是否强制刷新（忽略日期检查）
    返回: 汇总数据字典
    """
    today = datetime.now().strftime('%Y-%m-%d')
    cache_key = 'fund_summary'

    # 检查是否需要刷新（当天已计算过就不需要了，除非强制刷新）
    last_date = get_fund_cache_date(cache_key)
    if not force and last_date == today:
        app_logger.info(f"[缓存] 当天已计算过，跳过刷新")
        return get_fund_cache(cache_key, today) or get_cached_summary(False)

    # 重新计算并缓存
    app_logger.info(f"[缓存] 刷新基金缓存")
    return get_cached_summary(use_cache=False)


# ==================== 定时任务 ====================

def scheduled_fund_cache_update():
    """
    定时任务：更新基金缓存
    每天晚上 21:00 执行
    """
    app_logger.info("[定时任务] 开始执行基金缓存更新")
    try:
        result = refresh_fund_cache(force=True)
        app_logger.info(f"[定时任务] 基金缓存更新完成")
        return True
    except Exception as e:
        app_logger.error(f"[定时任务] 基金缓存更新失败: {e}")
        return False


def cache_scheduler_thread():
    """缓存定时任务线程（使用简单的时间检查）"""
    import time as time_module

    app_logger.info("[缓存调度器] 启动基金缓存定时任务")

    while True:
        try:
            now = datetime.now()
            current_hour = now.hour
            current_minute = now.minute

            # 每天 21:00 执行
            if current_hour == 21 and current_minute == 0:
                app_logger.info(f"[缓存调度器] 检测到21:00，执行缓存更新")
                scheduled_fund_cache_update()
                # 等待1分钟避免重复执行
                time_module.sleep(60)

            # 检查是否需要执行（如果错过了21:00，当天还没执行过）
            if current_hour > 21:
                cache_key = 'fund_summary'
                last_date = get_fund_cache_date(cache_key)
                today = now.strftime('%Y-%m-%d')
                if last_date != today:
                    app_logger.info(f"[缓存调度器] 检测到已过21:00但当天未更新，执行缓存更新")
                    scheduled_fund_cache_update()

            # 每30秒检查一次
            time_module.sleep(30)
        except Exception as e:
            app_logger.error(f"[缓存调度器] 错误: {e}")
            time_module.sleep(60)


# ==================== API 接口 ====================

@fund_trans_bp.route('/cache/refresh', methods=['POST'])
def refresh_cache():
    """手动刷新缓存接口"""
    data = request.get_json() or {}
    force = data.get('force', False)

    app_logger.info(f"手动刷新基金缓存，force={force}")

    try:
        result = refresh_fund_cache(force=force)
        return jsonify({
            'success': True,
            'message': '缓存刷新成功',
            'data': {
                'total_shares': result.get('total_shares'),
                'total_cost': result.get('total_cost'),
                'market_value': result.get('market_value'),
                'realized_profit': result.get('realized_profit'),
                'overall_xirr': result.get('overall_xirr')
            }
        })
    except Exception as e:
        app_logger.error(f"刷新缓存失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@fund_trans_bp.route('/cache/status', methods=['GET'])
def cache_status():
    """获取缓存状态接口"""
    cache_key = 'fund_summary'
    last_date = get_fund_cache_date(cache_key)
    today = datetime.now().strftime('%Y-%m-%d')

    return jsonify({
        'cache_date': last_date,
        'is_today': last_date == today,
        'need_refresh': last_date != today
    })


# ==================== 启动定时任务 ====================

def start_cache_scheduler():
    """启动缓存定时任务调度器（使用简单线程）"""
    import threading

    scheduler_thread = threading.Thread(
        target=cache_scheduler_thread,
        daemon=True,
        name='FundCacheScheduler'
    )
    scheduler_thread.start()
    app_logger.info("[定时任务] 基金缓存调度器已启动（每天21:00执行）")
    return scheduler_thread
