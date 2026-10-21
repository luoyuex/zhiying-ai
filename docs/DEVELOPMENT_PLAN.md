# 智赢 AI 开发计划与进度总览

> 本文档是项目的唯一进度真相源。每完成一个阶段，更新「状态」列与「已完成清单」，避免范围漂移与重复劳动。
> 最后更新：2026-10-21（工作台首页改版：真实额度/最近分析 + 报告列表组件抽离）

---

## 一、项目定位

**智赢 AI —— A 股 AI 分析工作台**：输入一只股票，六个分析师（技术面/基本面/资金面/风险管理/市场情绪/新闻舆情）并行出报告，再由首席策略官汇总成「评级 + 三档价位 + 置信度 + 风险提示」的可执行结论。

参考项目 `D:\code\AI\aiagents-stock`（Streamlit 单体）：只借鉴其**业务逻辑**（Agent prompt、打分规则、数据接口经验），UI 与工程架构全部重写。

**产品原则（写代码前先看这里）：**
1. 好看：浅色清爽数据风，设计 token 统一管理，不做后台模板感。
2. 可信：每个数字带来源与时间戳，AI 结论标注模型与 prompt 版本，价位由代码计算。
3. 可公网：免费数据源必须配缓存/限流/熔断，用户有配额，密钥加密存储。
4. 合规：所有输出仅为研究参考，页面固定免责声明，不接交易、不做收益承诺。

---

## 二、技术选型（已定，不反复）

| 层 | 选型 | 备注 |
| --- | --- | --- |
| 后端 | FastAPI + Uvicorn + Python 3.13 | uv 管依赖 |
| ORM / 迁移 | SQLAlchemy 2.x async + asyncpg + Alembic | 提交由 service 显式执行 |
| 数据库 | PostgreSQL 16（Docker） | 后续分析结果用 JSONB |
| 缓存 / 限流 / 队列 | Redis 7（Docker） | OTP、令牌桶、Pub/Sub、ARQ |
| 任务执行 | ARQ（第三期引入） | asyncio 原生 worker |
| 鉴权 | Argon2id + JWT(15min) + refresh Cookie(7d) 轮换 | 已实现 |
| LLM | AsyncOpenAI 兼容协议，默认 DeepSeek | 密钥 AES-GCM 加密存储 |
| 前端 | Vue 3.5 + TypeScript + Vite 6 + npm | |
| UI | Tailwind CSS 4 + 手写基础组件 | 未用 Element Plus / shadcn-vue |
| 状态 / 请求 | Pinia + axios（401 单飞续期） | |
| 图表 | klinecharts（K 线）+ ECharts 5（雷达等） | 第三期引入 |
| 实时进度 | SSE | 第四期引入 |

**端口约定（不可再改，改要同步 4 处）：** 前端 5288（strictPort）、后端 8010、PG 5432、Redis 6379。**8000 端口被用户其他项目占用，禁止使用。**

---

## 三、阶段总览与状态

| 阶段 | 内容 | 状态 | 完成时间 |
| --- | --- | --- | --- |
| P1 | 项目骨架 + 邮箱验证码认证 | ✅ 完成 | 2026-10-21 |
| P2 | 行情数据层（Provider + 缓存/限流/熔断） | 🚧 进行中 | 报价/K线/财务/资金流/情绪已通 |
| P3 | 个股页（报价/K线/指标） | 🚧 进行中 | 详情页 v1 已上线 |
| P4 | Agent 编排 + 分析任务 + SSE 流式 | 🚧 进行中 | 六分析师 + 首席决策已上线 |
| P5 | 分析报告页 + 评分卡 | 🚧 进行中 | 历史报告已落库 |
| P6 | 自选股 + 分析历史对比 | 🚧 进行中 | 历史已落库，对比/自选待做 |
| P7 | 管理后台 + 生产部署（Nginx/HTTPS） | ⬜ 未开始 | — |
| P8（远期） | 选股策略模块族（龙虎榜/主力/低估值…） | ⬜ 规划中 | — |

---

## 四、已完成清单（P1，截至 2026-10-21）

### 4.1 工程骨架
- ✅ monorepo：`backend/` + `frontend/` + `docs/` + 根 `package.json`（跨平台脚本）+ `Makefile`
- ✅ `docker-compose.yml`：PostgreSQL 16 + Redis 7，带 healthcheck 与持久卷
- ✅ `.env` / `.env.example` 全套配置项，`.gitignore` 排除密钥与产物
- ✅ git 仓库未初始化（**待办**，见 6.1）

### 4.2 后端
| 模块 | 内容 | 状态 |
| --- | --- | --- |
| `app/main.py` | FastAPI 装配、CORS、三类异常处理器、`/health`（db+redis） | ✅ |
| `core/config.py` | pydantic-settings 读根目录 `.env`，`get_settings()` 单例 | ✅ |
| `core/security.py` | Argon2id、JWT 签发/校验、refresh 生成与哈希、OTP HMAC | ✅ |
| `core/errors.py` | `AppError` + 错误码常量 + 工厂函数 | ✅ |
| `core/deps.py` | `get_db` / `get_current_user` / `require_admin` | ✅ |
| `db/session.py` | async engine + sessionmaker，异常回滚 | ✅ |
| `db/models/` | `User`、`RefreshToken` | ✅ |
| `db/redis.py` | 惰性 Redis 客户端 | ✅ |
| `services/otp_service.py` | 验证码生成/存储/校验/三重限流 | ✅ |
| `services/mail_service.py` | SMTP（465 SSL / 587 STARTTLS）+ console 兜底 + HTML 模板 | ✅ |
| `services/auth_service.py` | 注册/两种登录/刷新轮换/重放检测/登出/重置密码 | ✅ |
| `api/v1/auth.py` | 8 个端点 + Cookie 管理 | ✅ |
| `alembic/` | 异步 env + 初始迁移 `0001_init_auth` | ✅ |
| `tests/test_auth_flow.py` | 11 个端到端用例（真实 PG+Redis） | ✅ 全绿 |

