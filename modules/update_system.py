"""
系统更新功能模块
负责检查、下载和应用项目更新
"""
import os
import sys
import json
import time
import shutil
import zipfile
import tempfile
import requests
import subprocess
from datetime import datetime
import logging
from typing import Dict, Any

# 获取项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 数据库路径
DATABASE_PATH = os.path.join(BASE_DIR, 'data', 'stock_fund.db')

# 日志记录器
app_logger = logging.getLogger(__name__)


def backup_database():
    """备份数据库文件"""
    import shutil
    from datetime import datetime

    if not os.path.exists(DATABASE_PATH):
        app_logger.warning("数据库文件不存在，跳过备份")
        return None

    # 创建备份文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(
        os.path.dirname(DATABASE_PATH),
        f"stock_fund_backup_{timestamp}.db"
    )

    try:
        shutil.copy2(DATABASE_PATH, backup_path)
        app_logger.info(f"数据库备份成功: {backup_path}")
        return backup_path
    except Exception as e:
        app_logger.error(f"数据库备份失败: {e}")
        return None


def get_setting(key, default=None):
    """获取设置值 - 从数据库中获取"""
    import sqlite3

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = cursor.fetchone()
    conn.close()

    if row:
        try:
            return json.loads(row[0])  # row是元组，使用索引访问
        except:
            return row[0]  # row是元组，使用索引访问
    return default


def set_setting(key, value):
    """设置值 - 保存到数据库中"""
    import sqlite3
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (key, json.dumps(value)))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        conn.close()
        app_logger.error(f"保存设置失败 {key}: {e}")
        return False


def compare_versions(v1, v2):
    """
    比较两个版本号
    :param v1: 第一个版本号 (本地)
    :param v2: 第二个版本号 (远程)
    :return: 如果v2>v1返回True，否则返回False
    """
    def parse_version(version):
        # 将版本号拆分为数字部分，例如 "1.2.3" -> [1, 2, 3]
        parts = version.replace('v', '').split('.')
        return [int(part) for part in parts if part.isdigit()]

    try:
        v1_parts = parse_version(v1)
        v2_parts = parse_version(v2)

        # 比较每个部分
        for i in range(max(len(v1_parts), len(v2_parts))):
            val1 = v1_parts[i] if i < len(v1_parts) else 0
            val2 = v2_parts[i] if i < len(v2_parts) else 0

            if val2 > val1:
                return True  # 远程版本更高
            elif val2 < val1:
                return False  # 本地版本更高或相等

        return False  # 版本相同或本地版本更高
    except Exception:
        # 如果版本号格式不正确，回退到字符串比较
        return v2 != v1 and v2 > v1


def check_for_updates():
    """检查项目是否有更新 - 不依赖Git"""
    try:
        # 从远程服务器或GitHub API检查更新
        # 这里可以检查远程版本文件或GitHub API
        import requests

        # 从设置中获取仓库信息，如果不存在则使用默认值
        repo_info = get_setting('repo_info', {})
        repo_owner = repo_info.get('owner', 'KevinZjYang')  # 实际用户名
        repo_name = repo_info.get('name', 'stock')  # 实际仓库名

        # 检查本地版本信息（如果存在）
        local_version_file = os.path.join(BASE_DIR, 'VERSION')
        current_version = "unknown"
        if os.path.exists(local_version_file):
            with open(local_version_file, 'r', encoding='utf-8') as f:
                current_version = f.read().strip()

        try:
            # 尝试获取远程版本文件
            version_url = f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/main/VERSION"
            response = requests.get(version_url, timeout=10)
            if response.status_code == 200:
                remote_version = response.text.strip()

                # 使用版本比较函数，只有当远程版本大于本地版本时才认为有更新
                has_update = compare_versions(current_version, remote_version)

                return {
                    "has_update": has_update,
                    "current_version": current_version,
                    "remote_version": remote_version,
                    "message": f"发现新版本: {remote_version}" if has_update else "已是最新版本"
                }
            else:
                app_logger.warning(f"无法获取远程版本信息: HTTP {response.status_code}")

                # 如果无法获取版本文件，回退到检查最新提交
                repo_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/commits/main"
                response = requests.get(repo_url, timeout=10)
                if response.status_code == 200:
                    remote_data = response.json()
                    remote_commit_sha = remote_data.get('sha', '')[:8]  # 获取前8位作为版本标识

                    # 检查本地是否有记录的最新远程commit SHA
                    last_remote_commit = get_setting('last_remote_commit', '')

                    # 比较远程commit SHA与本地记录的SHA
                    has_update = remote_commit_sha != last_remote_commit

                    # 更新本地记录的远程commit SHA
                    set_setting('last_remote_commit', remote_commit_sha)

                    return {
                        "has_update": has_update,
                        "current_version": current_version,
                        "remote_version": remote_commit_sha,
                        "message": f"发现新版本: {remote_commit_sha}" if has_update else "已是最新版本",
                        "last_commit_date": remote_data.get('commit', {}).get('author', {}).get('date', '')
                    }
                else:
                    return {"has_update": False, "message": f"无法获取远程仓库信息: HTTP {response.status_code}"}
        except requests.RequestException as e:
            app_logger.error(f"网络请求失败: {e}")
            return {"has_update": False, "message": f"网络请求失败: {e}"}
        except Exception as e:
            app_logger.error(f"解析远程仓库信息失败: {e}")
            return {"has_update": False, "message": f"解析远程仓库信息失败: {e}"}

    except Exception as e:
        app_logger.error(f"检查更新时发生错误: {e}")
        return {"has_update": False, "error": str(e)}


