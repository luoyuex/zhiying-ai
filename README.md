# 智盈 AI（zhiying-ai）

A 股 AI 分析工作台。前端 Vue 3 + TypeScript，后端 FastAPI + PostgreSQL + Redis。

当前进度：用户侧核心功能已上线（邮箱认证、个股 AI 分析、自选/组合诊断、五策略选股、定时任务、评级变化与价位提醒、历史报告/对比/PDF）；**后台管理 P0–P2 已上线**（运营总览、用户与额度、审计、LLM 调用与任务台账、成本日报、任务中心、定时执行记录、跨用户内容库），P3–P4 见 [开发计划](docs/DEVELOPMENT_PLAN.md)。

**当前可用功能**

- 邮箱验证码注册、密码/验证码登录、重置密码
- **管理后台** `/app/admin`（仅管理员）：运营总览、用户搜索/额度/封禁/强制下线、操作审计；成本日报（按日聚合 token/估算成本）、任务中心（筛选/详情/失败重跑）、定时执行记录（含跳过原因）、跨用户内容库（报告/选股/组合诊断/自选只读）
- 工作台「个股查询」：输入 6 位代码或点快捷标的，**直接进入个股详情页**；工作台不再预加载行情，避免重复查询
- 个股详情页 `/stock/:symbol`：统一加载报价、12 项指标、日/周/月 K、前复权/后复权/不复权；支持页面内切换代码
- **技术面诊断**：基于 90 根日 K 前复权计算评分/评级、趋势、MA/MACD/RSI/BOLL/ATR/量比信号、支撑压力，以及由代码计算的三档价位
- **六维数据**：行情/技术、财务指标（东财 F10，最近 6 期）、资金流（东财近 30 日）、市场情绪（ARBR/换手/RSI/指数）、公开网页（元宝搜索）
- **六分析师 + 首席决策**：技术面/基本面/资金面/风险/情绪/新闻六份结构化报告由代码基于真实数据生成；首席策略官 LLM 做最终决策（买入/持有/卖出 + 操作建议/持有周期/仓位/风险），失败自动规则兜底；三档价位始终由代码计算
- **历史报告**：每次生成落库 PostgreSQL；顶栏头像菜单 →「历史报告」可查看当前用户全部记录（按日期分组、代码/名称筛选），也可在个股页查看该股最近 6 份；报告页完整展示六分析师全部依据/风险/数据源与首席决策
- **定时任务**：个人中心可开启每日定时选股与自选股分析，自定义执行时间与各策略参数；可填写邮件接收地址，任务跑完后把当天结果汇总成一封邮件（同一天同一任务线仅一封）
- **评级变化与调仓记录**：新报告自动与同股上一份对比，报告详情/个股页/自选卡/历史列表显示「评级上调/下调」；自选股成本或数量变化会记录调仓历史，可按需查看
- **关键价位提醒**：报告详情可一键设置入场/止盈/止损提醒，自选卡也可设置「涨到 / 跌破」目标价；交易日 09:30–15:00 每 5 分钟检查一次，触发后记录触发价并发送通知（不消耗 AI 额度，触发一次后自动结束）。自选页「价位提醒」面板汇总所有生效中与近期触发的提醒，不要求股票在自选列表
- **统一通知设置**：个人中心「定时与通知」统一管理定时任务汇总与价位提醒的邮件、Webhook 渠道；支持钉钉/飞书机器人，两个事件各有独立开关，邮件接收地址共用
- **导出**：单股报告、选股结果、组合诊断支持 PDF；选股结果与组合诊断支持 CSV（Excel 友好）
- **头像**：个人中心资料设置支持上传/更换/移除头像，顶栏与用户菜单同步展示
- **元宝搜索（可选）**：一次 AI 分析最多 1 次公开网页检索，缓存 30 分钟；命中 6h 报告缓存时连搜索也跳过
- 接口：`/api/v1/stocks/{symbol}/quote`、`/kline`、`/analysis`、`/ai-analysis`、`/api/v1/ai/jobs/{id}`、`/api/v1/analysis/reports`

> 📋 完整的开发计划、已完成/未完成清单与风险登记见 **[docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md)**。
>
> 生产部署（Nginx 同域反代 + HTTPS + systemd + Docker）见 **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**；想一条命令拉起全栈，见 **[docs/DOCKER.md](docs/DOCKER.md)**。
>
> 每个版本需要执行的更新步骤与新增配置见 **[docs/RELEASE_NOTES.md](docs/RELEASE_NOTES.md)**。