### 4.3 认证行为规范（已实现并测试）
- 验证码：6 位数字，`secrets` 生成，HMAC-SHA256 存 Redis，TTL 300s，一次性；错 5 次立即作废。
- 限流：同邮箱 60s 冷却、单邮箱每日 10 次、单 IP 每小时 20 次（Redis 原子计数）。
- access token：JWT HS256，15 分钟，仅存前端内存（不进 localStorage）。
- refresh token：随机 32 字节，httpOnly Cookie（path=`/api/v1/auth`），7 天，每次刷新轮换；**重放即吊销该用户全部会话**。
- 密码：Argon2id；≥8 位且含字母数字；登录失败统一文案防枚举；哈希参数升级自动 rehash。
- 登录耗时均衡：账号不存在时也执行 dummy verify。

### 4.4 前端
- ✅ 设计 token（`styles/tokens.css`，Tailwind 4 `@theme`）：背景/边框/文字三级/主色/涨跌色/圆角/阴影/字体
- ✅ UI 组件：`Button` `Input` `Field` `OtpInput`
- ✅ `OtpInput`：单容器 6 等分格 + 细分隔线；聚焦整组描边、当前格浅蓝底；保留自动跳格/整段粘贴/退格回退
- ✅ 布局：`AuthLayout`（左品牌区 + 右表单）、`AppShell`（顶栏 + 内容）
- ✅ 页面：登录（密码/验证码双 Tab）、注册（验证码 + 密码强度条）、忘记密码（成功态）、工作台（行情速查 + 进度看板）
- ✅ `api/client.ts`：Bearer 注入 + 401 单飞 refresh + 原请求重放
- ✅ `stores/auth.ts`：启动时用 Cookie 恢复会话
- ✅ 路由守卫：受保护页/仅游客页双向拦截，登录后回跳 `redirect`
- ✅ 响应式：移动端 390px 无横向溢出（Playwright 实测 scrollWidth == clientWidth）

### 4.5 验收记录
- 后端 `pytest -q`：**11 passed**（注册、重复邮箱、错 5 次作废、60s 冷却、过期、密码错误、验证码登录、刷新轮换+重放拒绝、登出、重置密码、密码强度校验）
- 真实 HTTP 冒烟：send-code → 读日志验证码 → register → Set-Cookie → refresh 轮换 → me → 旧 cookie 重放 401
- 前端 `npm run build`（vue-tsc + vite）：通过
- `/health`：db ok / redis ok

### 4.6 P2 第一刀（2026-10-21，报价 + K 线）

| 模块 | 内容 | 状态 |
| --- | --- | --- |
| `providers/models.py` | `Quote` / `KlineBar` / `KlineSeries`；价格=元、量=股、额=元、Asia/Shanghai、`_pct` 命名、`source`/`fetched_at`/`delayed` | ✅ |
| `providers/symbols.py` | 六位代码归一化：`600519` / `sh600519` / `600519.SH`；派生 `prefixed`、`secid`、`ts_code`；拒绝非 A 股代码与市场后缀不匹配 | ✅ |
| `providers/tencent.py` | 报价 + 日/周/月 K 线；GBK 解码；字段单位换算（手→股、亿→元） | ✅ |
| `providers/sina.py` | 报价 + 日/分钟 K 线；必须带 Referer；GBK 解码 | ✅ |
| `providers/eastmoney.py` | 报价 + 1/5/15/30/60 分钟/日/周/月 K 线；按 `f59` 小数位缩放；日期窗口取数后截取尾部 | ✅ |
| `providers/resilience.py` | Redis 缓存（fresh/stale 两级 TTL）、Redis 令牌桶（腾讯 5rps/新浪 3rps/东财 5rps）、按 provider+capability 熔断（60s 内 5 次失败→open 60s）、进程内 singleflight | ✅ |
| `providers/registry.py` | 降级链：报价 `tencent→sina→eastmoney`；K 线 `eastmoney→tencent→sina`；单源超时 6s、全局并发 8 | ✅ |
| `services/market_service.py` | 缓存编排、stale 兜底（`delayed=true`）、同 key 请求合并 | ✅ |
| `api/v1/stocks.py` | `GET /stocks/{symbol}/quote`、`GET /stocks/{symbol}/kline`（登录保护）；错误码 `INVALID_SYMBOL` / `STOCK_NOT_FOUND` / `MARKET_UNAVAILABLE` | ✅ |
| 测试 | 新增 31 个用例：三家真实报文解析、缓存命中、singleflight 10 并发合并为 1 次、熔断跳过、stale 返回、接口错误映射 | ✅ |
| 配置 | `.env.example` 新增 `EGRESS_PROXY_URL` 与 `MARKET_*` 抗压参数 | ✅ |

**P2 验收记录**
- 后端全量 `pytest -q`：**42 passed**（原 11 个认证用例 + 新增 31 个行情用例）
- 真实 HTTP 冒烟（临时 8011 端口）：注册 → quote `source=tencent` → kline `source=eastmoney`；Redis 写入 `mkt:cache:quote:*` 与 `mkt:cache:kline:*`
- 错误映射实测：非法代码 422 `INVALID_SYMBOL`；未登录 401 `UNAUTHORIZED`
- 三家报价交叉核对：600519 价格/成交量/成交额一致（量 1,064,100 股，额 1,405,822,456 元）

**尚未覆盖（P2 剩余）**：财务/资金流/新闻三类 Provider、AKShare 线程池接入、股票搜索接口与 `stocks` 表。