def perform_update():
    """执行项目更新 - 不依赖Git"""
    import sys
    import os
    import tempfile
    import zipfile
    import shutil
    try:
        app_logger.info("开始执行项目更新...")

        # 获取当前目录
        current_dir = os.path.dirname(BASE_DIR)

        # 从设置中获取仓库信息
        repo_info = get_setting('repo_info', {})
        repo_owner = repo_info.get('owner', 'KevinZjYang')  # 实际用户名
        repo_name = repo_info.get('name', 'stock')  # 实际仓库名

        # 备份data目录
        data_backup_path = ""
        data_dir = os.path.join(current_dir, "data")
        if os.path.exists(data_dir):
            data_backup_path = os.path.join(current_dir, f"data_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            shutil.copytree(data_dir, data_backup_path)
            app_logger.info(f"已备份data目录到 {data_backup_path}")

        # 下载最新的代码包（从GitHub或其他源）
        import requests

        # 使用GitHub的zipball链接下载最新代码
        download_url = f"https://github.com/{repo_owner}/{repo_name}/archive/main.zip"

        try:
            response = requests.get(download_url, stream=True, timeout=30)
            response.raise_for_status()

            # 创建临时文件保存下载的zip
            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    tmp_file.write(chunk)
                temp_zip_path = tmp_file.name

            # 解压到临时目录
            with tempfile.TemporaryDirectory() as temp_extract_dir:
                with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_extract_dir)

                # 找到解压后的根目录（GitHub的zip通常包含一个带分支名的根文件夹）
                extracted_dirs = os.listdir(temp_extract_dir)
                if extracted_dirs:
                    extracted_root = os.path.join(temp_extract_dir, extracted_dirs[0])

                    # 备份当前运行的应用程序（除了特定目录）
                    backup_dir = os.path.join(current_dir, f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                    os.makedirs(backup_dir, exist_ok=True)

                    # 复制当前项目文件到备份目录（除了排除的目录）
                    for item in os.listdir(current_dir):
                        src_path = os.path.join(current_dir, item)
                        dst_path = os.path.join(backup_dir, item)

                        # 跳过一些不应备份的目录
                        if item in ['.git', '__pycache__', 'data', 'venv', 'env', '.gitignore', '.env', 'config.json', 'backup_*']:
                            continue

                        if os.path.isdir(src_path):
                            shutil.copytree(src_path, dst_path)
                        else:
                            shutil.copy2(src_path, dst_path)

                    app_logger.info(f"已创建备份: {backup_dir}")

                    # 删除当前目录中除data外的所有内容
                    for item in os.listdir(current_dir):
                        item_path = os.path.join(current_dir, item)

                        # 跳过data目录、logs目录和备份目录（在Docker环境中logs可能被挂载为卷）
                        if item in ['data', 'logs', os.path.basename(backup_dir), 'templates']:
                            continue

                        if os.path.isdir(item_path):
                            try:
                                shutil.rmtree(item_path)
                            except OSError as e:
                                app_logger.warning(f"无法删除目录 {item_path}: {e}")
                                # 如果无法删除目录，跳过它
                                continue
                        else:
                            try:
                                os.remove(item_path)
                            except OSError as e:
                                app_logger.warning(f"无法删除文件 {item_path}: {e}")
                                # 如果无法删除文件，跳过它
                                continue

                    # 将新版本文件复制到当前目录
                    for item in os.listdir(extracted_root):
                        src_path = os.path.join(extracted_root, item)
                        dst_path = os.path.join(current_dir, item)

                        if os.path.isdir(src_path):
                            # 对于特定的目录（如templates, data, logs），它们可能被挂载为Docker卷
                            # 我们需要处理这些特殊情况，避免尝试替换挂载的目录
                            if item in ['templates', 'data', 'logs']:
                                # 只复制目录内容而不替换目录本身
                                if not os.path.exists(dst_path):
                                    os.makedirs(dst_path, exist_ok=True)

                                for sub_item in os.listdir(src_path):
                                    sub_src_path = os.path.join(src_path, sub_item)
                                    sub_dst_path = os.path.join(dst_path, sub_item)

                                    if os.path.isdir(sub_src_path):
                                        if os.path.exists(sub_dst_path):
                                            shutil.rmtree(sub_dst_path)
                                        shutil.copytree(sub_src_path, sub_dst_path)
                                    else:
                                        shutil.copy2(sub_src_path, sub_dst_path)
                            else:
                                # 其他目录正常操作
                                if os.path.exists(dst_path):
                                    shutil.rmtree(dst_path)
                                shutil.copytree(src_path, dst_path)
                        else:
                            shutil.copy2(src_path, dst_path)

                    # 恢复data目录
                    if data_backup_path and os.path.exists(data_backup_path):
                        restored_data_path = os.path.join(current_dir, "data")
                        if os.path.exists(restored_data_path):
                            # 如果新版本有data目录，先删除它
                            shutil.rmtree(restored_data_path)

                        # 恢复备份的data目录
                        shutil.copytree(data_backup_path, restored_data_path)
                        app_logger.info("已恢复data目录内容")

                        # 删除备份的data目录
                        shutil.rmtree(data_backup_path)

                app_logger.info("代码更新成功")

        except Exception as download_error:
            app_logger.error(f"下载或应用更新失败: {download_error}")

            # 如果更新失败，尝试恢复data目录
            if data_backup_path and os.path.exists(data_backup_path):
                restored_data_path = os.path.join(current_dir, "data")
                if os.path.exists(restored_data_path):
                    shutil.rmtree(restored_data_path)
                shutil.copytree(data_backup_path, restored_data_path)
                app_logger.info("已从备份恢复data目录")

            return {"success": False, "error": str(download_error)}

        # 重新安装依赖（如果requirements.txt有变化）
        requirements_path = os.path.join(current_dir, 'requirements.txt')
        if os.path.exists(requirements_path):
            import subprocess
            result = subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt', '--upgrade'],
                                  capture_output=True, text=True, cwd=current_dir)
            if result.returncode != 0:
                app_logger.warning(f"依赖安装有警告: {result.stderr}")
            else:
                app_logger.info("依赖安装成功")

        # 记录更新时间
        set_setting('last_update_time', datetime.now().isoformat())

        # 清理临时文件
        try:
            os.unlink(temp_zip_path)
        except:
            pass  # 忽略清理临时文件的错误

        return {
            "success": True,
            "message": "更新成功完成",
            "output": "代码和依赖已更新"
        }
    except Exception as e:
        app_logger.error(f"执行更新时发生错误: {e}")
        return {"success": False, "error": str(e)}


