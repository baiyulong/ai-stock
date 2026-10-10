# 📈 TDX 量化交易系统

> 基于通达信行情的 A 股量化选股 + 交易监控 + 自动告警平台

[![Go Version](https://img.shields.io/badge/Go-1.22+-00ADD8?style=flat&logo=go)](https://golang.org)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python)](https://python.org)
[![Vue](https://img.shields.io/badge/Vue-3-4FC08D?style=flat&logo=vue.js)](https://vuejs.org)
[![Docker](https://img.shields.io/badge/Docker-支持-2496ED?style=flat&logo=docker)](https://www.docker.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**感谢源作者 [injoyai](https://github.com/injoyai/tdx)，请支持原作者！**

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    浏览器 (Vue 3 + Vela)                  │
│  自选 | 选股 | 监控 | 忽略 | 待买 | 持仓 | 设置           │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP :18080
┌────────────────────────▼────────────────────────────────┐
│              Go 后端服务 (web/server.exe)                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐  │
│  │ TDX 行情  │ │ DuckDB   │ │ 前端托管  │ │ 反向代理    │  │
│  │ 连接池    │ │ 存储     │ │ static/  │ │ /api/*     │  │
│  └──────────┘ └──────────┘ └──────────┘ └─────┬──────┘  │
└─────────────────────────────────────────────────┼────────┘
                                                  │ HTTP :18081
┌─────────────────────────────────────────────────▼────────┐
│           Python 策略服务 (strategy/main.py)               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐  │
│  │ pandas   │ │ 选股引擎  │ │ 交易监控  │ │ Webhook    │  │
│  │ 指标计算  │ │ 入池分层  │ │ 待买持仓  │ │ 微信推送   │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────┘  │
│  SQLite: 选股结果 | 监控结果 | 待买 | 持仓 | 告警 | 配置    │
└──────────────────────────────────────────────────────────┘
```

---

## ✨ 功能特性

### 📊 行情与图表
- Vela K 线图，支持 8 种周期（1/5/15/30/60 分钟、日、周、月）
- 成交量副图，A 股红涨绿跌配色
- 顶部行情条：名称、代码、最新价、涨跌额、涨跌幅、今开、最高、最低、成交量
- 支持个股、大盘指数、ETF

### 🎯 底部抬高形态选股
- **入池条件**：近60日最低 > 前40日最低 + 20日内创60日新高 + 百日振幅≥25% + 日均额>2亿 + 非ST
- **分层指标**：低点抬升幅度、距低点回升、距高点空间、百日量能
- **三点验证**：支撑线、放量突破、MA60 走平上翘
- **一条证伪**：收盘价跌破前40日最低×0.99 → 结构作废
- **新形成筛选**：第二个低点在20日内形成的股票优先监控

### 💰 三锚点五公式交易参数
- **三锚点**：A（结构低点）、H（百日高点）、MA20
- **五公式**：
  - B（买入价）：回踩=max(MA20,抬升线) / 突破=T×0.98
  - L1（先导止损）= B×0.92
  - L2（硬止损）= A×0.97
  - T（目标价）= H×1.03
  - RR（盈亏比）≥ 2.0 才开仓
- **仓位计算**：资金×1%÷((B-L1)/B)，上限15%

### 🔔 待买与持仓监控
- **待买列表**：自动监控是否进入买入区（现价≤B 且 RR≥2），呼吸灯提醒
- **持仓列表**：监控止损（跌破L1减半/跌破L2清仓）和止盈（达到T）
- **告警中心**：未读计数、铃铛提醒、告警面板
- **Webhook 推送**：支持企业微信机器人、钉钉、Server酱

### ⚙️ 系统设置
- Webhook 配置与测试
- 时区设置（默认 Asia/Shanghai）
- 自动监控：交易时段每5分钟检查，收盘15:30自动同步+选股

---

## 🚀 快速开始

### 方式一：Docker 部署（推荐）⭐

```bash
# 克隆项目
git clone https://github.com/baiyulong/ai-stock.git
cd tdx-api

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 访问 http://localhost:18080
```

**服务端口**：
- Go 后端：`18080`（Web 界面 + API）
- Python 策略：`18081`（策略 API，内部使用）

### 方式二：源码运行

#### 前置要求
- Go 1.22+（需 CGO + MinGW）
- Python 3.11+
- Node.js 18+（前端构建）

#### 1. 启动 Go 后端

```bash
cd web

# Windows 需要 MinGW
$env:CGO_ENABLED="1"
$env:PATH="C:\path\to\mingw64\bin;$env:PATH"

# 编译运行
go build -o server.exe .
./server.exe
```

#### 2. 启动 Python 策略服务

```bash
cd strategy

# 安装依赖
pip install -r requirements.txt

# 启动
python main.py
```

#### 3. 构建前端（可选，已包含构建产物）

```bash
cd web/frontend
npm install
npm run build
```

#### 4. 访问
打开浏览器访问 `http://localhost:18080`

---

## 📁 项目结构

```
tdx-api/
├── web/                          # Go 后端
│   ├── server.go                 # 主服务，端口 18080
│   ├── duckdb/                   # DuckDB 存储
│   │   ├── db.go                 # 初始化+建表
│   │   ├── kline_repo.go         # 日K线读写
│   │   └── stock_repo.go         # 股票信息读写
│   ├── screener/                 # 选股相关
│   │   ├── api.go                # HTTP handler + 反向代理
│   │   └── data_pipeline.go      # 数据同步管道
│   ├── static/                   # 前端构建产物
│   ├── frontend/                 # Vue 3 前端源码
│   │   └── src/
│   │       ├── views/            # 页面组件
│   │       │   ├── WatchlistView.vue    # 自选列表
│   │       │   ├── ScreenerView.vue     # 选股页面
│   │       │   ├── MonitorView.vue      # 监控列表
│   │       │   ├── IgnoreView.vue       # 忽略名单
│   │       │   ├── WatchBuyView.vue     # 待买列表
│   │       │   ├── PositionView.vue     # 持仓列表
│   │       │   ├── SettingsView.vue     # 系统设置
│   │       │   └── ChartView.vue        # K线图
│   │       ├── providers/ashare.ts      # A股数据 provider
│   │       └── api.ts                   # API 封装
│   └── Dockerfile                # Go 服务 Dockerfile
├── strategy/                     # Python 策略服务
│   ├── main.py                   # FastAPI 入口，端口 18081
│   ├── config.py                 # 策略阈值配置
│   ├── db.py                     # 数据加载 + SQLite 持久化
│   ├── indicators.py             # pandas 滚动窗口指标
│   ├── screener.py               # 入池筛选 + 分层 + 排序
│   ├── detail.py                 # 单票三点验证 + 证伪
│   ├── trading.py                # 三锚点 + 五公式
│   ├── monitor.py                # 批量实时监控
│   ├── portfolio.py              # 待买 + 持仓监控
│   ├── scheduler.py              # 定时任务 + Webhook
│   ├── persistence.py            # SQLite 持久化（7张表）
│   ├── backtest.py               # 策略回测
│   ├── requirements.txt          # Python 依赖
│   └── Dockerfile                # Python 服务 Dockerfile
├── docker-compose.yml            # Docker 编排
├── start.bat                     # Windows 一键启动
└── README.md
```

---

## 🔌 API 接口

### 行情接口（Go 后端 :18080）

| 接口 | 说明 | 示例 |
|-----|------|------|
| `/api/quote` | 五档行情 | `?code=000001` |
| `/api/kline` | K线数据 | `?code=000001&type=day` |
| `/api/kline-history` | 前复权K线 | `?code=000001&type=day` |
| `/api/index` | 指数行情 | `?code=sh000001` |
| `/api/search` | 搜索股票 | `?keyword=平安` |
| `/api/batch-quote` | 批量行情 | `?code=000001,000002` |

### 选股策略接口（Python :18081，经 Go 反向代理）

| 接口 | 方法 | 说明 |
|-----|------|------|
| `/api/screener/run` | POST | 执行选股 |
| `/api/screener/results` | GET | 获取选股结果 |
| `/api/screener/stock/{code}` | GET | 单票详细诊断 |
| `/api/screener/monitor` | GET/POST | 实时监控 |
| `/api/screener/sync` | POST | 触发数据同步 |
| `/api/screener/webhook` | GET/POST | Webhook 配置 |
| `/api/screener/timezone` | GET/POST | 时区配置 |

### 持仓交易接口

| 接口 | 方法 | 说明 |
|-----|------|------|
| `/api/portfolio/watch-buy` | GET/POST/DELETE | 待买列表管理 |
| `/api/portfolio/watch-buy/check` | POST | 检查买入信号 |
| `/api/portfolio/positions` | GET/POST/DELETE | 持仓列表管理 |
| `/api/portfolio/positions/check` | POST | 检查止损止盈 |
| `/api/portfolio/alerts` | GET | 告警列表 |
| `/api/portfolio/alerts/{id}/read` | POST | 标记已读 |
| `/api/portfolio/check` | POST | 执行完整检查 |

---

## ⚙️ 配置说明

### Webhook 推送

支持以下格式自动适配：
- **企业微信机器人**：`https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx`
- **钉钉机器人**：`https://oapi.dingtalk.com/robot/send?access_token=xxx`
- **Server酱**：`https://sctapi.ftqq.com/你的SendKey.send`

在「设置」页面配置 Webhook 地址，点击「发送测试消息」验证。

### 策略参数

在 `strategy/config.py` 中可调整：
- 入池阈值（振幅、成交额等）
- 分层阈值（回升比例、空间比例等）
- 交易参数（止损比例、目标比例、RR 门槛等）

---

## 📊 数据说明

- **DuckDB**：存储 5226 只股票的日K线数据（73万+条）
- **SQLite**：存储选股结果、监控结果、待买、持仓、告警、配置
- **数据同步**：收盘后自动从通达信增量同步，也可手动触发

---

## ⚠️ 免责声明

本系统仅供学习和研究使用，不构成任何投资建议。股市有风险，投资需谨慎。

> 本回答由AI生成，仅供参考，请仔细甄别，谨慎投资。

---

## 📄 License

MIT License