### 4.7 认证页 UI 收尾（2026-10-21）

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 验证码控件 | 6 个独立方框改为单容器 6 等分格 + 细分隔线；聚焦时整组蓝边，当前格浅蓝底；高度 40px | ✅ |
| 发送按钮布局 | 注册页、找回密码页的「获取验证码」从邮箱行移到验证码行；与验证码登录 Tab 完全一致；移动端自动上下堆叠 | ✅ |
| 控件高度 | 发送按钮统一 `h-10`（40px），移除验证码登录页的 `sm:h-12`；与输入框、验证码容器齐平 | ✅ |
| 文字垂直居中 | `Input` 与验证码格子统一 `leading-10`，行高=控件高度，修复占位符/输入值偏下 | ✅ |
| 三页一致性 | 注册、密码/验证码登录、找回密码共用同一套输入与验证码控件 | ✅ |

**UI 验收记录**
- Playwright 1440×900 桌面：验证码与按钮同排、同高；填充 123456 自动分配 + 聚焦态正常
- Playwright 390×844 移动端：验证码/按钮堆叠，`scrollWidth == clientWidth`（无横向溢出）
- `npm run build`（vue-tsc + vite）：通过
- 后端未改动；全量 `pytest -q` 仍为 **42 passed**

### 4.8 工作台行情速查（2026-10-21，P3 前哨）

> 后续已改为「查询直接进入详情页」，工作台不再内联预览；当前行为见 4.13。

| 模块 | 内容 | 状态 |
| --- | --- | --- |
| `api/market.ts` | `Quote` / `KlineSeries` 类型；`quote` / `kline` 请求封装 | ✅ |
| `components/market/MiniKline.vue` | 近 60 日 SVG K 线 + 成交量柱；区间、日期范围、红涨绿跌；无第三方图表依赖；支持大尺寸模式 | ✅ |
| `components/market/StockLookup.vue` | 代码输入 + 4 个快捷标的；**进入页面不自动请求**，用户点击才查询；12 项报价指标；报价/K 线来源、时间、延迟标记；加载/错误/空数据态 | ✅ |
| `DashboardPage.vue` | 行情数据源/缓存/额度/自选统计；P2 完成说明；P3–P5 路线 | ✅ |
| `tokens` | 复用 A 股红涨绿跌与 `tabular-nums`；图表使用设计 token | ✅ |

**行情速查验收记录**
- Playwright 临时账号真实登录：进入工作台后 `stockRequests = 0`，确认刷新不会自动请求；点击快捷标的才发报价 + K 线请求
- 输入 300750 切换宁德时代成功；报价来源腾讯行情、K 线来源东方财富，页面同时标注 `source` 与 `fetched_at`
- 桌面 1440 / 移动端 390：图表正常渲染，`scrollWidth == clientWidth`，无横向溢出
- `npm run build` 通过；后端未改动，`pytest -q` 仍为 **42 passed**

### 4.9 个股详情页 v1（2026-10-21）

| 模块 | 内容 | 状态 |
| --- | --- | --- |
| 路由 | `/stock/:symbol`（requiresAuth）；支持直接访问与页面内切换代码 | ✅ |
| `StockDetailPage.vue` | 报价头 + 12 项指标 + 日/周/月 K + 前复权/后复权/不复权 + 来源/时间 | ✅ |
| `MiniKline.vue` | 新增 `large` 模式（移动 280px / 桌面 380px 固定高度）；`preserveAspectRatio="none"` 适配响应式宽度 | ✅ |
| `utils/market.ts` | 统一价格/量额/百分比/来源/时间格式化与涨跌色 | ✅ |
| 入口 | 工作台查询结果「查看详情 →」；详情页「切换股票代码」表单 | ✅ |

**个股页验收记录**
- 进入工作台不自动请求；点快捷标的后正常查询
- `/stock/600519`：默认日 K / 前复权；切周 K + 后复权均返回 200，图表与 12 项指标正常
- Playwright 桌面 1440 / 移动 390：`scrollWidth == clientWidth`；大尺寸图表在移动端 280px 可读
- `npm run build` 通过；后端 `pytest -q` **42 passed**

**待补**：klinecharts + MA/MACD/BOLL、资金流与新闻、股票名称/拼音搜索、自选股。

### 4.10 技术面诊断 v0（2026-10-21，P4 前哨）

| 模块 | 内容 | 状态 |
| --- | --- | --- |
| `services/technical_analysis.py` | MA5/10/20/60、MACD、RSI14、BOLL、ATR14、量比；评分/评级/趋势/信号/支撑压力/三档价位 | ✅ |
| `schemas/analysis.py` | `TechnicalAnalysis` / `AnalysisSignal` / `IndicatorSnapshot` / `PriceLevels`；`computed_by=code` | ✅ |
| `GET /stocks/{symbol}/analysis` | 复用行情缓存 + 90 根日 K 前复权；登录保护；数据不足返回 `ANALYSIS_UNAVAILABLE` | ✅ |
| 详情页诊断卡 | 评分/评级/摘要/信号/关键价位/指标快照/免责声明；来源映射为中文 | ✅ |
| 测试 | 引擎 4 个 + 接口 1 个：上升/下降趋势、指标、价位顺序、数据不足 | ✅ |

**技术诊断验收记录**
- 后端全量 `pytest -q`：**47 passed**（原 42 + 技术诊断 5）
- 真实数据：600519 评分 82「强势」上升趋势；300750 评分 22「弱势」下降趋势
- 价位约束：止损 < 入场 < 现价 < 止盈；`stop_loss` 按 ATR 在 −5%~−8% 间钳制
- 详情页桌面 1440 / 移动 390：诊断卡正常、无横向溢出；`npm run build` 通过
- 未使用 LLM Key；本版为六分析师中的**技术面分析师规则版**

**说明**：规则版先把「可复现、零成本」的技术面结论跑通；LLM 版技术面分析与其余五位分析师在 P4 接入。

### 4.11 LLM 综合研判 v1（2026-10-21，P4 起步）

