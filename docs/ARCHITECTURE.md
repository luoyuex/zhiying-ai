# 架构说明

## 分层

```
浏览器 (Vue 3 SPA)
    │  axios + httpOnly Cookie
    ▼
FastAPI (app/api → app/services)
    │                      │
    ▼                      ▼
PostgreSQL 16          Redis 7
用户 / 会话              验证码 / 限流计数
```

约束：**路由层只做参数校验与响应组装**，业务逻辑全部在 `services/`；数据访问通过 `db/models` 与 `db/session`，不在路由里写 SQL。

## 后端模块

| 模块 | 职责 |
| --- | --- |
| `core/config.py` | pydantic-settings 读取根目录 `.env`，单例 `settings` |
| `core/security.py` | Argon2id 密码、JWT 签发/校验、refresh token 生成与哈希、OTP HMAC |
| `core/errors.py` | `AppError` + 错误码常量，全局异常处理器统一输出 `{code, message, detail}` |
| `core/deps.py` | `get_db` / `get_current_user` / `require_admin` |
| `db/session.py` | async engine + sessionmaker；异常回滚，提交由 service 显式执行 |
| `db/models/` | `User`、`RefreshToken` |
| `services/otp_service.py` | 验证码生成、Redis 存储、三重限流、一次性校验 |
| `services/mail_service.py` | SMTP 发信（465 SSL / 587 STARTTLS），未配置时降级 console |
| `services/auth_service.py` | 注册、两种登录、刷新轮换、重放检测、登出、重置密码 |
| `api/v1/auth.py` | 8 个认证端点，负责 Cookie 写入/清除 |
| `providers/` | 腾讯/新浪/东财直连行情、统一模型、代码归一化、缓存/限流/熔断 |
| `services/market_service.py` | 行情编排：缓存未命中时走降级链，上游全挂返回 stale |
| `services/technical_analysis.py` | 技术面诊断：MA/MACD/RSI/BOLL/ATR/量比、评分、支撑压力、三档价位 |
| `providers/financial.py` | 东财 F10 财务指标/最近 6 期，缓存 12h |
| `providers/fundflow.py` | 东财近 30 日个股资金流，缓存 5min |
| `services/sentiment_service.py` | ARBR(26) + 换手/RSI/量比 + 主要指数涨跌 |
| `schemas/analysis.py` | 技术诊断响应模型；价位字段带 `computed_by="code"` |
| `schemas/company.py` | 财务/资金流/情绪数据模型 |
| `schemas/analyst.py` | 六分析师报告、最终决策（含代码价位） |
| `llm/client.py` | OpenAI 兼容 `AsyncOpenAI` 客户端、JSON 提取/修复、错误分类 |
| `llm/prompts.py` | 首席策略官提示词与 `PROMPT_VERSION`（内容 hash） |
| `services/analyst_service.py` | 六份分析师报告：由真实数据规则生成，标注数据缺口；元宝搜索结果供新闻/基本面/风险/情绪四位分析师提取线索与情绪计数 |
| `services/decision_service.py` | 首席策略官：1 次 LLM 决策 + 规则兜底 |
| `services/ai_analysis_service.py` | 分析编排：6h 缓存、每日额度、报告组装 |
| `services/ai_job_service.py` | AI 后台任务：Redis job 状态机、进程内 runner、活跃任务去重、stale 检测 |
| `services/web_search_service.py` | 元宝搜索（WSA SearchPro）：官方 TC3 签名 / Bearer 兼容、公开网页检索、去重、30min 缓存 |
| `services/report_history_service.py` | 报告落库、按用户/股票列表、详情 |
| `db/models/analysis_report.py` | `analysis_reports` 表（JSONB 报告） |
| `schemas/search.py` | 公开网页来源模型（title/url/date/site/summary） |
| `schemas/report.py` | 历史报告列表/详情模型 |
| `api/v1/ai.py` | AI 配置状态与 job 查询接口（不返回密钥） |
| `api/v1/stocks.py` | 个股报价、K 线、技术诊断、AI 分析任务接口（登录保护） |
| `api/v1/reports.py` | 历史报告列表/详情接口（用户隔离） |