---

## 快速开始

### 服务器部署（Docker 全栈）

克隆后三步拉起官网、工作台、API、worker、PostgreSQL 与 Redis：

```bash
git clone https://github.com/luoyuex/zhiying-ai.git
cd zhiying-ai

./scripts/docker-init.sh        # 复制 .env 并生成随机密钥
vi .env                         # 至少填 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL

docker compose up -d --build    # 首次会自动跑数据库迁移
```

打开 `http://服务器IP:8088/`（官网）或 `/app/`（工作台）。首次启动后同步一次股票列表：

```bash
docker compose exec api .venv/bin/python -m app.scripts.seed_stocks
```

端口、HTTPS、备份、更新与排障见 **[docs/DOCKER.md](docs/DOCKER.md)**。

### 本地开发

#### 0. 环境要求

| 依赖 | 版本 | 说明 |
| --- | --- | --- |
| Docker | 24+ | 一键部署全栈，或本地只跑 PostgreSQL 16 与 Redis 7 |
| Python | 3.12+ | 用 uv 管理虚拟环境 |
| uv | 0.5+ | `pip install uv` 或官方脚本安装 |
| Node.js | 24+ | 前端构建（`html2canvas-pro` 要求 Node 24+） |

#### 1. 准备配置

```bash
cp .env.example .env
```

本地开发可以直接用模板里的占位密钥；部署到服务器前必须换成随机值（`./scripts/docker-init.sh` 会自动生成）。

#### 2. 启动数据库与缓存

```bash
npm run up          # 等价于 docker compose up -d postgres redis
```

> 只起依赖，不启动 API / worker / web；全栈部署用 `docker compose up -d --build`。

#### 3. 启动后端

```bash
cd backend
uv sync             # 首次安装依赖
uv run alembic upgrade head   # 建表
uv run uvicorn app.main:app --reload --reload-dir app --port 8010
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

#### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

打开 <http://localhost:5288> 是产品官网；进入工作台用 <http://localhost:5288/app/>，登录页为 `/app/login`。Vite 已把 `/api` 代理到 `127.0.0.1:8010`。

根目录也可以用 `npm run api` / `npm run web` 启动（等价命令）。

#### 端口约定

| 服务 | 端口 | 说明 |
| --- | --- | --- |
| Web（Docker 全栈） | **8088** | `WEB_PORT` 可改；Nginx 静态站点 + `/api` 反代 |
| 前端（Vite） | **5288** | 固定端口，`strictPort: true`，被占用会直接报错而不是自动换端口 |
| 后端（FastAPI） | **8010** | 只用 127.0.0.1，不对外暴露 |
| PostgreSQL | 5432 | Docker，只绑 127.0.0.1 |
| Redis | 6379 | Docker，只绑 127.0.0.1 |

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
LLM_MAX_TOKENS=8192
# 推理力度：default/none/low/medium/high；default 不传参，SenseNova 自动按 none
LLM_REASONING_EFFORT=default
LLM_FINAL_REASONING_EFFORT=default
LLM_ANALYST_MAX_TOKENS=8000
LLM_FINAL_MAX_TOKENS=16000
# 可选：当前模型每百万 token 单价（人民币）；两项都填才启用成本估算
LLM_PRICE_INPUT_PER_M=
LLM_PRICE_OUTPUT_PER_M=
LLM_TEMPERATURE=0.3
LLM_CACHE_SECONDS=21600
```

> `LLM_TIMEOUT_SECONDS` 是单次调用超时；`LLM_ANALYST_TIMEOUT_SECONDS` 是每位分析师的超时；`LLM_JOB_TIMEOUT_SECONDS` 是整个后台任务超时。六位分析师按 `LLM_ANALYST_CONCURRENCY` 并发，免费/低配模型建议保持 3。
>
> 推理型模型（如 `sensenova-6.8-flash-lite`）的思考过程也计入 completion token。若日志出现 `finish_reason=length` / `LLM 思考过程耗尽 token`：`LLM_REASONING_EFFORT=default` 时代码会对 SenseNova 自动使用 `none`；其他推理模型可显式设 `none`/`low`。`max_tokens` 不能真正“无限”，上限由模型最大输出与上下文决定；`LLM_ANALYST_MAX_TOKENS` / `LLM_FINAL_MAX_TOKENS` 是选股专用上限。
>
> 后台的估算成本依赖模型单价：`LLM_PRICE_INPUT_PER_M` / `LLM_PRICE_OUTPUT_PER_M` 按“人民币 / 百万 token”填写，两项都填才启用；未配置时成本显示为“—”，不按 0 计算。内置表只包含少量 DeepSeek 模型，SenseNova 等自定义模型请用这两个键配置。
>
> 开发期不想被额度挡住：在 `.env` 设 `AI_DAILY_QUOTA_OVERRIDE=9999`，所有用户统一按该额度计算；设为 `0` 则恢复使用用户表的 `daily_analysis_quota`。改完需重启后端。