| 模块 | 内容 | 状态 |
| --- | --- | --- |
| `core/config.py` | `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` / 超时 / max_tokens / temperature / 缓存时长 | ✅ |
| `llm/client.py` | `AsyncOpenAI`（OpenAI 兼容），`max_retries=0`；JSON 提取 + `json_repair` 兜底；错误分类 | ✅ |
| `llm/prompts.py` | 技术面 + 风险提示词；`PROMPT_VERSION` 含内容 hash，提示词变更自动换缓存 | ✅ |
| `schemas/ai.py` | 结构化输出校验：评级/趋势别名归一、置信度 clamp、要点/风险列表归一 | ✅ |
| `services/ai_analysis_service.py` | 同股同交易日 + 同模型 6h 缓存；每日额度；输出校验失败重试 1 次；失败不扣额度 | ✅ |
| `services/ai_job_service.py` | Redis job 状态机、后台 runner、活跃任务去重、stale 检测；见 4.12 | ✅ |
| `POST /stocks/{symbol}/ai-analysis` | 创建后台任务，202 返回 job_id；未配置/无效代码立即报错；LLM 失败在 job 状态中返回 | ✅ |
| `GET /ai/jobs/{job_id}` | 查询 queued/running/succeeded/failed、阶段、已等待秒数与结果 | ✅ |
| `GET /ai/config` | 返回 configured / model / prompt_version / daily_quota / quota_used（不含密钥） | ✅ |
| 详情页 AI 卡 | 未配置提示、按钮提交、轮询阶段/耗时、评级/置信度/摘要/依据/风险/额度/模型版本 | ✅ |

**LLM 验收记录**
- 用本地 OpenAI 兼容 mock 服务走真实 `AsyncOpenAI` 链路：首次生成 `quota_used=1`，第二次 `cached=true`、额度不变，mock 只收到 1 次请求
- 未配置时：`GET /ai/config` → `configured=false`；`POST /ai-analysis` → 503 `LLM_NOT_CONFIGURED`，不会请求行情或 LLM
- 后端全量 `pytest -q`：**60 passed**（新增 13 个 LLM/额度/缓存/异步 job/接口用例）
- 前端 `npm run build` 通过；未配置态、轮询中、完成态均完成 1440 桌面验收
- **未使用外部 LLM Key**；需要用户填 `.env` 后重启后端
- ✅ **2026-10-21 12:10 真实 Key 验收通过**：商汤 SenseNova（`sensenova-6.8-flash-lite`）连通，真实调用返回规范 JSON（rating/confidence/summary/key_points/risks 全部合规），`extract_json` 解析成功
- ⚠️ **该模型是推理型**：响应带 `message.reasoning`，思考过程消耗 completion token（实测 64 token 全被思考吃掉）。已把 `llm_max_tokens` 从 900 放宽到 **2048**，否则正文被截断、JSON 解析必失败
- 手动验证脚本：`backend/manual_test_llm.py`（不落库，直接跑真实模型）

**说明**：v1 是一次结构化 LLM 调用（技术面 + 风险），不是六分析师并行；多分析师编排、讨论、SSE、密钥加密与管理后台留在 P4 后续。

### 4.12 AI 分析异步任务化（2026-10-21）

**背景**：同步 HTTP 等待 LLM 时，慢模型/推理模型会触发前端 90s 超时。参考 `aiagents-stock` 在 Streamlit 会话里跑数分钟并显示进度条的做法，改为**后台任务 + 轮询**。

| 模块 | 内容 | 状态 |
| --- | --- | --- |
| `services/ai_job_service.py` | Redis job 状态机 queued→running→succeeded/failed；phase/耗时；active key 去重；服务重启后 stale job 自动失败 | ✅ |
| `POST /ai-analysis` | 立即返回 202 + job_id，不再在 HTTP 请求里等 LLM | ✅ |
| `GET /ai/jobs/{job_id}` | 前端每 2s 轮询；返回阶段、已等待秒数、结果或错误码 | ✅ |
| 超时策略 | 单次 LLM 调用 180s，整个 job 420s；SDK `max_retries=0`；空响应不重复重试 | ✅ |
| 前端 AI 卡 | 提交后显示「LLM 分析中 · 已等待 N 秒」；切页停止本地轮询，任务继续；重进后可复用 active job | ✅ |

**异步化验收**
- 本地 mock LLM 全链路：POST 202 → 轮询 succeeded；首次 quota=1；第二次 cached=true 且 mock 只收到 1 次请求
- 前端 Playwright：轮询中显示「LLM 分析中（可能需要 1–3 分钟）· 已等待 4 秒」，完成后展示评级/依据/风险/额度
- 后端 **60 passed**；前端构建通过
- 真实 SenseNova 任务不会因浏览器 90s 超时被中断；若模型本身超时/返回空，会在 job 状态中给出明确错误

### 4.13 工作台查询直达详情页（2026-10-21）

**背景**：工作台内联预览 + 进入详情会重复请求报价/K 线；改为工作台只做入口。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| `StockLookup.vue` | 只保留代码输入 + 快捷标的 + 错误提示；提交/点击直接 `router.push('/stock/:symbol')` | ✅ |
| `DashboardPage.vue` | 不再加载报价/K 线，只保留统计、路线与进度 | ✅ |
| 详情页 | 统一加载 quote / kline / analysis / ai-config；后端行情缓存继续共享 | ✅ |

**验收**
- 登录后工作台 `beforeNavigationRequests = 0`
- 提交 601318 后只产生详情页请求：quote、kline、analysis、ai/config，没有工作台重复请求
- `npm run build` 通过；后端 **60 passed** 不受影响

### 4.14 元宝搜索接入（2026-10-21）

