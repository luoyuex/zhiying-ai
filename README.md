# 智盈 AI（zhiying-ai）

A 股 AI 分析工作台。前端 Vue 3 + TypeScript，后端 FastAPI + PostgreSQL + Redis。

当前进度：**P1 项目骨架 + 邮箱验证码认证**（完成）；**P2 行情数据层**（报价 + K 线 + 缓存/限流/熔断已通，财务/资金流/情绪已补，新闻/搜索待做）；**P3 进行中**（行情速查 + 个股详情页 v1 已上线，搜索/自选/klinecharts 指标待做）；**P4 六分析师 + 首席决策** 已上线；**P5 历史报告** 已落库（PDF/并排对比待做）。

**当前可用功能**

- 邮箱验证码注册、密码/验证码登录、重置密码
- 工作台「个股查询」：输入 6 位代码或点快捷标的，**直接进入个股详情页**；工作台不再预加载行情，避免重复查询
- 个股详情页 `/stock/:symbol`：统一加载报价、12 项指标、日/周/月 K、前复权/后复权/不复权；支持页面内切换代码
- **技术面诊断**：基于 90 根日 K 前复权计算评分/评级、趋势、MA/MACD/RSI/BOLL/ATR/量比信号、支撑压力，以及由代码计算的三档价位
- **六维数据**：行情/技术、财务指标（东财 F10，最近 6 期）、资金流（东财近 30 日）、市场情绪（ARBR/换手/RSI/指数）、公开网页（元宝搜索）
- **六分析师 + 首席决策**：技术面/基本面/资金面/风险/情绪/新闻六份结构化报告由代码基于真实数据生成；首席策略官 LLM 做最终决策（买入/持有/卖出 + 操作建议/持有周期/仓位/风险），失败自动规则兜底；三档价位始终由代码计算
- **历史报告**：每次生成落库 PostgreSQL；顶栏头像菜单 →「历史报告」可查看当前用户全部记录（按日期分组、代码/名称筛选），也可在个股页查看该股最近 6 份；报告页完整展示六分析师全部依据/风险/数据源与首席决策
- **元宝搜索（可选）**：一次 AI 分析最多 1 次公开网页检索，缓存 30 分钟；命中 6h 报告缓存时连搜索也跳过
- 接口：`/api/v1/stocks/{symbol}/quote`、`/kline`、`/analysis`、`/ai-analysis`、`/api/v1/ai/jobs/{id}`、`/api/v1/analysis/reports`

> 📋 完整的开发计划、已完成/未完成清单与风险登记见 **[docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md)**。

---

## 快速开始

### 0. 环境要求

| 依赖 | 版本 | 说明 |
| --- | --- | --- |
| Docker | 24+ | 跑 PostgreSQL 16 与 Redis 7 |
| Python | 3.12+ | 用 uv 管理虚拟环境 |
| uv | 0.5+ | `pip install uv` 或官方脚本安装 |
| Node.js | 20+ | 前端构建 |

### 1. 准备配置

```bash
cp .env.example .env
```

`.env` 里已有本地生成的 `JWT_SECRET` / `OTP_SECRET`（仓库中的 `.env` 已带默认值，可跳过复制）。

### 2. 启动数据库与缓存

```bash
npm run up          # 等价于 docker compose up -d
```

### 3. 启动后端

```bash
cd backend
uv sync             # 首次安装依赖
uv run alembic upgrade head   # 建表
uv run uvicorn app.main:app --reload --port 8010
```

后端地址 <http://127.0.0.1:8010>，接口文档 <http://127.0.0.1:8010/docs>，健康检查 `/health`。

AI 分析任务由独立队列执行，另开一个终端启动 worker（不启动时发起分析会返回 503「分析队列未启动」）：

```bash
uv run arq app.worker.WorkerSettings
```

根目录等价命令：`npm run worker`。只做本地临时调试时可以设 `AI_JOB_EXECUTION=inline`，任务会退回进程内执行，重启即中断。

初始化股票库（全量 A 股代码 / 名称 / 拼音，约 5900 只，用于查询补全）：

```bash
uv run python -m app.scripts.seed_stocks
```

新股 / 退市后重跑同一命令即可增量刷新；根目录也可用 `npm run seed`。

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

打开 <http://localhost:5288>，Vite 已把 `/api` 代理到 `127.0.0.1:8010`。