## 认证时序

### 注册

```
POST /email/send-code  {email, purpose:register}
  → 限流检查（冷却 / 邮箱日限 / IP 时限）
  → 生成 6 位码，HMAC 后写 Redis（TTL 300s）
  → SMTP 发信
POST /register {email, code, password, nickname}
  → 邮箱是否已存在（存在则 409，先于验码，避免白白消耗验证码）
  → 校验验证码（错 5 次作废）
  → Argon2id 哈希密码 → 建用户 → 签发 access + refresh
  → Set-Cookie: zy_refresh（httpOnly, path=/api/v1/auth, 7d）
```

### 刷新与重放检测

```
POST /refresh（携带 Cookie）
  → sha256(token) 查库
  → 不存在 / 已过期 → 401
  → 已撤销 → 判定为重放 → 吊销该用户全部会话 → 401
  → 正常 → 建新 refresh，旧的置 revoked_at + replaced_by
  → 返回新 access + Set-Cookie 新 refresh
```

## 行情数据层

```
GET /api/v1/stocks/{symbol}/quote
  → MarketDataService（Redis 缓存）
      → SingleFlight（同 key 并发只发一次）
          → ProviderRegistry
              → 熔断检查 → 令牌桶 → 全局信号量(8) → 单源超时(6s)
                  → tencent → sina → eastmoney
```

- 报价降级链：腾讯 → 新浪 → 东财；K 线：东财 → 腾讯 → 新浪。
- 缓存：报价 fresh 3s / stale 60s；K 线 fresh 5min / stale 30min。stale 命中时 `delayed=true`。
- 限流：Redis 令牌桶，腾讯 5rps、新浪 3rps、东财 5rps；Redis 故障时放行。
- 熔断：按 `provider+capability` 统计，60s 内 5 次失败打开 60s。
- Provider 只返回 Pydantic 模型，不做文本格式化；所有价格/量/额统一为元、股、元。

## 前端模块

| 模块 | 职责 |
| --- | --- |
| `api/client.ts` | axios 实例；请求注入 Bearer；401 触发单飞 refresh 后重放原请求 |
| `stores/auth.ts` | 用户与登录态；启动时用 Cookie 恢复会话 |
| `router/index.ts` | 路由守卫：受保护页未登录跳登录，已登录访问登录页跳工作台 |
| `styles/tokens.css` | 设计 token（Tailwind 4 `@theme`），所有颜色/圆角/阴影集中定义 |
| `api/market.ts` | 行情类型与 quote / kline 请求封装 |
| `api/ai.ts` | AI 配置、job 提交/轮询与多分析师报告类型 |
| `api/reports.ts` | 历史报告列表/详情请求 |
| `components/ui/` | Button / Input / Field / OtpInput |
| `components/layout/` | AuthLayout（品牌区 + 表单区）、AppShell（顶栏 + 用户菜单「工作台 / 历史报告 / 退出登录」+ 内容区） |
| `components/market/` | StockLookup（代码查询入口，直达详情）、MiniKline（SVG K 线 + 成交量，支持大尺寸） |
| `components/report/PublicInfoPanel.vue` | 「公开信息 · 元宝搜索」面板：有来源列出来源，无来源展示未收录说明；报告页（card）与 AI 卡（flat）复用 |
| `pages/StockDetailPage.vue` | `/stock/:symbol` 个股页：报价、指标、日/周/月 K、复权切换、代码切换、AI 分析入口与该股历史入口 |
| `pages/ReportsPage.vue` | `/reports` 全部历史报告：按日期分组、代码/名称筛选、空态/错误重试、跳转报告详情 |
| `pages/ReportDetailPage.vue` | `/reports/:id` 完整报告页：六分析师全部依据/风险/来源/缺口、首席决策、价位、元宝来源、返回全部历史入口 |
| `utils/market.ts` | 行情格式化：价格/量额/百分比/来源/时间/涨跌色 |

