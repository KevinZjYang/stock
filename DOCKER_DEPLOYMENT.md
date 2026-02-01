# Docker 部署指南

## 项目概述

这是一个基于 Flask 开发的股票基金监控系统，支持实时价格监控、基金投资跟踪、价格变动通知等功能。

## Docker 部署

### 环境要求

- Docker Engine 19.03 或更高版本
- Docker Compose v2.0 或更高版本

### 快速部署（推荐）

使用自动化部署脚本一键完成部署：

#### Windows (PowerShell):
```powershell
# 设置执行策略（首次运行）
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 运行部署脚本（默认从 https://github.com/KevinZjYang/stock 克隆）
.\deploy.ps1
```

#### Windows (命令提示符):
```cmd
# 运行部署脚本（默认从 https://github.com/KevinZjYang/stock 克隆）
deploy.bat
```

### 传统部署方式

如果您希望手动部署：

1. 克隆项目代码：
   ```bash
   git clone https://github.com/KevinZjYang/stock
   cd stock
   ```

2. 构建并启动容器：
   ```bash
   docker-compose up -d
   ```

3. 访问应用：
   - 打开浏览器访问 `http://localhost:3333`

### 配置说明

#### 数据持久化

- `./data` 目录映射到容器内的 `/app/data`，用于存储 SQLite 数据库文件
- `./logs` 目录映射到容器内的 `/app/logs`，用于存储应用日志
- `./templates` 目录映射到容器内的 `/app/templates`，用于存放前端模板

#### 环境变量

可根据需要修改 `.env` 文件中的配置项：

```bash
# 应用配置
APP_PORT=3333
FLASK_ENV=production

# 日志配置
LOG_LEVEL=INFO
LOG_RETENTION_DAYS=30
```

### 管理命令

#### 查看容器状态
```bash
docker-compose ps
```

#### 查看应用日志
```bash
docker-compose logs -f stock-app
```

#### 停止应用
```bash
docker-compose down
```

#### 重启应用
```bash
docker-compose restart stock-app
```

#### 更新应用
```bash
# 拉取最新代码
git pull

# 重建镜像并启动
docker-compose up -d --build
```

### 数据备份与恢复

#### 备份数据
```bash
# 备份数据库
docker run --rm -v $(pwd)/data:/data -v $(pwd)/backup:/backup alpine tar czf /backup/stock_fund_db_$(date +%Y%m%d_%H%M%S).tar.gz -C /data .

# 备份日志
docker run --rm -v $(pwd)/logs:/logs -v $(pwd)/backup:/backup alpine tar czf /backup/logs_$(date +%Y%m%d_%H%M%S).tar.gz -C /logs .
```

#### 恢复数据
```bash
# 恢复数据库（请先停止容器）
docker-compose down
docker run --rm -v $(pwd)/data:/data -v $(pwd)/backup:/backup alpine tar xzf /backup/stock_fund_db_YYYYMMDD_HHMMSS.tar.gz -C /data
```

### 故障排除

#### 应用无法启动
1. 检查端口 3333 是否已被占用：
   ```bash
   netstat -tulpn | grep :3333
   ```

2. 查看详细错误日志：
   ```bash
   docker-compose logs stock-app
   ```

#### 数据库连接问题
1. 确认 `./data` 目录有正确的读写权限：
   ```bash
   ls -la data/
   ```

2. 检查数据库文件是否存在：
   ```bash
   ls -la data/stock_fund.db
   ```

#### 性能问题
1. 检查容器资源使用情况：
   ```bash
   docker stats stock-app
   ```

### 自定义配置

如需自定义配置，可以修改 `docker-compose.yml` 文件：

```yaml
services:
  stock-app:
    # 自定义端口映射
    ports:
      - "8080:3333"  # 将主机的8080端口映射到容器的3333端口
    
    # 自定义资源限制
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '0.5'
        reservations:
          memory: 512M
          cpus: '0.25'
```

### 生产环境建议

1. 使用反向代理（如 Nginx）来处理 HTTPS 和负载均衡
2. 定期备份数据卷
3. 监控容器资源使用情况
4. 设置适当的日志轮转策略
5. 使用专用的生产级数据库（如 PostgreSQL）替代 SQLite

### 安全注意事项

1. 不要在生产环境中暴露不必要的端口
2. 定期更新基础镜像以获得安全补丁
3. 限制对数据卷的访问权限
4. 如使用通知功能，保护好 webhook URL 等敏感信息