根目录也可以用 `npm run api` / `npm run web` 启动（等价命令）。

### 端口约定

| 服务 | 端口 | 说明 |
| --- | --- | --- |
| 前端（Vite） | **5288** | 固定端口，`strictPort: true`，被占用会直接报错而不是自动换端口 |
| 后端（FastAPI） | **8010** | 只用 127.0.0.1，不对外暴露 |
| PostgreSQL | 5432 | Docker |
| Redis | 6379 | Docker |

改后端端口需要同时改三处：`package.json` 的 `api` 脚本、`Makefile` 的 `api` 目标、`frontend/vite.config.ts` 的 proxy `target`。


---

## 邮件配置（验证码真实发信）

默认 `EMAIL_MODE=console`，验证码只打印在后端日志里，方便本地开发。

要真实发信，编辑根目录 `.env`：

```env
EMAIL_MODE=smtp
SMTP_HOST=smtp.qq.com      # QQ 邮箱；163 用 smtp.163.com；Gmail 用 smtp.gmail.com
SMTP_PORT=465              # 465 走 SSL，587 走 STARTTLS
SMTP_USER=你的邮箱@qq.com
SMTP_PASSWORD=授权码        # 注意：邮箱设置里生成的授权码，不是登录密码
SMTP_FROM_NAME=智盈 AI
```

QQ 邮箱授权码获取：设置 → 账户 → 开启 SMTP 服务 → 生成授权码。

改完重启后端即可，无需改代码。

---

## LLM 配置（AI 综合研判）

任意兼容 OpenAI `/chat/completions` 的服务都可以。编辑根目录 `.env`：

```env
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=你的 Key
LLM_MODEL=deepseek-chat
LLM_TIMEOUT_SECONDS=180
LLM_ANALYST_TIMEOUT_SECONDS=150
LLM_ANALYST_CONCURRENCY=3
LLM_JOB_TIMEOUT_SECONDS=600
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=0.3
LLM_CACHE_SECONDS=21600
```

> `LLM_TIMEOUT_SECONDS` 是单次调用超时；`LLM_ANALYST_TIMEOUT_SECONDS` 是每位分析师的超时；`LLM_JOB_TIMEOUT_SECONDS` 是整个后台任务超时。六位分析师按 `LLM_ANALYST_CONCURRENCY` 并发，免费/低配模型建议保持 3。推理型模型思考也消耗 token，`LLM_MAX_TOKENS` 不要低于 4096。
>
> 开发期不想被额度挡住：在 `.env` 设 `AI_DAILY_QUOTA_OVERRIDE=9999`，所有用户统一按该额度计算；设为 `0` 则恢复使用用户表的 `daily_analysis_quota`。改完需重启后端。

改完重启后端。未配置时详情页会显示引导，不会发起 LLM 请求；配置后：
- `GET /api/v1/ai/config` 返回 `configured=true` 与当前模型
- 详情页「开始 AI 分析」提交后台任务；进度优先走 SSE `GET /api/v1/ai/jobs/{job_id}/events`（snapshot / phase / done），连接失败自动回退轮询 `GET /api/v1/ai/jobs/{job_id}`
- 每次成功生成消耗 1 次 `daily_analysis_quota`；同股同交易日 + 同模型 + 同提示词版本 6 小时内直接复用，不重复消耗
- 任务在后台执行，页面切走不会中断；重新点击会复用仍在运行的任务

> 分析流程：六位分析师并发 → 团队讨论（LLM 整理 4-6 轮交叉回应）→ 首席策略官决策。任一步失败会自动回退到规则版，并在报告中标记 `engine=rule` / `source=rule`。整份报告仍只消耗 1 次额度。
>
> 任务执行：默认 `AI_JOB_EXECUTION=arq`，由 `npm run worker` 消费；API 重启不会中断分析，worker 优雅重启会等待在跑任务结束。worker 每 30 秒写入心跳 `ai:worker:alive`（TTL 120 秒），没有心跳时新任务直接返回 503。

---

## 元宝搜索（公开网页信息）

腾讯云联网搜索 WSA `SearchPro`。注意不是 You.com 的 `YDC_API_KEY`。

推荐使用官方腾讯云 API 3.0（TC3-HMAC-SHA256 签名）：