**背景**：项目缺少新闻/公告/事件数据；按参考项目「单股分析只调 1 次元宝搜索」的做法，补公开网页信息。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| `services/web_search_service.py` | 腾讯云 WSA `SearchPro`；20 条 → 去重 → top 8；30 分钟 Redis 缓存；未配置自动跳过 | ✅ |
| AI job | 先查 6h AI 缓存；未命中才执行一次元宝搜索；阶段显示「检索公开信息」 | ✅ |
| Prompt | `public_web_info` 带 title/site/date/url；要求核对日期、只作事件背景、不得当财务事实 | ✅ |
| 响应/UI | `web_search_used` + `web_sources`；AI 卡展示来源链接与数据覆盖说明 | ✅ |

**元宝搜索验收**
- 本地 mock WSA + mock LLM 全链路：`search_calls=1`、`llm_calls=1`、prompt 包含 `public_web_info`
- 第二次分析命中 6h 缓存：不新增搜索、不新增 LLM 调用
- 未配置任何 WSA 凭据时跳过搜索，AI 分析继续
- 前端来源链接、数据覆盖说明已验收；后端 **64 passed**，前端构建通过

**成本策略**：一次个股分析最多 1 次搜索；搜索缓存 30 分钟；AI 缓存 6 小时优先；批量分析默认不搜索。

### 4.15 六维数据、六分析师、首席决策与历史报告（2026-10-21）

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 财务/季报 | 东财 F10 最近 6 期：营收/净利/同比/ROE/毛利率/净利率/负债率/流动比率/EPS/BPS，缓存 12h | ✅ |
| 资金流 | 东财近 30 日主力/超大单/大单/中单/小单净流入与占比，缓存 5min | ✅ |
| 市场情绪 | ARBR(26) 本地计算 + 换手/RSI/量比 + 上证/深证当日涨跌，指数缓存 60s | ✅ |
| 六分析师 | 技术/基本面/资金面/风险/情绪/新闻，统一 `AnalystReport`（score/rating/summary/points/risks/data_sources/missing） | ✅ 规则+数据 |
| 首席决策 | `FinalDecision`：买入/持有/卖出、置信度、操作建议、持有周期、仓位、核心理由、风险、共识/分歧、代码价位；LLM 失败规则兜底 | ✅ |
| 历史报告 | `analysis_reports` JSONB 表 + Alembic 迁移；用户隔离；列表/详情 API；详情页历史回看 | ✅ |
| 报告详情页 | `/reports/:id`：完整六分析师（全部依据/风险/来源/缺口）+ 首席决策 + 价位 + 元宝来源；当前 AI 卡与历史列表均可进入 | ✅ |
| 数据缺口 | 每个分析师带 `missing`，决策 prompt 要求降低置信度并写入 risks；UI 展示数据覆盖/缺口 | ✅ |

**验收**
- 真实行情/财务/资金流/情绪 + 本地 mock LLM 全链路：六分析师报告生成、决策 `买入 76`、价位 `computed_by=code`；元宝搜索 1 次、LLM 1 次
- 第二次分析命中 6h 缓存：搜索/LLM 均为 0 次；历史不重复新增
- 报告落库并可通过 `/api/v1/analysis/reports` 列表、`/{id}` 详情回看；用户隔离已测
- 后端 **66 passed**；前端构建通过；桌面/移动端六分析师与历史布局无横向溢出
- 真实财务/资金流/情绪已打通；真实 SenseNova 决策尚未由我调用验证（规则兜底可保证链路完成）。真实元宝 Key 当时未配置，后已在 4.16 完成官方 TC3 实测接通

**说明**：参考项目是 6 次独立 LLM + 讨论 + 决策；当前六份分析师报告由代码基于真实数据生成，首席策略官用 1 次 LLM。这样成本/延迟更低、结果可复现；需要 LLM 版分析师时可在 P4 后续逐位替换。PDF、并排 diff、SSE/ARQ、批量/定时仍在后续。

### 4.16 元宝 SearchPro 官方 API 对齐（2026-10-21）

**问题**：此前按参考项目使用 `https://api.wsa.cloud.tencent.com/SearchPro` + `Authorization: Bearer`。对照腾讯云官方文档（`wsa.tencentcloudapi.com`、Action `SearchPro`、Version `2025-05-08`），这属于服务 API KEY 兼容模式，不是官方云 API 3.0 的 TC3 签名调用。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 官方模式 | `WSA_SECRET_ID`+`WSA_SECRET_KEY` → `https://wsa.tencentcloudapi.com/`；`X-TC-Action`、`X-TC-Version`、`X-TC-Timestamp`、`X-TC-Token`（临时密钥）与 TC3-HMAC-SHA256 签名 | ✅ |
| 请求参数 | `Query`、`Mode=0`、`Industry=finance`、`Cnt=20`、`Freshness=m3`（可配）；参数放在 JSON body | ✅ |
| 响应解析 | `Response.Pages`（JSON 字符串数组）、`Version`、`Msg`、`RequestId`；`Response.Error` 映射鉴权/未开通/限流提示 | ✅ |
| Bearer 兼容 | 只有 `WSA_API_KEY` 时走原服务地址与 `Authorization: Bearer`，不追加 `Freshness`；两套凭据同时存在时优先官方模式 | ✅ |
| 配置 | `.env.example` 增加 `WSA_SECRET_ID/SECRET_KEY/SECRET_TOKEN/SEARCH_HOST/SEARCH_VERSION/SEARCH_FRESHNESS`；凭据全部留空 | ✅ |
| 测试 | MockTransport 校验官方 URL/Header/TC3 授权格式/参数/`Response.Error`；Bearer 保持原行为；SecretId 误填 `WSA_API_KEY` 时发请求前拦截 | ✅ 70 passed |

**曾发现问题**：最初 `.env` 的 `WSA_API_KEY` 填成了 `AKID` 开头的 SecretId，而不是 `sk-` 服务 API KEY。已加预检提示，不会把 SecretId 当 Bearer 发出去；现用户已改为官方 `WSA_SECRET_ID + WSA_SECRET_KEY`。

