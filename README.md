# 股票基金监控系统

一个基于Flask开发的股票和基金监控系统，支持实时价格监控、基金投资跟踪、价格变动通知等功能。

## 功能特性

- **股票监控**：实时监控股票价格变动
- **基金监控**：实时监控基金净值变动
- **基金投资跟踪**：记录和跟踪基金投资交易
- **价格变动通知**：设置价格变动提醒，支持企业微信机器人推送
- **日志系统**：完整的系统日志记录和查看
- **指数监控**：监控主要股市指数

## 项目架构

### 模块划分

项目采用模块化设计，各功能模块职责明确：

#### 1. 核心模块 (`app.py`)
- 应用入口点
- 蓝图注册中心
- 主页路由

#### 2. 数据模型 (`modules/models.py`)
- 数据库初始化和管理
- 通用工具函数
- 日志基础设施
- 股票/基金数据服务

#### 3. 股票模块 (`modules/stock_module.py`)
- 股票相关API路由
- 股票关注列表管理
- 股票实时数据获取

#### 4. 基金模块 (`modules/fund.py`)
- 基金相关API路由
- 基金关注列表管理
- 基金实时数据获取
- 指数相关功能

#### 5. 基金交易模块 (`modules/fund_trans.py`)
- 基金交易记录管理
- 交易数据导入/导出
- 投资收益统计

#### 6. 通知模块 (`modules/notify.py`)
- 价格变动通知设置
- 企业微信机器人集成
- 通知条件管理
- 通知监控线程

#### 7. 日志模块 (`modules/log.py`)
- 系统日志API路由
- 日志查看和清理

## 技术栈

- **后端框架**: Flask
- **数据库**: SQLite
- **前端模板**: Jinja2
- **HTTP库**: Requests
- **数据处理**: Pandas

## API 接口

### 股票相关
- `GET /api/stock/prices` - 获取关注股票价格
- `GET /api/stock/watchlist` - 获取股票关注列表
- `POST /api/stock/watchlist` - 添加股票到关注列表
- `DELETE /api/stock/watchlist` - 从关注列表移除股票

### 基金相关
- `GET /api/fund/prices` - 获取关注基金价格
- `GET /api/fund/watchlist` - 获取基金关注列表
- `POST /api/fund/watchlist` - 添加基金到关注列表
- `DELETE /api/fund/watchlist` - 从关注列表移除基金

### 基金交易相关
- `GET /api/fund_trans/transactions` - 获取交易记录
- `POST /api/fund_trans/transactions` - 添加交易记录
- `DELETE /api/fund_trans/transactions` - 删除交易记录
- `GET /api/fund_trans/summary` - 获取投资汇总
- `POST /api/fund_trans/import` - 导入交易记录
- `GET /api/fund_trans/export` - 导出交易记录

### 通知相关
- `GET /api/notifications` - 获取通知条件
- `POST /api/notifications` - 添加通知条件
- `DELETE /api/notifications` - 删除通知条件
- `GET/POST /api/webhook` - 企业微信机器人设置

### 日志相关
- `GET /api/log/list` - 获取系统日志
- `POST /api/log/clear` - 清空系统日志

## 配置

### 环境变量配置
系统支持通过 `.env` 文件进行配置，具体参数见 `.env.example` 文件。

### 数据库配置
- 数据库文件: `data/stock_fund.db`
- Excel数据文件: `basedata/code.xlsx`

### 日志配置
- 日志目录: `logs/`
- 日志文件: `logs/app.log`
- 日志保留: 30天

## 部署

### 在线一键部署（推荐）

直接在命令行中运行以下命令即可开始部署（无需预先下载任何脚本）：

#### Windows PowerShell (一行命令部署):
```powershell
powershell -ExecutionPolicy Bypass -Command "Invoke-RestMethod -Uri 'https://raw.githubusercontent.com/KevinZjYang/stock/main/deploy.ps1' | Invoke-Expression"
```

#### Linux/macOS (一行命令部署):
```bash
curl -sSL https://raw.githubusercontent.com/KevinZjYang/stock/main/deploy.sh | bash
```

在线部署方式会直接从 GitHub 获取最新的部署脚本并立即执行，无需预先下载到本地。
现在用户只需要在命令行中输入一个简单的命令，就可以开始部署整个应用，真正实现了"一个链接"启动部署的功能。

### 传统部署方式

如果需要手动部署：

```bash
# 克隆项目
git clone https://github.com/KevinZjYang/stock
cd stock

# 安装依赖（如果直接运行）
pip install -r requirements.txt

# 启动应用
python app.py
```

应用默认运行在 `http://0.0.0.0:3333`

## 文件结构

```
stock/
├── app.py                 # 应用入口
├── requirements.txt       # 依赖包列表
├── README.md             # 项目说明
├── LICENSE              # 许可证
├── data/                # 数据文件
│   ├── stock_fund.db    # SQLite数据库
├── basedata\            # 基础数据目录
│   └── code.xlsx        # 股票代码Excel文件
├── logs/                # 日志文件
├── templates/           # 前端模板
└── modules/             # 功能模块
    ├── models.py        # 数据模型和工具
    ├── stock_module.py  # 股票模块
    ├── fund.py          # 基金模块
    ├── fund_trans.py    # 基金交易模块
    ├── notify.py        # 通知模块
    └── log.py           # 日志模块
```

## 第三方API

- 股票数据API: 雪球财经API
- 基金数据API: autostock.cn API

## 许可证

MIT License