改完重启后端。未配置时详情页会显示引导，不会发起 LLM 请求；配置后：
- `GET /api/v1/ai/config` 返回 `configured=true` 与当前模型
- 详情页「开始 AI 分析」提交后台任务；进度优先走 SSE `GET /api/v1/ai/jobs/{job_id}/events`（snapshot / phase / done），连接失败自动回退轮询 `GET /api/v1/ai/jobs/{job_id}`
- 每次成功生成消耗 1 次 `daily_analysis_quota`；同股同交易日 + 同模型 + 同提示词版本 6 小时内直接复用，不重复消耗
- 任务在后台执行，页面切走不会中断；重新点击会复用仍在运行的任务

> 分析流程：六位分析师并发 → 团队讨论（LLM 整理 4-6 轮交叉回应）→ 首席策略官决策。任一步失败会自动回退到规则版，并在报告中标记 `engine=rule` / `source=rule`。整份报告仍只消耗 1 次额度。
>
> 任务执行：默认 `AI_JOB_EXECUTION=arq`，由 `npm run worker` 消费；API 重启不会中断分析，但 worker 重启会取消进行中的任务（当前未配置 `job_completion_wait`），请在低峰发布。worker 每 30 秒写入心跳 `ai:worker:alive`（TTL 120 秒），没有心跳时新任务直接返回 503。单个 worker 同时执行 `AI_WORKER_MAX_JOBS`（默认 4）个任务，实际模型并发约为它 × `LLM_ANALYST_CONCURRENCY`；队列积压时可调大，出现 `LLM_BUSY` 限流则回调。

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
# 在项目根目录执行
cd backend
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
│  ├─ index.html              产品官网（静态内容，面向 SEO/GEO）
│  ├─ app.html                Vue 工作台入口
│  ├─ public/                 favicon / robots.txt / llms.txt / OG 分享图
│  └─ src/
│     ├─ marketing/           官网交互（菜单、滚动揭示、分析师轮播）
│     ├─ api/                 axios 客户端（401 单飞续期）+ 认证 / 行情接口
│     ├─ stores/auth.ts       Pinia 会话
│     ├─ router/              路由与守卫（base: /app/）
│     ├─ components/          UI 基础组件 + 布局 + market（行情速查 / 迷你 K 线）
│     ├─ pages/               登录 / 注册 / 重置密码 / 工作台 / 个股详情 / 历史报告 / 分析报告
│     └─ styles/              设计 token（应用）+ marketing.css（官网）
├─ docker-compose.yml         全栈编排；也可只起 postgres / redis 供本地开发
├─ docs/ARCHITECTURE.md       架构说明
└─ .env.example               配置模板
```

---

## 官网与 SEO / GEO

- `/` 是独立静态官网，正文不依赖 JavaScript 渲染；工作台在 `/app/`，`app.html` 带 `noindex`，不会被搜索引擎收录。
- 已内置：语义化 HTML、title/meta description、canonical、Open Graph / Twitter Card、Organization / WebSite / WebPage / SoftwareApplication / FAQPage 结构化数据、`robots.txt`、`llms.txt`（面向 AI 检索的站点摘要）。
- 官网的交互逻辑在 `frontend/src/marketing/`，样式在 `frontend/src/styles/marketing.css`。
- **上线前**：把 `frontend/index.html` 里的 canonical、`og:image`、`twitter:image` 改成正式域名的绝对地址（当前为相对路径），并基于正式域名补一份 `sitemap.xml`，把首页地址写进去。`robots.txt` 已允许搜索引擎与 AI 爬虫抓取官网，并禁止抓取 `/app/` 与 `/api/`。

### 生产部署（Nginx）

> 已有 Docker 环境时优先用 **[docs/DOCKER.md](docs/DOCKER.md)**；下面是裸机 Nginx + systemd 方式。

可直接参考 **`deploy/nginx.conf.example`**，要点只有三条：

1. `root` 指向 `frontend/dist`，`index index.html` —— **`/` 必须落到官网 `index.html`**。不要把全局 fallback 指到 `app.html`，否则官网会被工作台顶掉（表现就是打开首页被要求登录）。
2. `/app` 301 到 `/app/`；`location /app/` 用 `try_files $uri /app.html;` 回退到工作台入口，否则刷新 `/app/stock/600519` 这类深链会 404。
3. `/api/` 反代 FastAPI(8010)，并 `proxy_buffering off`（SSE 分析进度需要）。

部署 checklist：

- [ ] 服务器上的是**最新** `dist`（`npm run build` 后整体上传 `frontend/dist`）；如果 `/` 打开还是工作台，先怀疑传的是旧构建
- [ ] 浏览器/CDN 缓存已清（HTML 建议配 `Cache-Control: no-cache`，见示例配置）
- [ ] `curl -I https://你的域名/` 返回 200 且 title 是官网；`curl -I https://你的域名/app/` 返回 200 且是 `app.html`
- [ ] 未登录访问 `/app/` 会被前端带回官网首页；`/app/stock/600519` 这类深链未登录时进登录页并带 `redirect` 参数

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
| PATCH | `/me` | 修改昵称 |
| POST | `/me/avatar` | 上传/替换头像（data URL） |
| DELETE | `/me/avatar` | 移除头像 |
| GET | `/avatar/{user_id}` | 读取用户头像（公开，带版本号） |

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

