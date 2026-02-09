# 股票基金监控系统

<p align="center">
    <img src="https://img.shields.io/badge/Python-3.8+-blue?style=for-the-badge&logo=python" alt="Python">
    <img src="https://img.shields.io/badge/Flask-2.3+-black?style=for-the-badge&logo=flask" alt="Flask">
    <img src="https://img.shields.io/badge/SQLite-3+-lightgrey?style=for-the-badge&logo=sqlite" alt="SQLite">
    <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License">
</p>

一个基于 Flask 开发的股票和基金监控系统，支持实时价格监控、基金投资跟踪、价格变动通知等功能。系统采用模块化设计，界面简洁直观，支持多市场品种监控。

## 功能特性

### 核心功能

| 功能 | 描述 |
|------|------|
| 股票监控 | 实时监控沪A、深A、港股、美股等市场股票价格变动 |
| 基金查询 | 支持公募基金净值实时查询与关注列表管理 |
| 投资跟踪 | 记录基金交易记录，自动计算持仓、收益与年化收益率 |
| 价格通知 | 设置价格阈值提醒，支持企业微信机器人推送 |
| 指数监控 | 同步显示上证指数、深证成指、创业板指等主要指数 |
| 日志系统 | 完整的系统运行日志记录与查看 |

### 主要特性

- **多市场支持**：覆盖沪市、深市、港股、美股、指数、基金等多个市场
- **实时刷新**：股票10秒自动刷新，基金10分钟自动刷新（可配置）
- **页面状态保持**：刷新页面后保持当前视图，无需重新切换
- **响应式设计**：适配桌面端与移动端设备
- **数据缓存**：请求智能缓存，减少API调用压力
- **本地数据**：基于SQLite数据库，数据完全本地存储

## 项目架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Flask 应用层                            │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │
│  │ 股票模块 │  │ 基金模块 │  │交易模块 │  │通知模块 │        │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘        │
├─────────────────────────────────────────────────────────────┤
│                      数据模型层                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │         SQLite 数据库 (关注列表、交易记录、通知)      │    │
│  └─────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│                      外部 API 层                             │
│  ┌────────────────┐  ┌────────────────────────────┐        │
│  │ 雪球财经API     │  │ autostock.cn 基金API       │        │
│  └────────────────┘  └────────────────────────────┘        │
└─────────────────────────────────────────────────────────────┘
```

### 模块说明

| 模块 | 文件 | 功能 |
|------|------|------|
| 核心入口 | `app.py` | 应用初始化、蓝图注册、路由分发 |
| 数据模型 | `modules/models.py` | 数据库初始化、通用工具、日志基础设施 |
| 股票模块 | `modules/stock_module.py` | 股票API、关注列表、实时数据获取 |
| 基金模块 | `modules/fund.py` | 基金API、关注列表、指数数据 |
| 交易模块 | `modules/fund_trans.py` | 交易记录管理、导入导出、收益统计 |
| 通知模块 | `modules/notify.py` | 价格通知、企业微信推送、监控线程 |
| 日志模块 | `modules/log.py` | 系统日志API、日志管理 |

## 技术栈

- **后端框架**: Flask 2.3+
- **数据库**: SQLite 3
- **前端模板**: Jinja2
- **HTTP客户端**: Requests
- **数据处理**: Pandas
- **图表库**: Chart.js

## 快速开始

### 环境要求

- Python 3.8 或更高版本
- pip 包管理器
- 至少 100MB 磁盘空间

### 安装部署

#### 方式一：在线一键部署（推荐）

**Windows (PowerShell)**：
```powershell
powershell -ExecutionPolicy Bypass -Command "Invoke-RestMethod -Uri 'https://raw.githubusercontent.com/KevinZjYang/stock/main/deploy.ps1' | Invoke-Expression"
```

**Linux/macOS**：
```bash
curl -sSL https://raw.githubusercontent.com/KevinZjYang/stock/main/deploy.sh | bash
```

#### 方式二：手动部署

```bash
# 1. 克隆项目
git clone https://github.com/KevinZjYang/stock.git
cd stock