```env
WSA_SECRET_ID=腾讯云 SecretId（AKID 开头）
WSA_SECRET_KEY=腾讯云 SecretKey
# 临时密钥才需要；长期密钥留空
WSA_SECRET_TOKEN=
WSA_SEARCH_HOST=wsa.tencentcloudapi.com
WSA_SEARCH_VERSION=2025-05-08
WSA_SEARCH_COUNT=20
WSA_SEARCH_TOP_N=8
WSA_SEARCH_FRESHNESS=m3
WSA_SEARCH_CACHE_SECONDS=1800
```

如果拿到的是参考项目那种 Bearer 服务 API KEY（`sk-` 开头），也可以只填 `WSA_API_KEY`（与 SecretId/SecretKey 二选一；同时填时优先官方 API）：

```env
WSA_API_KEY=服务 API KEY（sk- 开头）
WSA_SEARCH_URL=https://api.wsa.cloud.tencent.com/SearchPro
```

注意：`AKID` 开头的是 SecretId，不是服务 API KEY。填错时后端会在发请求前直接返回配置提示，不会浪费一次调用。

规则：
- **一次个股 AI 分析最多 1 次搜索**，不按分析师/维度重复调用
- 命中 AI 报告的 6h 缓存时，连搜索也跳过
- 搜索结果缓存 30 分钟，同一股票短时间重复分析不再消耗搜索
- 未配置凭据或搜索失败时自动跳过，不影响 AI 分析
- 官方模式请求 `Mode=0`（公开网页）、`Industry=finance`、`Cnt` 20 条，并按 `WSA_SEARCH_FRESHNESS` 追加时效；Bearer 模式保持原有 `Query/Cnt/Mode/Industry` 参数，不追加 `Freshness`
- 官方 API 的 `Freshness`、`Mode`、`Cnt`、`Industry` 仅标准版/旗舰版支持；极速版（lite）会拒绝这些参数，需要升级版本或改用 Bearer 兼容模式
- 结果作为 `public_web_info` 进入 prompt（带 title/site/date/url），只作新闻/事件背景；页面展示来源链接和数据覆盖说明
- 搜索结果进入多位分析师：新闻（来源列表）、基本面（公司动态线索）、风险（减持/解禁/处罚等事件线索）、情绪（正面/负面关键词计数）；「公开信息」面板会显示「已用于：XX分析师」
- 前端展示：报告详情页顶部带「元宝搜索 · 已检索 N 条 / 本次未收录」状态标签；报告页与 AI 卡内始终有「公开信息」面板——有来源列出来源，没有来源时说明该报告未包含公开网页信息、相关结论按数据缺口处理
- 官方错误码会转成可读提示：`AuthFailure.*`/`UnauthorizedOperation` 鉴权失败、`ResourceNotFound`/`ResourceUnavailable` 未开通、`RequestLimitExceeded` 频率超限

### 怎么确认已经接通

先检查配置（不发起调用、不产生费用）：

```powershell
cd D:\code\AI\zhiying-ai\backend
.\.venv\Scripts\python.exe manual_test_wsa.py
```

输出会显示 `官方 TC3` / `服务 API KEY（Bearer）` / `未配置`，以及 Host、Version、Freshness。

真实连通性检查会消耗一次搜索调用：

```powershell
.\.venv\Scripts\python.exe manual_test_wsa.py --live
```

成功时会打印 `success=True`、`version`（standard/flagship）、结果条数和前 5 条来源。也可以在跑完一次 AI 分析后看产品结果：`web_search_used=true`、新闻分析师不再标记「公开网页缺失」、报告页出现「公开信息来源（元宝搜索）」小节。失败时后端日志会打印「元宝搜索未返回结果: 原因」。

---

## 项目结构