后台管理（前缀 `/api/v1/admin`，仅 `role=admin`）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/overview?range=today\|7d` | 运营总览：用户、任务、成本、Worker/队列/熔断/代理 |
| GET | `/users` | 用户列表，支持搜索/状态/角色/额度/分页 |
| GET/PATCH | `/users/{id}` | 用户详情；调整每日额度或状态（写操作审计） |
| POST | `/users/{id}/reset-quota` | 重置今日已用额度 |
| POST | `/users/{id}/revoke-sessions` | 强制下线 |
| GET | `/users/{id}/sessions` | 登录会话 |
| GET | `/audit-logs` | 管理员操作审计 |
| GET | `/costs/summary?days=14` | 成本日报：按日聚合调用数/token/估算成本、Top 用户与任务 |
| GET | `/costs/calls` | LLM 调用明细（邮箱/任务/状态筛选） |
| GET | `/jobs`、`/jobs/{id}` | AI 任务列表与详情 |
| POST | `/jobs/{id}/retry` | 重跑失败任务（以用户身份、消耗额度、写审计） |
| GET | `/automation-runs` | 定时任务执行记录（含跳过原因） |
| GET | `/reports`、`/reports/{id}` | 跨用户报告库与只读详情 |
| GET | `/screener-records`、`/{id}` | 跨用户选股记录与只读详情 |
| GET | `/portfolio-diagnoses`、`/{id}` | 跨用户组合诊断与只读详情 |
| GET | `/watchlist-items` | 跨用户自选股列表 |

管理员初始化（在 `backend` 目录）：

```bash
uv run python -m app.scripts.create_admin --email you@example.com --promote
# 取消管理员（不能移除最后一个 active 管理员）
uv run python -m app.scripts.create_admin --email you@example.com --demote
```

数据约定：价格=元、成交量=股、成交额=元；返回 `source` / `fetched_at` / `delayed`。缓存过期但上游全挂时返回 stale 数据并置 `delayed=true`。

---

## 测试

```bash
cd backend
uv run pytest -q
```

测试会真实写入 PostgreSQL 与 Redis（使用 `test-xxxx@example.com` 临时账号，结束后自动清理），运行前请先 `npm run up` 并执行迁移。

当前覆盖 250 个用例（249 通过 + 1 跳过，截至 2026-10-25）：认证链路、行情 Provider/缓存/API、技术诊断、LLM/六分析师/异步任务、元宝搜索（官方 TC3 + Bearer）、历史报告、自选增强（评级变化/调仓记录/价位提醒/报告价位联动）、Webhook 通知、头像、导出、后台权限/分页/写操作审计/成本聚合/任务重跑/定时执行记录/跨用户内容库。

---

## 下一步

1. 后台 P3：数据源/代理/熔断/缓存、配置快照、日志查看
2. 后台 P4：公告/反馈
3. 生产部署（Nginx/HTTPS/备份/限流压测）

---

## 免责声明

本项目输出的所有内容仅为技术研究与学习参考，不构成任何投资建议。股市有风险，投资需谨慎。
