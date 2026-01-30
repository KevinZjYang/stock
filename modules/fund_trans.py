# fund_trans.py
from flask import Blueprint, request, jsonify, make_response, send_file
import sys
import os
# 添加上级目录到路径，以便导入 app.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import (
    load_fund_transactions, calculate_fund_summary,
    import_excel_transactions, export_excel_transactions, app_logger,
    add_fund_transaction, update_fund_transaction, delete_fund_transaction
)

fund_trans_bp = Blueprint('fund_trans', __name__)

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