**真实验证（2026-10-21）**：用户补齐 `WSA_SECRET_ID/WSA_SECRET_KEY` 后，官方 TC3 模式真实调用成功：`success=True`、`version=standard`、返回 8 条公开网页结果（贵州茅台/公告），说明签名、Host、Action/Version 与参数均可用。新增 `backend/manual_test_wsa.py`：默认只检查配置，加 `--live` 发起一次计费搜索；命令见 README「怎么确认已经接通」。

**说明**：标准版/旗舰版支持 `Mode/Cnt/Industry/Freshness`；极速版会拒绝这些参数，需要升级或改用 Bearer 服务 KEY。

### 4.17 全部历史报告入口（2026-10-21）

**背景**：历史报告此前只能进入某只股票详情页后查看该股最近 6 份，入口过少。参考用户提供的个人中心菜单样式，在顶栏加入用户菜单，并增加跨股票的历史报告页。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 顶栏用户菜单 | 头像/昵称触发；包含「工作台」「历史报告」「退出登录」；点击外部/Esc/路由变化自动关闭；移动端保留头像入口 | ✅ |
| 全部历史页 | 新增 `/reports`：最近 50 份，按日期分组，展示名称/代码/评级/置信度/决策来源/模型/时间；客户端按代码或名称筛选 | ✅ |
| 详情回看 | 报告详情页新增「全部历史报告」链接；历史列表点击进入 `/reports/:id` | ✅ |
| 后端 | 复用 `GET /analysis/reports`，`symbol` 可选；补充跨股票列表测试，用户隔离保持 | ✅ |
| 验收 | 后端 **70 passed**；前端构建通过；桌面 864px 与移动 390px 实际操作菜单、筛选、详情跳转，`scrollWidth=390` 无横向溢出；临时验收账号已删除 | ✅ |

**说明**：全部历史页每次进入只请求一次，不做轮询/自动刷新；筛选在已加载的 50 条内本地完成，不额外请求。

### 4.18 元宝搜索界面展示（2026-10-21）

**背景**：搜索接入后，若报告没有来源，页面上看不出「已接入元宝搜索」；需要在报告界面直接展示搜索状态，避免别人不知道搜索能力存在。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 状态标签 | 报告详情页顶部新增「元宝搜索 · 已检索 N 条 / 本次未收录」标签；有来源为品牌色，无来源为中性色 | ✅ |
| 公开信息面板 | 新增 `PublicInfoPanel`：报告页（card）与个股 AI 卡（flat）始终展示；有来源列出来源，无来源说明该报告未包含公开网页信息、相关结论按数据缺口处理 | ✅ |
| 展示位置 | 报告页面板放在首席决策与六分析师之间；个股 AI 卡放在报告内容尾部；替换原「仅成功时出现」的来源块 | ✅ |
| 验收 | 前端构建通过；桌面 1440px 与移动 390px 分别验证无来源/有来源两种报告，无来源标签与面板说明可见，`scrollWidth=390` 无横向溢出；临时验收账号与数据已删除 | ✅ |

**说明**：无来源的旧报告会显示「本次未收录」，不虚构搜索结果；新报告搜索成功时自动显示来源数量与来源列表。搜索状态以报告里落库的 `web_search_used` 与 `web_sources` 为准，不做额外请求。

### 4.19 搜索数据进入多位分析师（2026-10-21）

**背景**：此前只有新闻分析师直接使用元宝搜索结果，其余五位的依据里看不到搜索痕迹，容易让人觉得「搜索没效果」。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 新闻分析师 | 维持现状：来源列表 + 正面/负面关键词计数 | ✅ |
| 风险分析师 | 按减持/解禁/处罚/立案/诉讼/质押等关键词提取事件线索：依据展示线索、风险提示需以正式公告核实、命中时按条数小幅降分且不再标记「公告级风险事件」缺口 | ✅ |
| 基本面分析师 | 按业绩/回购/分红/中标等关键词提取公司动态线索；财务缺失时也能用公开信息补充线索（缺口仍标注） | ✅ |
| 情绪分析师 | 公开信息正面/负面关键词计数进入评分（±最多 6 分）；情绪数据缺失时用公开信息兜底（缺口仍标注） | ✅ |
| 界面体现 | 「公开信息」面板新增「已用于：XX分析师」（从 `analysts[].data_sources` 推导）；各分析师卡的「来源」中出现「元宝搜索」 | ✅ |
| 测试 | 新增多分析师消费搜索结果的用例；后端 **71 passed**，前端构建通过 | ✅ |

**说明**：搜索结果只作线索与情绪参考，不替代正式公告与结构化财务数据；风险线索会明确提示「以正式公告核实」。

### 4.20 工作台首页改版（2026-10-21）

**背景**：首页统计卡全部写死（「今日分析额度 0/5」「自选股 0 · P3 开放」），额度提示还停留在「Agent 上线后启用」；下方挂着 P3/P4/P5 路线图与「当前进度」开发日志，且不展示任何用户自己的数据。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 统计卡 | 改为真实数据：额度取 `GET /ai/config`（未配置显示「LLM 未配置」），报告数/覆盖股票取 `GET /analysis/reports`（最近 50 份），行情源保留 | ✅ |
| 最近分析 | 首页展示最近 5 份报告（跨日显示 MM-DD HH:mm），带骨架屏/错误重试/空态；空态引导完成首次分析 | ✅ |
| 移除 | 删除首页「接下来」（P3/P4/P5 模块卡）与「当前进度」开发日志，路线图只保留在本文档 | ✅ |
| 组件抽离 | 新增 `components/report/ReportListItem.vue`、`ReportListSkeleton.vue` 与 `utils/report.ts`（time/ratingTone/sourceLabel/dayLabel），首页与历史页共用，去掉历史页内重复实现 | ✅ |

**验收**：`npm run build`（vue-tsc + vite）通过；后端未改动，接口与数据格式不变。

---

## 五、未完成清单（按优先级）