## 行情页面

```
DashboardPage（不请求行情）
  → 用户输入代码 / 点快捷标的
      → router.push('/stock/:symbol')
  → 工作台只保留统计、路线与进度

StockDetailPage（统一加载一次）
  → GET quote + GET kline + GET analysis + GET /ai/config
  → 技术面诊断（规则引擎）
  → AI 综合研判（手动触发，后台 job + 轮询）
  → 页面标注 source / fetched_at / delayed；红涨绿跌
```

当前 K 线为无依赖 SVG 实现；klinecharts、MA/MACD/BOLL 与资金流/新闻仍待 P3 补齐。

## 技术面诊断

```
GET /api/v1/stocks/{symbol}/analysis
  → 复用 MarketDataService 的 quote + 90 根日 K（前复权）
  → technical_analysis.analyze_technicals()
      ├─ 指标：MA5/10/20/60、MACD、RSI14、BOLL(20,2)、ATR14、5/20 日均量比
      ├─ 评分：均线/价格位置/MACD/RSI/量能/布林加权，0–100 → 强势…弱势
      ├─ 信号：逐项给出 bullish / bearish / neutral 与中文解释
      ├─ 支撑压力：近期高低点、MA20/60、布林上下轨中取最近有效位
      └─ 三档价位：entry=现价×0.98，止盈=现价×1.08，
                   止损=min(-5%, 2.5×ATR) 并钳制在 -5%~-8%，computed_by="code"
```

本版为六分析师中的**技术面分析师规则版**，不调用 LLM、不消耗 Key；LLM 版与其余五位分析师在 P4 接入。

## LLM 综合研判

```
GET /ai/config
  → configured / model / prompt_version / daily_quota / quota_used（不返回密钥）

POST /stocks/{symbol}/ai-analysis
  → 校验代码 / 模型配置 / 活跃任务
  → 202 返回 job_id（不在 HTTP 请求里等 LLM）
  → 后台 runner：
      准备行情数据（quote + 90 根日 K + 技术诊断）
      → 先查 6h AI 报告缓存
          ├─ 命中 → 直接成功，不搜索、不调 LLM、不落新历史
          └─ 未命中 → 并行获取财务/季报、资金流、情绪 +（若配置 WSA）1 次元宝搜索
              → 代码生成六份分析师报告（每份带 data_sources / missing）
              → 首席策略官：1 次 LLM 决策；失败用规则兜底
              → 组装报告、写 6h 缓存、额度 +1、落库 analysis_reports
      → 更新 job 状态与阶段

GET /ai/jobs/{job_id}
  → queued / running / succeeded / failed；phase、elapsed_seconds、result、error_code/message

GET /analysis/reports?symbol=...
GET /analysis/reports/{id}
  → 当前用户的报告列表与完整报告详情（六分析师 + 决策 + 价位）
```

- 元宝搜索只提供公开网页信息；prompt 要求核对日期、只作事件背景，不能当财务事实。
- 一次个股分析最多 1 次元宝搜索；AI 报告缓存命中时连搜索也跳过；搜索失败/未配置不阻塞分析。
- 响应带 `web_search_used` 与 `web_sources`，前端展示来源链接；数据覆盖/缺口来自六份分析师的 `missing`。
- 六份分析师报告当前由代码基于真实数据生成，首席策略官用 1 次 LLM；参考项目的 6 次 LLM 分析师可在后续逐位替换。
- 报告落库到 `analysis_reports`（JSONB），Redis 6h 缓存命中不重复落库；历史详情页按用户隔离。