def perform_safe_update():
    """执行安全的更新，保护用户数据"""
    import tempfile
    import zipfile
    import requests
    import shutil
    import os
    from datetime import datetime

    try:
        # 1. 备份当前数据库
        backup_path = backup_database()
        if not backup_path:
            app_logger.error("无法创建数据库备份，取消更新")
            return {"success": False, "error": "无法创建数据库备份"}

        app_logger.info("开始执行安全更新...")

        # 获取当前目录
        current_project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # 备份data目录
        data_backup_path = ""
        data_dir = os.path.join(current_project_dir, "data")
        if os.path.exists(data_dir):
            data_backup_path = os.path.join(current_project_dir, f"data_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
            shutil.copytree(data_dir, data_backup_path)
            app_logger.info(f"已备份data目录到 {data_backup_path}")

        # 2. 从GitHub下载最新版本
        repo_owner = "KevinZjYang"  # 从配置中获取或硬编码
        repo_name = "stock"
        download_url = f"https://github.com/{repo_owner}/{repo_name}/archive/main.zip"

        try:
            response = requests.get(download_url, stream=True, timeout=30)
            response.raise_for_status()

            # 创建临时文件保存下载的zip
            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    tmp_file.write(chunk)
                temp_zip_path = tmp_file.name

            # 在临时目录中解压
            with tempfile.TemporaryDirectory() as temp_extract_dir:
                with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_extract_dir)

                # 找到解压后的根目录
                extracted_dirs = os.listdir(temp_extract_dir)
                if not extracted_dirs:
                    raise Exception("解压后没有找到项目文件")

                extracted_root = os.path.join(temp_extract_dir, extracted_dirs[0])

                # 备份当前运行的应用程序（除了特定目录）
                backup_dir = os.path.join(current_project_dir, f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                os.makedirs(backup_dir, exist_ok=True)

                # 复制当前项目文件到备份目录（除了排除的目录）
                for item in os.listdir(current_project_dir):
                    src_path = os.path.join(current_project_dir, item)
                    dst_path = os.path.join(backup_dir, item)

                    # 跳过一些不应备份的目录
                    if item in ['.git', '__pycache__', 'data', 'venv', 'env', '.gitignore', '.env', 'config.json', 'backup_*']:
                        continue

                    if os.path.isdir(src_path):
                        shutil.copytree(src_path, dst_path)
                    else:
                        shutil.copy2(src_path, dst_path)

                app_logger.info(f"已创建备份: {backup_dir}")

                # 删除当前目录中除data外的所有内容
                for item in os.listdir(current_project_dir):
                    item_path = os.path.join(current_project_dir, item)

                    # 跳过data目录、logs目录、templates目录和备份目录（在Docker环境中这些可能被挂载为卷）
                    if item in ['data', 'logs', os.path.basename(backup_dir), 'templates']:
                        continue

                    if os.path.isdir(item_path):
                        try:
                            shutil.rmtree(item_path)
                        except OSError as e:
                            app_logger.warning(f"无法删除目录 {item_path}: {e}")
                            # 如果无法删除目录，跳过它
                            continue
                    else:
                        try:
                            os.remove(item_path)
                        except OSError as e:
                            app_logger.warning(f"无法删除文件 {item_path}: {e}")
                            # 如果无法删除文件，跳过它
                            continue

                # 将新版本文件复制到当前目录
                for item in os.listdir(extracted_root):
                    src_path = os.path.join(extracted_root, item)
                    dst_path = os.path.join(current_project_dir, item)

                    if os.path.isdir(src_path):
                        # 对于特定的目录（如templates, data, logs），它们可能被挂载为Docker卷
                        # 我们需要处理这些特殊情况，避免尝试替换挂载的目录
                        if item in ['templates', 'data', 'logs']:
                            # 只复制目录内容而不替换目录本身
                            if not os.path.exists(dst_path):
                                os.makedirs(dst_path, exist_ok=True)

                            for sub_item in os.listdir(src_path):
                                sub_src_path = os.path.join(src_path, sub_item)
                                sub_dst_path = os.path.join(dst_path, sub_item)

                                if os.path.isdir(sub_src_path):
                                    if os.path.exists(sub_dst_path):
                                        shutil.rmtree(sub_dst_path)
                                    shutil.copytree(sub_src_path, sub_dst_path)
                                else:
                                    shutil.copy2(sub_src_path, sub_dst_path)
                        else:
                            # 其他目录正常操作
                            if os.path.exists(dst_path):
                                shutil.rmtree(dst_path)
                            shutil.copytree(src_path, dst_path)
                    else:
                        shutil.copy2(src_path, dst_path)

                # 恢复data目录
                if data_backup_path and os.path.exists(data_backup_path):
                    restored_data_path = os.path.join(current_project_dir, "data")
                    if os.path.exists(restored_data_path):
                        # 如果新版本有data目录，先删除它
                        shutil.rmtree(restored_data_path)

                    # 恢复备份的data目录
                    shutil.copytree(data_backup_path, restored_data_path)
                    app_logger.info("已恢复data目录内容")

                    # 删除备份的data目录
                    shutil.rmtree(data_backup_path)

                app_logger.info("文件更新完成")

            # 3. 清理临时文件
            os.unlink(temp_zip_path)

            # 4. 执行数据库迁移（如果有）
            try:
                migrate_database_schema()
                app_logger.info("数据库迁移完成")
            except Exception as e:
                app_logger.error(f"数据库迁移失败: {e}")
                # 这种情况下不应该完全失败，因为用户数据更重要
                # 可以记录错误但继续执行

            # 5. 记录更新时间
            set_setting('last_update_time', datetime.now().isoformat())

            return {
                "success": True,
                "message": "更新成功完成",
                "backup_path": backup_path
            }

        except Exception as download_error:
            app_logger.error(f"下载或应用更新失败: {download_error}")

            # 如果更新失败，尝试恢复data目录
            if data_backup_path and os.path.exists(data_backup_path):
                restored_data_path = os.path.join(current_project_dir, "data")
                if os.path.exists(restored_data_path):
                    shutil.rmtree(restored_data_path)
                shutil.copytree(data_backup_path, restored_data_path)
                app_logger.info("已从备份恢复data目录")

            # 如果更新失败，尝试从备份恢复数据库
            try:
                if os.path.exists(backup_path) and os.path.exists(DATABASE_PATH):
                    shutil.copy2(backup_path, DATABASE_PATH)
                    app_logger.info("已从备份恢复数据库")
            except Exception as restore_error:
                app_logger.error(f"恢复数据库失败: {restore_error}")

            return {"success": False, "error": str(download_error)}

    except Exception as e:
        app_logger.error(f"执行安全更新时发生错误: {e}")
        return {"success": False, "error": str(e)}


def migrate_database_schema():
    """数据库模式迁移，用于在版本更新时安全地更新数据库结构"""
    import sqlite3
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    try:
        # 检查是否已存在version_info表
        cursor.execute("""
            SELECT name FROM sqlite_master WHERE type='table' AND name='version_info'
        """)
        table_exists = cursor.fetchone()

        if not table_exists:
            # 创建版本信息表
            cursor.execute('''
                CREATE TABLE version_info (
                    id INTEGER PRIMARY KEY,
                    schema_version TEXT NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # 插入初始版本
            cursor.execute(
                "INSERT INTO version_info (schema_version) VALUES (?)",
                ("1.0.0",)
            )
            conn.commit()
            app_logger.info("创建版本信息表并设置初始版本")

        # 获取当前数据库模式版本
        cursor.execute("SELECT schema_version FROM version_info ORDER BY id DESC LIMIT 1")
        current_version = cursor.fetchone()[0] if cursor.rowcount > 0 else "1.0.0"

        # 根据当前版本执行相应的迁移
        migrations_applied = 0

        # 示例：从1.0.0迁移到1.1.0 - 添加新字段
        if current_version < "1.1.0":
            try:
                cursor.execute('ALTER TABLE stocks ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
                app_logger.info("添加updated_at字段到stocks表")
                migrations_applied += 1
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e):
                    raise e  # 如果不是重复字段错误，则抛出异常

        # 示例：从1.1.0迁移到1.2.0 - 创建新表
        if current_version < "1.2.0":
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT UNIQUE,
                    setting_key TEXT NOT NULL,
                    setting_value TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            app_logger.info("创建user_settings表")
            migrations_applied += 1

        # 如果有迁移应用，更新版本信息
        if migrations_applied > 0:
            new_version = "1.2.0"  # 这应该根据实际迁移来确定
            cursor.execute(
                "INSERT INTO version_info (schema_version) VALUES (?)",
                (new_version,)
            )
            conn.commit()
            app_logger.info(f"数据库模式迁移完成，从 {current_version} 升级到 {new_version}")
        else:
            app_logger.info(f"数据库模式已是最新版本: {current_version}")

    except Exception as e:
        app_logger.error(f"数据库模式迁移失败: {e}")
        conn.rollback()
        raise e
    finally:
        conn.close()


def restart_application():
    """重启应用程序"""
    import subprocess
    import os
    try:
        app_logger.info("尝试重启应用程序...")

        # 如果是在Docker容器中运行，尝试重启服务
        if os.path.exists('/.dockerenv'):  # 检查是否在Docker容器中
            # 在Docker中，通常需要重启整个容器
            app_logger.info("检测到在Docker容器中运行，发送重启信号...")
            import signal
            os.kill(os.getpid(), signal.SIGTERM)  # 发送终止信号，让Docker重启容器
            return {"success": True, "message": "已发送重启信号"}
        else:
            # 不是在Docker中，尝试使用systemctl或其他方式重启
            # 这里可以根据实际部署方式进行调整
            return {"success": True, "message": "请手动重启应用程序以应用更新"}
    except Exception as e:
        app_logger.error(f"重启应用程序时发生错误: {e}")
        return {"success": False, "error": str(e)}