### 5.1 马上要做的（P1 收尾）
| 事项 | 说明 |
| --- | --- |
| ⬜ git 初始化 + 首次提交 | `git init` + 提交骨架；`.env` 已在 .gitignore |
| ⬜ SMTP 真实发信联调 | 用户填 `.env` 的 `SMTP_USER`/`SMTP_PASSWORD`（授权码）并把 `EMAIL_MODE` 改 `smtp`，重启后端实测收件 |
| ⬜ admin 账号 | 无注册入口生成 admin；需提供 SQL 或 CLI 脚本 |

### 5.2 P2 行情数据层（进行中，2026-10-21）
| 事项 | 说明 | 状态 |
| --- | --- | --- |
| Provider 协议 | `QUOTE/KLINE` 已完成；`PROFILE/FINANCIAL/FUND_FLOW/NEWS` 中财务/资金流已接，新闻仍以元宝公开网页补 | 🟡 部分完成 |
| 降级链 | 报价 tencent→sina→eastmoney；K线 eastmoney→tencent→sina 已实测 | ✅ |
| 五件套抗压 | 多级缓存 TTL、singleflight、Redis 令牌桶、按 provider+capability 熔断、全局信号量 8 | ✅ |
| AKShare 接入规范 | 未引入 AKShare；财务/资金流改为东财直连，减少重依赖 | ✅ 采用替代方案 |
| 统一模型 | `Quote`/`KlineSeries` + `FinancialData`/`FundFlowData`/`SentimentData` 已统一 | ✅ |
| 财务/季报 Provider | 东财 F10 最近 6 期：营收/净利/增速/ROE/毛利率/负债率等，缓存 12h | ✅ |
| 资金流 Provider | 东财近 30 日主力/超大单/大单/中单/小单，缓存 5min | ✅ |
| 情绪数据 | ARBR 本地计算 + 换手/RSI/量比 + 主要指数当日涨跌，缓存 60s | ✅ |
| 新闻/公告结构化 Provider | 目前用元宝公开网页；交易所/东财公告结构化仍待做 | ⬜ |
| 股票搜索接口 | 代码/名称/拼音模糊搜索（⌘K 数据源）+ `stocks` 表 | ⬜ |
| `stocks` 表 + 全量 A 股种子 | 东财 clist 拉取代码/名称/交易所，落库供搜索与外键引用 | ⬜ |

### 5.3 P3 个股页（进行中）
- ✅ 工作台行情速查（2026-10-21）：已改为输入代码/快捷标的直接进入详情页，不在工作台重复查询
- ✅ `/stock/:symbol` 详情页 v1：报价头、12 指标、日/周/月 K、前/后/不复权、代码切换（2026-10-21）
- ⬜ klinecharts 完整 K 线（MA/MACD/BOLL）、资金流、新闻列表
- ⬜ 股票搜索（代码/名称/拼音）与 `stocks` 表种子
- ⬜ 自选股（watchlist 表 + CRUD + 列表行情）—— 原计划在 P6，可与 P3 一起做
- ⬜ 每用户日配额检查（`daily_analysis_quota`）

### 5.4 P4 Agent 编排与任务
- ✅ 技术面分析师 v0（规则引擎）：MA/MACD/RSI/BOLL/ATR、评分、支撑压力、三档价位（2026-10-21）
- ✅ LLM 综合研判 v1：OpenAI 兼容 client、JSON 提取/修复、Pydantic 校验、失败重试 1 次、6h 缓存、每日额度（2026-10-21）
- ✅ 异步 job + 轮询：POST 返回 job_id，状态机 queued→running→succeeded/failed，避免慢模型触发 HTTP 超时（2026-10-21）
- ✅ 元宝搜索：一次分析最多 1 次公开网页检索，缓存 30 分钟；官方 TC3（`WSA_SECRET_ID/SECRET_KEY`）已实测接通（standard 版），Bearer 兼容模式保留（2026-10-21）
- ✅ 搜索结果进入四位分析师：新闻（来源）、风险（事件线索）、基本面（公司动态）、情绪（关键词计数）；「公开信息」面板展示「已用于：XX分析师」（2026-10-21）
- ✅ 六维数据：财务/季报、资金流、情绪、公开网页已接入，缺失维度在分析师报告中标注（2026-10-21）
- ✅ 六分析师 + 首席决策：技术/基本面/资金面/风险/情绪/新闻六份结构化报告；LLM 决策 + 规则兜底；决策含操作建议/持有周期/仓位/风险（2026-10-21）
- ✅ 报告历史：PostgreSQL `analysis_reports`、用户隔离、按股票列表/详情、详情页回看（2026-10-21）
- ✅ 全部历史入口：顶栏用户菜单 + `/reports` 跨股票列表（日期分组/筛选），报告页可返回全部历史（2026-10-21）
- ✅ 详情页 AI 分析卡：未配置提示、手动触发、轮询阶段/耗时、六分析师卡片、决策/价位/数据缺口/额度展示（2026-10-21）
- ✅ 价位代码计算：entry −2% / 止盈 +8% / 止损 ATR 钳制 −5%~−8%，`computed_by="code"`
- 🟡 六分析师实现方式：当前由代码基于真实数据生成，未逐位调用 LLM（成本/延迟更低）；LLM 版可后续逐位替换
- ⬜ 团队讨论时间线、SSE 流式、ARQ worker、批量/定时
- ⬜ `llm/crypto.py`：AES-256-GCM 密钥加密，主密钥 `APP_ENCRYPTION_KEY` 走环境变量
- 🟡 `prompts/v1/`：首席决策提示词在代码中；六分析师/讨论的 YAML 化待做
- ⬜ ARQ worker（当前用进程内 asyncio task；服务重启会中断，已做 stale 检测；后续迁移 ARQ + 条件 UPDATE 抢占）
- ⬜ SSE：Redis Pub/Sub 转发，事件 `job_status/agent_started/agent_token/agent_completed/discussion_*/decision_completed/done/error`，15s 心跳，断线按 `agent_runs` 回放
- 🟡 数据表：`analysis_reports` 已建；`analysis_jobs`、`agent_runs`、`llm_providers`、`app_settings`、`usage_daily` 待做