- 前端每 2s 轮询 job；页面切走只停止本地轮询，后台任务继续；重进后再次提交会复用 active job。
- 单次 LLM 调用 180s、整个 job 420s；SDK 关闭自动重试，避免慢模型等待翻倍。
- 当前 runner 是进程内 `asyncio.Task`；服务重启会中断任务，GET 时按 stale 规则标记失败；后续迁移 ARQ + SSE。
- 提示词版本 = 提示词内容 hash，改提示词自动换缓存。
- LLM 输出不允许生成价位，三档价位始终由技术诊断的代码计算。
- 错误码：未配置 `LLM_NOT_CONFIGURED`(503)、额度 `ANALYSIS_QUOTA_EXCEEDED`(429)、限流 `LLM_BUSY`(503)、格式/调用失败 `LLM_INVALID_RESPONSE` / `LLM_ERROR`(502)、任务中断 `AI_JOB_STALE`。
- v1 是单次「技术面 + 风险」综合研判；六分析师并行、讨论、决策与 SSE 在 P4 后续。参考项目 `aiagents-stock` 是 6 个分析师 + 讨论 + 决策的顺序调用，在 Streamlit 里可跑数分钟并显示进度；本项目的异步 job 先解决 HTTP 超时，再逐步扩展到多分析师。

## 设计 token 约定

- 背景 `#FFFFFF` / 表面 `#F7F8FA`，边框 `#E6E8EB`
- 文字三级 `#16181D` / `#5A6069` / `#8A9099`
- 主色 `#2F5AF3`，柔和底 `#EDF1FE`
- 涨 `#E0424A`（红）、跌 `#1BA672`（绿），符合 A 股习惯
- 圆角 6 / 10 / 14；阴影极轻，靠 1px 边框分层
- 数字统一 `tabular-nums`，金额与百分比右对齐
- 表单控件统一 40px 高（`h-10`）；单行输入行高同为 40px（`leading-10`），保证文字垂直居中
- 验证码为单容器 6 等分格，获取验证码按钮与输入同排、同高；移动端上下堆叠

## 环境变量

见根目录 `.env.example`。三个必须注意的点：

1. `JWT_SECRET` / `OTP_SECRET` 生产环境必须换成长随机串。
2. `COOKIE_SECURE=true` 仅在 HTTPS 下开启，本地 http 必须为 false。
3. `EMAIL_MODE=console` 时验证码只进日志；切 `smtp` 需要填 `SMTP_USER` 与授权码。
4. 行情源参数见 `.env.example` 的 `MARKET_*`；公网出口被封时用 `EGRESS_PROXY_URL` 指定代理。
5. LLM 使用 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`；未配置时 AI 接口返回 `LLM_NOT_CONFIGURED`，详情页展示引导。`LLM_TIMEOUT_SECONDS` 为单次调用超时（默认 180s），`LLM_JOB_TIMEOUT_SECONDS` 为整个后台任务超时（默认 420s）。密钥目前只放环境变量，P4 再做 AES-GCM 加密存储。
6. 元宝搜索有两条接入路径，按凭据自动选择：
   - 官方腾讯云 API 3.0（优先）：`WSA_SECRET_ID` + `WSA_SECRET_KEY`（临时密钥再加 `WSA_SECRET_TOKEN`），请求 `https://{WSA_SEARCH_HOST}/`，`X-TC-Action: SearchPro`、`X-TC-Version: 2025-05-08`，TC3-HMAC-SHA256 签名；`Mode=0`、`Industry=finance`、`Cnt`、可选 `Freshness`。不是 You.com 的 YDC。
   - 兼容 Bearer 模式：只填 `WSA_API_KEY` 时请求 `WSA_SEARCH_URL`，带 `Authorization: Bearer`，不追加 `Freshness`。服务 API KEY 形如 `sk-…`；若填成 `AKID…`（SecretId），客户端会在发请求前拦截并提示。
   - 两套凭据同时填时优先官方模式；`WSA_SEARCH_CACHE_SECONDS` 默认 1800；未配置时自动跳过。
