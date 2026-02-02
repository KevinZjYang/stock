# 增量更新机制说明

## 概述
本项目实现了安全的增量更新机制，确保在更新过程中保护用户数据不被覆盖。

## 主要特性

### 1. 数据库备份与恢复
- 更新前自动备份 `data/stock_fund.db` 数据库文件
- 更新失败时自动从备份恢复数据库
- 只恢复数据库文件，避免覆盖新版本的其他数据文件

### 2. 无Git依赖更新
- 使用HTTP下载ZIP包替代Git克隆
- 支持从GitHub直接下载最新版本
- 使用更可靠的archive URL (`/archive/refs/heads/main.zip`) 替代API端点
- 支持镜像地址（如 `https://gh.yiun.cyou`）以提高网络访问稳定性
- 适用于Docker部署环境

### 3. 智能文件覆盖
- 仅更新非数据文件（如代码、配置等）
- 保护 `data` 目录（包含用户数据库）
- 只恢复数据库文件，不覆盖新版本的其他数据文件

### 4. 数据库迁移
- 支持数据库结构的平滑升级
- 版本化数据库模式迁移
- 自动创建版本信息表跟踪迁移历史

## 部署脚本更新

### PowerShell (deploy.ps1)
- 修改 `Prepare-SourceCode` 函数，使用ZIP下载替代Git克隆
- 增强数据保护逻辑，只恢复数据库文件
- 添加错误处理和清理机制

### Shell (deploy.sh)
- 修改 `prepare_source_code` 函数，使用ZIP下载替代Git克隆
- 增强数据保护逻辑，只恢复数据库文件
- 添加curl/wget检测和错误处理

## 应用内更新

### 安全更新函数
- `perform_safe_update()` - 执行安全的更新流程
- `backup_database()` - 数据库备份功能
- `migrate_database_schema()` - 数据库迁移功能

### API端点
- `/api/update/check` - 检查更新
- `/api/update/perform` - 执行更新（使用安全更新函数）
- `/api/update/restart` - 重启应用

## 版本管理

### VERSION文件
- 项目根目录的 `VERSION` 文件跟踪当前版本
- 支持语义化版本号比较
- 用于检查远程更新

## 使用说明

### 一键部署更新
```bash
# Linux/macOS
./deploy.sh

# Windows
.\deploy.ps1
```

### 应用内更新
通过Web界面访问 `/update` 页面或调用API端点进行更新。

## 安全保障

1. **数据备份**: 每次更新前都会创建数据库备份
2. **事务处理**: 数据库迁移使用事务确保一致性
3. **错误恢复**: 更新失败时自动恢复数据库
4. **文件保护**: 保护 `data` 目录（包含用户数据库）不被覆盖
5. **版本控制**: 支持版本化的数据库迁移

## 注意事项

- 确保 `data` 目录有足够的磁盘空间用于备份
- 更新过程中不要中断应用运行
- 如需回滚，可以从备份文件手动恢复数据库

## 故障排除

### 网络连接问题
如果在下载过程中遇到SSL连接错误（如 `curl: (35) OpenSSL SSL_connect: SSL_ERROR_SYSCALL`），可以尝试以下解决方案：

1. **新版脚本已改进下载方式**：
   - 我们的部署脚本现在使用更可靠的archive URL (`/archive/refs/heads/main.zip`)
   - 这种方式比API端点更稳定，减少了SSL连接问题
   - 支持镜像地址（如 `https://gh.yiun.cyou`）以提高网络访问稳定性

2. **使用镜像地址**：
   - 如果直接访问GitHub有问题，可以使用镜像地址
   - 例如：`wget https://gh.yiun.cyou/https://github.com/KevinZjYang/stock/archive/refs/heads/main.zip`

3. **使用不同的下载方式**：
   ```bash
   # 手动下载ZIP文件
   wget https://github.com/KevinZjYang/stock/archive/refs/heads/main.zip
   unzip main.zip
   # 然后手动复制文件
   ```

4. **检查网络连接**：
   - 确认网络连接稳定
   - 检查防火墙或代理设置
   - 尝试使用不同的网络环境

5. **重试机制**：
   - 网络问题通常是临时的，稍后重试可能成功
   - 可以多次尝试运行部署脚本