# 2. 创建虚拟环境（可选但推荐）
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或
.\venv\Scripts\activate   # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动应用
python app.py
```

> **注意**：首次启动会自动创建数据库文件和必要的目录结构。

#### 方式三：Docker 部署（推荐用于生产环境）

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 3333
CMD ["python", "app.py"]
```

```bash
# 构建并运行
docker build -t stock-monitor .
docker run -d -p 3333:3333 -v $(pwd)/data:/app/data -v $(pwd)/logs:/app/logs stock-monitor
```

### 访问应用

启动成功后，浏览器访问：**http://localhost:3333**

默认端口为 `3333`，可在 `.env` 文件中修改。

## 配置说明

### 环境变量

在项目根目录创建 `.env` 文件（参考 `.env.example`）：

| 变量名 | 默认值 | 描述 |
|--------|--------|------|
| `FLASK_ENV` | `development` | 运行环境（development/production） |
| `SECRET_KEY` | 随机字符串 | Flask密钥 |
| `SERVER_PORT` | `3333` | 服务端口 |
| `REFRESH_INTERVAL_STOCK` | `10` | 股票刷新间隔（秒） |
| `REFRESH_INTERVAL_FUND` | `600` | 基金刷新间隔（秒） |
| `WEBHOOK_URL` | 空 | 企业微信机器人Webhook URL |

### 目录结构

```
stock/
├── app.py                    # 应用入口
├── requirements.txt          # Python依赖
├── .env                      # 环境配置（需手动创建）
├── .env.example              # 环境配置示例
├── .gitignore               # Git忽略配置
├── README.md                # 项目文档
├── LICENSE                  # MIT许可证
│
├── data/                    # 数据目录
│   └── stock_fund.db        # SQLite数据库文件
│
├── basedata/                # 基础数据
│   └── code.xlsx            # 股票/基金代码数据
│
├── logs/                    # 日志目录
│   └── app.log              # 应用日志
│
├── static/                  # 静态资源
│   ├── css/
│   │   └── common.css       # 公共样式
│   └── js/
│       └── common.js        # 公共脚本
│
├── templates/               # HTML模板
│   ├── master.html          # 主框架模板
│   ├── stock_detail.html    # 股票监控页面
│   ├── fund_detail.html     # 基金查询页面
│   ├── fund_trans.html      # 基金交易页面
│   ├── notification.html    # 通知管理页面
│   └── update.html          # 系统更新页面
│
└── modules/                 # 功能模块
    ├── models.py            # 数据模型
    ├── stock_module.py      # 股票模块
    ├── fund.py              # 基金模块
    ├── fund_trans.py        # 交易模块
    ├── notify.py            # 通知模块
    └── log.py               # 日志模块
```

## API 接口文档

### 股票相关接口

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/stock/search` | 搜索股票/基金代码 |
| GET | `/api/stock/prices` | 获取关注股票实时价格 |
| GET | `/api/stock/watchlist` | 获取股票关注列表 |
| POST | `/api/stock/watchlist` | 添加股票到关注列表 |
| DELETE | `/api/stock/watchlist` | 从关注列表移除股票 |

#### 搜索接口响应示例

```json
{
    "excel_results": [
        {
            "code": "600519",
            "name": "贵州茅台",
            "type": "11"
        },
        {
            "code": "000001",
            "name": "上证指数",
            "type": "20"
        }
    ]
}
```

类型编码：`11`=沪A, `12`=深A, `13`=港股, `14`=转债, `15`=基金, `16`=美股, `20`=指数

### 基金相关接口

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/fund/prices` | 获取关注基金实时净值 |
| GET | `/api/fund/watchlist` | 获取基金关注列表 |
| POST | `/api/fund/watchlist` | 添加基金到关注列表 |
| DELETE | `/api/fund/watchlist` | 从关注列表移除基金 |