```
zhiying-ai/
├─ backend/
│  ├─ app/
│  │  ├─ main.py              FastAPI 装配、异常处理、/health
│  │  ├─ core/                配置、安全、日志、错误码、依赖注入
│  │  ├─ db/                  SQLAlchemy 会话、模型、Redis 客户端
│  │  ├─ providers/           行情数据源（腾讯/新浪/东财）+ 缓存/限流/熔断
│  │  ├─ llm/                 OpenAI 兼容客户端 + 提示词 + 版本
│  │  ├─ schemas/             Pydantic 请求/响应模型
│  │  ├─ services/            otp / mail / auth / 行情 / 技术诊断 / AI 分析
│  │  └─ api/v1/              认证 + 行情 + AI 配置路由
│  ├─ alembic/                数据库迁移
│  └─ tests/                  端到端测试（跑真实 PG + Redis）
├─ frontend/
│  └─ src/
│     ├─ api/                 axios 客户端（401 单飞续期）+ 认证 / 行情接口
│     ├─ stores/auth.ts       Pinia 会话
│     ├─ router/              路由与守卫
│     ├─ components/          UI 基础组件 + 布局 + market（行情速查 / 迷你 K 线）
│     ├─ pages/               登录 / 注册 / 重置密码 / 工作台 / 个股详情 / 历史报告 / 分析报告
│     └─ styles/              设计 token（浅色清爽数据风）
├─ docker-compose.yml         本地 PostgreSQL + Redis
├─ docs/ARCHITECTURE.md       架构说明
└─ .env.example               配置模板
```

---

## 认证设计要点

- **验证码**：6 位数字，HMAC-SHA256 哈希后存 Redis，TTL 300 秒，一次性使用；错 5 次立即作废。
- **限流**：同邮箱 60 秒冷却、单邮箱每日 10 次、单 IP 每小时 20 次。
- **access token**：JWT HS256，15 分钟，只存在前端内存。
- **refresh token**：随机 32 字节，httpOnly Cookie，7 天，每次刷新轮换；检测到旧 token 重放即吊销该用户全部会话。
- **密码**：Argon2id 哈希；至少 8 位且含字母和数字。

接口一览（前缀 `/api/v1/auth`）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/email/send-code` | 发送验证码（purpose: register/login/reset） |
| POST | `/register` | 邮箱验证码注册，返回 access + Set-Cookie |
| POST | `/login` | 密码登录 |
| POST | `/login/code` | 验证码登录 |
| POST | `/password/reset` | 验证码重置密码 |
| POST | `/refresh` | 轮换刷新令牌 |
| POST | `/logout` | 退出登录 |
| GET | `/me` | 当前用户 |

行情接口（前缀 `/api/v1/stocks`，需登录）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/{symbol}/quote` | 实时报价（腾讯→新浪→东财自动降级） |
| GET | `/{symbol}/kline` | K 线（东财→腾讯→新浪），支持 `period` / `adjust` / `limit` |
| GET | `/{symbol}/analysis` | 技术面诊断（规则引擎）：评分/信号/支撑压力/三档价位 |
| POST | `/{symbol}/ai-analysis` | 创建 LLM 分析后台任务（202，返回 job_id）；6h 缓存 + 每日额度 |

AI 配置状态（前缀 `/api/v1/ai`，需登录）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/config` | 返回 configured / model / prompt_version / daily_quota / quota_used |
| GET | `/jobs/{job_id}` | 查询后台分析任务状态、阶段、已等待秒数与结果 |

历史报告（前缀 `/api/v1/analysis/reports`，需登录）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `?limit=50` | 当前用户全部历史报告（不传 symbol）；`/reports` 页面使用 |
| GET | `?symbol=600519&limit=6` | 当前用户某只股票的历史报告列表（个股页使用） |
| GET | `/{report_id}` | 回看完整六分析师报告与最终决策 |

数据约定：价格=元、成交量=股、成交额=元；返回 `source` / `fetched_at` / `delayed`。缓存过期但上游全挂时返回 stale 数据并置 `delayed=true`。

---

## 测试

```bash
cd backend
uv run pytest -q
```

测试会真实写入 PostgreSQL 与 Redis（使用 `test-xxxx@example.com` 临时账号，结束后自动清理），运行前请先 `npm run up` 并执行迁移。

当前覆盖 70 个用例（含参数化）：认证链路、行情 Provider/缓存/API、技术诊断、LLM/六分析师/异步任务、元宝搜索（官方 TC3 + Bearer）与历史报告。

---

## 下一步

1. P4：六位分析师逐位接 LLM（当前为规则+数据），再上 ARQ/SSE 流式
2. P3：股票名称/拼音搜索 + 自选股 + klinecharts 指标（MA/MACD/BOLL）
3. P5：历史报告并排对比 + PDF 导出；P2 收尾新闻/公告结构化 Provider

---

## 免责声明

本项目输出的所有内容仅为技术研究与学习参考，不构成任何投资建议。股市有风险，投资需谨慎。