### 5.5 P5–P7
- 🟡 分析报告页：独立 `/reports/:id` 已上线，完整展示六分析师/决策/价位/来源；6 维雷达、DiscussionTimeline、AgentStreamCard 待做
- ✅ 历史报告落库与按股票回看，当前 AI 卡与历史列表均可进入报告详情（2026-10-21）
- ⬜ 历史对比：同股多次分析并排 diff
- ⬜ PDF 导出
- ⬜ 管理后台：用户管理、LLM Provider 配置（密钥只回 last4）、数据源开关、任务日志
- ⬜ 生产部署：Nginx 同域反代 + HTTPS、`COOKIE_SECURE=true`、日志轮转、DB 备份、限流压测（50 并发浏览 + 5 并发分析）

### 5.6 明确不做（防止范围膨胀）
- ⬜❌ 交易下单 / 券商接口（永久不做）
- ⬜❌ 港股美股（第二期后再评估）
- ⬜❌ 多租户团队协作
- ⬜❌ 移动端原生 App（响应式网页足够）

---

## 六、风险登记表

| 风险 | 等级 | 对策 | 状态 |
| --- | --- | --- | --- |
| 免费数据源封 IP（公网共享出口） | 高 | 缓存优先 + 熔断时前端显示「数据延迟」而非 500 + 多源降级 + UA 规范 + 预留 `EGRESS_PROXY_URL` | 架构已设计，P2 落地 |
| LLM 成本被刷 | 高 | 日配额 + 6h 结果复用 + 上下文压缩 + max_tokens 上限 + `usage_daily` 记账 | 部分落地（配额/缓存/上限已做，记账待做） |
| LLM 输出格式不稳定 | 中 | 提示词约束 + Pydantic 校验 + json_repair + 失败重试 1 次；仍失败返回 502，不扣额度 | ✅ |
| 慢模型/推理模型导致 HTTP 超时 | 高 | 改后台 job + 轮询；单次 LLM 180s、job 420s；SDK 不自动重试；空响应不重复重试 | ✅ |
| 元宝搜索成本/结果质量 | 中 | 一次分析最多 1 次；30min 搜索缓存 + 6h AI 缓存优先；来源带日期/站点；失败/未配置自动跳过 | ✅ |
| AKShare 同步线程无法取消 | 中 | socket timeout + 线程池上限 8 + 超时丢弃 | 待 P2 |
| 验证码被爆破 | 中 | 已实现三重限流 + 5 次作废 | ✅ |
| refresh 被盗用 | 中 | 已实现轮换 + 重放检测全吊销 | ✅ |
| QQ/163 判垃圾邮件 | 低 | 规范发信人、纯 HTML 无外链、先发自己邮箱测试 | 待 SMTP 联调 |
| AKShare 接口变更 | 中 | 解析失败归 `SchemaDrift` 告警；关键路径用直连 HTTP | 待 P2 |
| 端口冲突 | 低 | 前端 5288 strictPort、后端 8010；改端口需同步 4 处（package.json / Makefile / vite proxy / README） | ✅ |

---

## 七、关键决策记录（ADR 摘要）

1. **不用 SQLite**：公网多用户并发写会排队，直接上 PostgreSQL 16。
2. **不用 Celery / WebSocket**：单机规模下 ARQ + Redis + SSE 足够，少三个运维面。
3. **不用 shadcn-vue / Element Plus**：手写 5~8 个基础组件 + token 化样式，控制「后台模板感」。
4. **邮箱存小写字符串而非 citext**：统一在 service 边界 `strip().lower()`，跨库可移植。
5. **service 层显式 commit**：FastAPI 0.106+ 的 yield 依赖在响应发出后才执行收尾，依赖里自动提交有「已返回 200 但提交失败」的风险。
6. **验证码不落库**：Redis TTL 天然过期，省清理任务；哈希存储防止 Redis 泄露即验证码泄露。
7. **热点行情不走 AKShare**：腾讯/新浪直连快 5–10 倍且稳；AKShare 只做宽表（财务/资金流/新闻）。

---

## 八、环境与命令速查

```bash
npm run up          # docker compose 启动 pg + redis
npm run migrate     # alembic upgrade head
npm run api         # 后端 http://127.0.0.1:8010（--reload）
npm run web         # 前端 http://127.0.0.1:5288
npm run test        # pytest（需先 up + migrate）
npm run build       # vue-tsc + vite build
```

- 接口文档：`http://127.0.0.1:8010/docs`
- 健康检查：`http://127.0.0.1:8010/health`
- 后端日志（当前会话）：`/tmp/zy-backend.log`；验证码在 `EMAIL_MODE=console` 时打印于此

**改后端端口需同步 4 处**：`package.json`、`Makefile`、`frontend/vite.config.ts`（proxy target）、`README.md`。

---

## 九、当前待办（按顺序）

1. `git init` + 首次提交（P1+P2 基线仍未纳入版本管理）
2. SMTP 真实发信联调（需要用户提供邮箱授权码）
3. admin 账号生成脚本（SQL 或 CLI）
4. P2 收尾 A：`stocks` 表 + 全量 A 股种子 + 股票搜索接口（代码/名称/拼音）
5. P2 收尾 B：财务 / 资金流 / 新闻 Provider + AKShare 线程池接入
6. P3：股票名称/拼音搜索 + 自选股 + klinecharts 指标（个股详情页 v1 + 技术诊断 + 历史已完成）
7. P4：六分析师逐位接 LLM + 团队讨论时间线 + SSE/ARQ（当前六分析师规则版 + 首席 LLM 决策已完成）
8. P5：历史并排 diff + PDF 导出