### 基金交易接口

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/fund_trans/transactions` | 获取交易记录列表 |
| POST | `/api/fund_trans/transactions` | 添加单条交易记录 |
| DELETE | `/api/fund_trans/transactions` | 删除交易记录 |
| GET | `/api/fund_trans/summary` | 获取投资收益汇总 |
| POST | `/api/fund_trans/import` | 批量导入交易记录 |
| GET | `/api/fund_trans/export` | 导出交易记录 |

#### 交易汇总响应示例

```json
{
    "total_invested": 50000.00,
    "current_value": 55000.00,
    "profit": 5000.00,
    "profit_rate": 0.10,
    "annualized_rate": 0.15,
    "positions": [
        {
            "fund_code": "161039",
            "fund_name": "富国天惠成长",
            "shares": 10000.00,
            "cost": 1.5000,
            "current": 1.6500,
            "profit": 1500.00
        }
    ]
}
```

### 通知相关接口

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/notifications` | 获取通知条件列表 |
| POST | `/api/notifications` | 添加通知条件 |
| DELETE | `/api/notifications` | 删除通知条件 |
| GET | `/api/webhook` | 获取Webhook配置 |
| POST | `/api/webhook` | 设置Webhook地址 |

### 日志相关接口

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/log/list` | 获取系统日志 |
| POST | `/api/log/clear` | 清空系统日志 |

## 使用指南

### 添加股票/基金

1. 在对应页面的搜索框中输入代码或名称
2. 从下拉列表选择目标
3. 点击"添加"按钮

### 设置价格通知

1. 进入"价格通知"页面
2. 点击"添加监控"按钮
3. 选择监控品种、设置阈值条件
4. 配置企业微信Webhook（可选）

### 记录基金交易

1. 进入"基金交易"页面
2. 点击"添加交易"按钮
3. 输入交易日期、代码、份额、单价
4. 系统自动计算持仓与收益

### 导入导出交易记录

支持 CSV/Excel 格式导入导出：

**导入格式**：
```csv
交易日期,基金代码,基金名称,交易类型,份额,单价,手续费
2024-01-15,161039,富国天惠成长,买入,1000.00,1.523,0.00
2024-03-20,161039,富国天惠成长,卖出,500.00,1.612,0.50
```

## 常见问题

### Q: 股票数据不更新？
A: 检查网络连接，确认雪球API可访问。日志中可查看详细错误信息。

### Q: 如何修改刷新间隔？
A: 在页面右上角点击"设置"按钮，可分别调整股票和基金的刷新间隔。

### Q: 企业微信通知收不到？
A: 确认Webhook URL正确配置，且企业微信机器人未被禁用。

### Q: 页面显示异常？
A: 尝试清除浏览器缓存，或使用无痕模式访问。

### Q: 如何备份数据？
A: 复制 `data/stock_fund.db` 文件即可，该文件包含所有数据。

## 第三方服务

| 服务 | 用途 | 文档 |
|------|------|------|
| 雪球财经 | 股票/指数数据 | https://xueqiu.com |
| autostock.cn | 基金净值数据 | https://autostock.cn |

## 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 更新日志

### v2.0.0 (2024-xx-xx)
- 重构前端代码，提取公共样式和脚本
- 添加页面状态保持功能
- 优化搜索组件视觉效果
- 支持年化收益率计算
- 提升交易记录加载性能

### v1.x
- 初始版本发布
- 基础股票/基金监控功能
- 基金交易记录管理
- 价格通知功能

## 许可证

本项目采用 MIT License 开源，详见 [LICENSE](LICENSE) 文件。

## 免责声明

本系统仅供学习研究使用，不构成任何投资建议。投资者据此操作，风险自担。

---

<p align="center">
    Made with ❤️ by KevinZjYang
</p>
