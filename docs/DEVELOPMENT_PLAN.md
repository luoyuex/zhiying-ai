# 智盈 AI 开发计划与进度总览

> 本文档是项目的唯一进度真相源。每完成一个阶段，更新「状态」列与「已完成清单」，避免范围漂移与重复劳动。
> 最后更新：2026-10-23（定时选股/定时分析上线并支持用户自定义执行时间；日志落盘；体验修复见 4.43）

---

## 一、项目定位

**智盈 AI —— A 股 AI 分析工作台**：输入一只股票，六个分析师（技术面/基本面/资金面/风险管理/市场情绪/新闻舆情）并行出报告，再由首席策略官汇总成「评级 + 三档价位 + 置信度 + 风险提示」的可执行结论。

参考项目 `aiagents-stock`（Streamlit 单体）：只借鉴其**业务逻辑**（Agent prompt、打分规则、数据接口经验），UI 与工程架构全部重写。

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

| 阶段 | 内容 | 状态 | 说明 |
| --- | --- | --- | --- |
| P1 | 项目骨架 + 邮箱验证码认证 | ✅ 完成 | 注册/登录/刷新轮换/重置密码全通；SMTP 真实收信待实测；admin 账号 CLI 已补 |
| P2 | 行情数据层（Provider + 缓存/限流/熔断） | ✅ 完成 | 报价/K 线/财务/资金流/情绪/股票库/公告新闻已上线；新闻公告结构化 Provider 见 4.42 |
| P3 | 个股页（报价/K 线/指标） | ✅ 完成 | 报价头、指标面板、日/周/月 K、复权、技术诊断、搜索、自选、MA/BOLL/MACD 叠加、资金流图、资讯列表均已上线 |
| P4 | Agent 编排 + 分析任务 + SSE | ✅ 基本完成 | 六分析师、讨论、首席决策、SSE、ARQ、报告历史、重新分析已上线；定时分析、密钥加密、记账未做 |
| P5 | 分析报告页 + 评分卡 | ✅ 完成 | 报告详情、历史列表、6 维雷达、同股并排对比、PDF 导出已上线 |
| P6 | 自选股 + 分析历史对比 | � 部分完成 | 自选股、持仓联动、组合诊断、批量分析已完成；持仓历史/评级变化/提醒未做 |
| P7 | 管理后台 + 生产部署 | 🟡 P0 完成 | `/app/admin` 运营总览、用户与额度、操作审计、LLM/任务台账已上线；任务中心、成本日报、数据源、内容运营与生产部署待做 |
| P8 | 选股策略模块族 | ✅ 五策略完成 | 主力追踪、低价寻宝、小盘精选、业绩高增、价值洼地全部 AI 化：规则候选 + 三分析师 + 资深研究员精选 + 后台任务 + 记录落库/历史；与参考项目的数据口径差异见 5.6；其余板块未做 |

### 3.1 功能模块总账（一眼看懂）

| 业务模块 | 状态 | 已实现 | 缺口 |
| --- | --- | --- | --- |
| 认证与用户 | ✅ 完成 | 邮箱验证码注册、密码/验证码登录、JWT、refresh 轮换、重放检测、登出、重置密码、限流；管理员 CLI | SMTP 真实收信实测 |
| 后台管理 | 🟡 P0 完成 | `/app/admin`：运营总览、用户额度/封禁/强制下线、审计日志、LLM 调用与任务台账 | P1–P4：成本日报、任务中心、内容库、数据源、公告/反馈 |
| 工作台 | ✅ 完成 | 问候、股票查询（代码/名称/拼音）、概览统计、最近分析、自选/历史入口 | — |
| 股票基础库 | ✅ 完成 | `stocks` 表、5925 只 A 股种子、代码/名称/全拼/首字母搜索 | 定期增量更新（当前为手动种子） |
| 个股详情页 | ✅ 完成 | 报价头、12 项指标、日/周/月 K、前/后/不复权、技术诊断、加入自选、MA/BOLL/MACD 叠加、资金流图、公告/新闻/AI 资讯 | — |
| 六分析师 AI 分析 | ✅ 完成 | 技术/基本面/资金面/风险/情绪/新闻六位分析师、团队讨论、首席决策、SSE 进度、ARQ、活跃任务恢复 | 定时/批量调度（自选批量已做） |
| 报告中心 | ✅ 完成 | 报告落库、按股票回看、全部历史、来源返回、重新诊断、6 维雷达、同股并排 diff、PDF 导出 | — |
| 自选股 | ✅ 完成 | 增删改查、最新 AI 结论、备注/成本/数量、浮动盈亏、批量分析、状态刷新恢复、详情页任务同步 | — |
| 组合 AI 诊断 | ✅ 完成 | 汇总持仓与最新结论，输出组合健康度、风险提示、逐只操作建议；诊断结果落库，自选页恢复最近一次，历史报告页可回看 | — |
| 持仓联动分析 | ✅ 完成 | 成本/数量/备注注入分析提示词、报告「我的持仓建议」、缓存按持仓失效 | 持仓变动历史、调仓记录 |
| 选股模块 | ✅ 五策略完成 | 五条策略（主力追踪/低价寻宝/小盘精选/业绩高增/价值洼地）全部 AI 化：规则候选池 + 三位分析师 + 资深研究员精选；后台任务、阶段进度、刷新续跑、失败重试、记录落库、独立历史与详情抽屉 | 与参考项目数据口径差异（见 5.6）；策略自动定时运行、结果导出未做 |
| 个人中心 | ✅ 完成 | 全局弹窗（AppShell 挂载）：账号信息、今日额度、近期报告/自选股统计、快捷入口；资料设置（昵称修改 `PATCH /auth/me`）；修改密码（`POST /auth/password/change`，吊销全部会话强制重登） | 邮箱修改、头像上传未做 |

### 3.2 参考项目 `aiagents-stock` 模块对齐

| 参考模块 | 智盈状态 | 说明 |
| --- | --- | --- |
| 股票分析 | ✅ 已对齐 | 六分析师 + 团队讨论 + 首席决策，覆盖参考项目的单股分析主流程 |
| 主力选股（主力追踪） | 🟡 核心对齐 | AI 决策链一致（三分析师 + 资深研究员）；数据口径差异：参考用问财按时间区间取前 100，我们用新浪当日排行前 300 取 40；无时间区间/市值区间，默认涨幅 7% vs 30% |
| 低价擒牛（低价寻宝） | ✅ 规则对齐 + AI 增强 | 参考项目为纯规则列表（无 AI）；我们保留同一规则候选，叠加三分析师 + 精选 |
| 小市值（小盘精选） | ✅ 规则对齐 + AI 增强 | 同上：规则候选与参考一致，AI 为增强 |
| 净利增长（业绩高增） | ✅ 规则对齐 + AI 增强 | 参考项目净利同比 ≥10%、按成交额升序、无 AI；我们同一候选规则 + 三分析师 + 精选 |
| 低估值（价值洼地） | ✅ 规则对齐 + AI 增强 | PE/PB/股息率/负债率/流通市值规则候选（东财估值快照 + 分红 + 财务），AI 为增强；股息率按近 12 个月已实施分红计算 |
| 智策板块 | ⬜ 未开发 | 板块轮动与概念热点策略 |
| 智瞰龙虎 | ⬜ 未开发 | 龙虎榜席位与资金跟踪 |
| 新闻流量 | ⬜ 未开发 | 新闻热度/舆情选股 |
| 宏观分析 | ⬜ 未开发 | 宏观指标解读 |
| 宏观周期 | ⬜ 未开发 | 周期定位与资产配置 |
| 持仓分析 | 🟡 部分对齐 | 自选组合诊断 + 持仓联动已做；持仓历史、收益归因、调仓建议未做 |
| AI 盯盘 | ⬜ 未开发 | 盘中异动监控与提示 |
| 实时监测 | ⬜ 未开发 | 定时任务 + 评级变化 + 关键价位提醒 + 通知 |
| 策略监控 / 钉钉通知 | ⬜ 未开发 | 参考项目低价/小市值带监控与钉钉推送，我们未做 |

---

## 四、已完成清单（全量，截至 2026-10-22）

### 4.1 工程骨架
- ✅ monorepo：`backend/` + `frontend/` + `docs/` + 根 `package.json`（跨平台脚本）+ `Makefile`
- ✅ `docker-compose.yml`：PostgreSQL 16 + Redis 7，带 healthcheck 与持久卷
- ✅ `.env` / `.env.example` 全套配置项，`.gitignore` 排除密钥与产物
- ✅ git 仓库已初始化并推送远端 `github.com/luoyuex/zhiying-ai`（见 5.1）

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

**后续补齐情况**：股票名称/拼音搜索、自选股已完成（见 4.21、4.29）；仍待补 K 线叠加 MA/MACD/BOLL、个股资金流与新闻列表。

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

### 4.21 股票基础库与名称/拼音搜索（2026-10-21）

**背景**：工作台只能输 6 位代码，用户不知道代码就无法查询；`stocks` 表与搜索接口此前一直缺失。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| `stocks` 表 | `code` 主键、`name`、`exchange`、`pinyin`、`abbr`、`is_active`、`updated_at`；迁移 `9d2e5a7c4b18` | ✅ |
| 列表 Provider | 东财 `clist`（沪深 A + 北交所，`pz=100` 分页）；交易所按号段推导（`SH/SZ/BJ`）；临时断连按 1/3/7s 退避重试 | ✅ |
| 拼音生成 | `pypinyin` 生成全拼（`guizhoumaotai`）与首字母（`gzmt`），忽略 `*ST`/`N`/`C` 等 ASCII 标记 | ✅ |
| 种子脚本 | `python -m app.scripts.seed_stocks`（根目录 `npm run seed`）：分批 upsert，本次未出现的代码标记停用；实测入库 **5925 只** | ✅ |
| 搜索接口 | `GET /stocks/search?q=&limit=`：代码前缀、名称包含、全拼/首字母前缀；代码与拼音精确匹配优先；登录保护 | ✅ |
| 前端补全 | 工作台查询框支持代码/名称/拼音，250ms 防抖、↑↓/Enter/Esc、点击外部关闭、沪深京标签；6 位代码仍可直接回车 | ✅ |
| 测试 | 拼音、列表归一化、同步+搜索、搜索接口 4 组用例；测试前快照、结束后还原，避免误删种子数据 | ✅ 75 passed |

**验收**
- 库内 5925 行；`gzmt` → 600519 贵州茅台；`宁德` → 300750；`600519` 精确命中；`%`/`_` 等非法字符被清洗
- 前端 `npm run build` 通过；接口层用 ASGI 用例验证（真实 HTTP 待用户启动服务后自测）

**说明**：东财会对连续全量拉取临时断连（本次实测出现过一次），重试仍失败时稍后重跑 `npm run seed` 即可，旧数据不受影响。

### 4.22 六位分析师逐位接 LLM（2026-10-21）

**背景**：此前六位分析师是规则版，只有首席决策用 LLM，报告里「六位分析师」的结论缺少模型推理；P4 要先把分析链路补完整。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| LLM 分析师 | 每位分析师独立提示词，只拿本维度原始数据 + 代码初稿；按 `llm_analyst_concurrency`（默认 3）并发 | ✅ |
| 失败隔离 | 单点超时/空响应/JSON 异常只回退该位规则稿，整份报告不中断；日志保留堆栈 | ✅ |
| 引擎标记 | `AnalystReport` 新增 `engine`（`llm` / `rule`），旧报告默认 `rule`；报告页与个股 AI 卡显示标签 | ✅ |
| 进度细分 | job 阶段变为「六位分析师分析中 0/6 → 6/6 → 首席策略官汇总」；并发完成时串行写状态，避免进度回退 | ✅ |
| Token 预算 | 推理模型思考吃 token：`LLM_MAX_TOKENS` 2048 → **4096**；财报上下文只取近 3 期 | ✅ |
| 缓存版本 | `PROMPT_VERSION` 升到 `multi_agent_decision.v2`，并入分析师提示词 digest，旧缓存自动失效 | ✅ |
| 配置 | 新增 `LLM_ANALYST_TIMEOUT_SECONDS`（150）与 `LLM_ANALYST_CONCURRENCY`（3）；`LLM_JOB_TIMEOUT_SECONDS` 420 → 600 | ✅ |

**验收**
- 真实 SenseNova（`sensenova-6.8-flash-lite`）跑 600519：六位分析师全部 `engine=llm`，首席决策 `decision_source=llm`（持有，置信度 55）
- 首次真实跑暴露两个问题并已修复：财报 `date` 无法 JSON 序列化；推理模型 2048 token 被思考吃光导致空响应
- 后端 **79 passed**（新增 LLM 分析师、单点回退、进度、日期序列化用例）；前端 `npm run build` 通过

**说明**：当次东财资金流/指数接口被临时限流，资金面数据缺失，LLM 如实写入缺口并按中性处理，说明降级链路正常。

### 4.23 团队讨论时间线（2026-10-21）

**背景**：六份分析师报告与首席决策之间缺少交叉回应，报告读起来像六份并列结论；P4 需要把“讨论”补进链路。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 讨论生成 | 一次 LLM 圆桌整理 4-6 轮发言，`stance` 限定 同意/补充/质疑，必须点名回应另一位分析师；输入只含六份简报、价位与数据缺口 | ✅ |
| 规则兜底 | LLM 空响应/超时/格式异常时，按评分最高与最低分析师生成 2-3 轮时间线，`source=rule`，报告不中断 | ✅ |
| 决策联动 | 讨论纪要写入首席决策 context；提示词要求吸收收敛结论，并在 consensus/dissent 中体现保留分歧 | ✅ |
| 展示 | 新增 `DiscussionTimeline.vue`（card/flat 两种形态），报告页放在六位分析师之后，个股 AI 卡展示紧凑版；旧报告无 `discussion` 自动隐藏 | ✅ |
| 版本与进度 | `PROMPT_VERSION` 升到 v3 并入 discussion digest；job 新增「团队讨论中」阶段 | ✅ |

**验收**
- 真实 SenseNova 用同一份六分析师输入在 4096 / 8192 token 预算下均返回 6 轮讨论，分析师名字与 `target` 匹配成功
- 真实 600519：讨论首次空响应自动回退规则版（2 轮），六位分析师与首席决策仍为 `llm`，报告正常完成
- 后端 **82 passed**（新增 LLM 讨论入报告/决策、失败回退用例）；前端 `npm run build` 通过

**说明**：推理模型偶尔会因思考耗尽 token 返回空内容，讨论已做规则兜底；若频繁出现可提高 `LLM_MAX_TOKENS`。

### 4.24 SSE 实时进度（2026-10-21）

**背景**：前端每 2 秒轮询一次 job，阶段间隔长时“已等待”会停住，六位分析师逐位完成也看不到即时反馈。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 事件流接口 | `GET /api/v1/ai/jobs/{job_id}/events`，`text/event-stream`；事件 `snapshot → phase* → done`，15s 心跳，终态后关闭 | ✅ |
| 推送机制 | `_save_state` 每次落 Redis 后 publish 到 `ai:job:events:{job_id}`，与轮询共用同一状态源 | ✅ |
| 竞态处理 | 先订阅再读快照，避免任务恰好在两次请求间完成而丢 `done`；快照即终态则立即发送 `done` | ✅ |
| 前端读取 | `fetch + ReadableStream` 手动解析 SSE，带 Bearer 头（不把 token 放进 URL）；`AbortController` 随切股/卸载断开 | ✅ |
| 降级 | 连接失败、代理缓冲或流意外结束 → 自动回退 2s 轮询，任务继续可用 | ✅ |
| 计时 | 前端新增 1s 本地计时，阶段事件之间“已等待 N 秒”持续增长，收到事件时以服务端为准 | ✅ |

**验收**
- 新增 ASGI SSE 用例：`snapshot → phase → done` 顺序与终态关闭均通过；后端 **83 passed**
- 前端 `npm run build`（vue-tsc + vite）通过；未新增依赖
- 真实 LLM 任务仍由同一 job 状态机驱动，轮询接口保持不变

**说明**：生产环境 Nginx 需对该路径关闭 `proxy_buffering`（`X-Accel-Buffering: no` 已返回），否则事件会被缓冲成一次性输出。

### 4.25 ARQ worker（2026-10-21）

**背景**：任务此前用进程内 asyncio task 执行，API 重启即中断，只能靠 stale 检测标记失败；P4 需要把执行与 API 进程解耦。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| Worker | 新增 `app/worker.py`：`WorkerSettings` 注册 `run_ai_job`，复用现有 job 状态机；`max_jobs=2`、`max_tries=1`（避免失败重试重复扣费） |
| 入队 | 默认 `AI_JOB_EXECUTION=arq`，`start_ai_job` 通过 ARQ pool `enqueue_job(..., _job_id=job_id)`，job_id 与状态键一致 |
| 心跳 | 每 30 秒写入 `ai:worker:alive`（TTL 120s）；API 无心跳时新任务直接 503「分析队列未启动」，不会卡在排队中 |
| 入队失败 | 删除 job 状态与 active key 后返回 503，避免用户重试被旧 active 记录挡住 |
| 兼容 | 保留 `AI_JOB_EXECUTION=inline` 供本地调试；FastAPI lifespan 关闭 ARQ 连接池；worker 退出时释放 HTTP/DB/Redis 资源 |
| 依赖 | `arq 0.28`（依赖 redis 5.3.x，已随 uv.lock 锁定） |

**验收**
- 真实启动 `uv run arq app.worker.WorkerSettings`：加载 `run_ai_job` 与 `worker_heartbeat` 两个函数，心跳 TTL 116s
- 通过 `start_ai_job` 入队 600519：worker 消费并落状态 `succeeded（命中 6h 缓存）`，ARQ 日志 `j_complete=3 j_failed=0`
- 后端 **88 passed**（新增心跳可见性、无 worker 拒绝、入队参数、inline 回退、worker 入口 5 个用例）
- 文档与命令：`npm run worker`、`AI_JOB_EXECUTION` / `AI_WORKER_MAX_JOBS` 写入 `.env.example`

**说明**：API 重启不再中断分析；worker 优雅重启会等待在跑任务结束。若 worker 硬崩溃，运行中任务仍由 stale 检测标记失败，用户重新发起即可。

### 4.26 开发期额度覆盖（2026-10-21）

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 配置 | 新增 `AI_DAILY_QUOTA_OVERRIDE`：`>0` 时所有用户统一按该额度计算，`0` 表示使用用户表 `daily_analysis_quota` | ✅ |
| 生效范围 | `GET /ai/config`、`POST /stocks/{symbol}/ai-analysis`（job 的额度检查与报告 `quota_limit` 均使用同一值） | ✅ |
| 当前设置 | 开发期 `.env` 设 `9999`；`.env.example` 保持 `0` | ✅ |

**验收**：`settings.effective_daily_quota(5)` 返回 9999；后端 **89 passed**（新增额度覆盖用例）；前端无需改动。

### 4.27 报告详情返回来源（2026-10-21）

**问题**：报告详情顶部的「返回」固定指向个股页，从首页「最近分析」或历史列表进入后，返回会跳到 `/stock/:symbol`，而不是来时的页面。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 来源标记 | 进入报告时带 `?from=dashboard|reports|stock`；个股入口额外带 `symbol`，避免详情加载完成前返回失效 | ✅ |
| 返回目标 | 工作台 → `/`；历史列表 → `/reports`；个股 → `/stock/:symbol`（默认兼容旧链接） | ✅ |
| 入口统一 | `ReportListItem` 新增 `from` 参数；首页、历史页、个股 AI 卡与历史列表全部传入来源 | ✅ |

**验收**：前端 `npm run build` 通过；从首页「最近分析」进入后顶部显示「返回工作台」。

### 4.28 重新 AI 诊断（2026-10-21）

**问题**：同股同交易日命中 6 小时缓存后，个股页只能看到旧报告，用户想重新诊断没有入口。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 跳过缓存 | `POST /stocks/{symbol}/ai-analysis?force=true` → job → ARQ worker → `generate_ai_analysis(force=True)`，跳过 job 级与报告级两次缓存读取，生成后仍写回新缓存 | ✅ |
| 前端入口 | 个股页 AI 卡右上角，「查看完整报告」同排的描边按钮（刷新图标 + 「重新诊断」）；颜色用 `ink-2` 文字 + `line-strong` 描边，hover 加深，不再是灰色小字；保留旧报告直到新结果返回，执行中禁用并显示「诊断中…」 | ✅ |
| 进度 | 复用现有 SSE/轮询链路，重新诊断与首次分析共用同一套状态机与额度（消耗 1 次） | ✅ |
| 兼容 | ARQ `run_ai_job` 增加可选 `force`（默认 False），旧队列任务不受影响 | ✅ |

**验收**：后端 **90 passed**（新增 force 绕过缓存用例）；前端构建通过；worker 已重启并加载新签名。

### 4.29 自选股（2026-10-21）

**背景**：首页只有查询与最近分析，用户无法固定关注列表；P3/P6 的自选股一直缺位。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 数据表 | `watchlist_items(id, user_id, symbol, created_at)`，唯一约束 `(user_id, symbol)`，用户删除级联；迁移 `b2c3d4e5f6a7` | ✅ |
| 接口 | `GET /watchlist`、`POST /watchlist`（幂等加入，上限 50）、`DELETE /watchlist/{symbol}`、`GET /watchlist/{symbol}` 查询是否已自选 | ✅ |
| 列表行情 | 并发拉取报价；单只失败时保留名称、价格留空不阻塞整表；名称以 `stocks` 表为准 | ✅ |
| 个股页 | 「加入自选 / 已自选」切换，乐观更新，失败回滚并提示 | ✅ |
| 页面 | 自选股独立页 `/watchlist`：名称/代码/现价/涨跌幅/来源与延迟标记；删除立即从列表移除（不重新拉取）；骨架屏与空态（4.30 起从首页移出为独立路由） | ✅ |

**验收**：后端 **92 passed**（新增自选增删查、行情降级、用户隔离与接口用例）；前端 `npm run build` 通过；迁移已执行，重启后端后 `/api/v1/watchlist` 返回 401（路由已加载）。

**说明**：自选列表行情不做额外缓存，直接复用行情层 3 秒报价缓存；数量上限 50 只，避免一次打开首页打出过多上游请求。

### 4.30 顶部导航与板块路由拆分（2026-10-21）

**背景**：所有功能堆在首页，顶部只有 logo 与用户菜单；参考产品的做法用顶部居中导航区分板块。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 导航栏 | 顶部居中三个板块：工作台 `/`、自选股 `/watchlist`、历史报告 `/reports`；选中项深色加粗 + 底部 0.5px 横线 | ✅ |
| 响应式 | 桌面居中一行；移动端在顶栏下方新增可横向滚动的第二行导航，保留用户菜单 | ✅ |
| 路由拆分 | 新增 `/watchlist` 页面，自选股从首页移出；首页保留查询、概览与最近分析，并在标题右侧提供「自选股 →」「全部历史报告 →」入口 | ✅ |

**验收**：前端 `npm run build` 通过；`/watchlist` 需登录并带 4.29 的自选增删能力。

### 4.31 自选股增强：最新结论、持仓信息与批量分析（2026-10-21）

**背景**：自选股只有行情，看不到 AI 结论；也无法记录成本/备注，组合无法一次性分析。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 最新 AI 结论 | `GET /watchlist` 按 `DISTINCT ON (symbol)` 关联每股最新 `analysis_reports`，返回 `latest{report_id, rating, confidence, decision_source, created_at}`；卡片展示评级/置信度/时间，并提供「查看报告 →」（`?from=watchlist`） | ✅ |
| 备注与持仓 | `watchlist_items` 新增 `note(120)/cost_price/quantity`（迁移 `c3d4e5f6a7b8`）；`POST /watchlist` 支持初始填写，新增 `PATCH /watchlist/{symbol}` 只更新传入字段，显式 `null` 清空成本/数量 | ✅ |
| 批量分析 | `POST /watchlist/batch-analysis`（1–20 只，可选 `force`）逐只复用现有 `start_ai_job`，单只失败只影响该行；前端支持勾选/全选、提交后按 job 轮询，行内显示排队/阶段/完成/失败 | ✅ |
| 前端结构 | 抽出 `components/watchlist/WatchlistCard.vue`：卡片包含选择、行情、最新结论、备注/成本/数量行内编辑与任务状态；页面只负责列表、选择与轮询 | ✅ |

**验收**：后端 **93 passed**（新增 PATCH 更新/清空、批量提交逐只成功与非法代码失败用例）；前端 `npm run build` 通过；迁移已执行，重启后 API 已包含 `PATCH /watchlist/{symbol}` 与 `POST /watchlist/batch-analysis`。

### 4.32 批量分析状态同步与保存修复（2026-10-21）

**背景**：自选卡片编辑持仓后点保存无反应；批量分析状态在刷新后丢失；从自选进入个股详情时看不到正在运行的分析。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 保存修复 | `<input type="number">` 的 `v-model` 运行时是 number，保存前统一 `String(...)` 再 `trim()`，避免抛 `TypeError` 导致请求未发出 | ✅ |
| 刷新恢复 | 待轮询的 `job_id` 按用户写入 `sessionStorage`，刷新后自动恢复并继续轮询；完成、失败、移出自选或切换账号自动清理 | ✅ |
| 详情同步 | 新增 `GET /ai/jobs/active?symbol=`，个股详情页加载时接上该股票正在运行的任务（SSE/轮询），显示阶段与已等待秒数；无活跃任务返回 `null` | ✅ |
| 任务去重 | `start_ai_job` 统一归一化股票代码，保证活跃任务 key 一致；运行中重复提交返回原任务 | ✅ |

**验收**：后端 **96 passed**（新增活跃任务查询、路由优先级与非法代码用例）；前端 `npm run build` 通过；实测 `000009` 运行中的批量任务可在个股详情页接续显示「首席策略官汇总六份报告」阶段。

### 4.33 自选股 AI 决策：组合诊断与持仓联动（2026-10-21）

**背景**：自选股只有行情与最新结论，成本/数量仅展示，AI 决策不结合持仓，用户认为价值不足。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 持仓上下文 | 分析任务读取自选股的成本/数量/备注，生成 `user_position` 快照（成本、市值、浮盈亏）并注入首席策略官提示词 | ✅ |
| 持仓建议 | 决策新增 `position_action`（加仓/建仓/持有/减仓/清仓/观望）与 `position_advice`；规则兜底同样按成本与浮盈亏给出建议；报告详情页与个股页展示「我的持仓建议」 | ✅ |
| 缓存隔离 | 报告缓存改为按「用户 + 持仓摘要」隔离，避免跨用户或持仓变化后复用旧建议；提示词版本升至 `v4` | ✅ |
| 组合诊断 | 新增 `POST /watchlist/portfolio-analysis`：汇总全部自选（行情、成本、数量、浮盈亏、最新评级/摘要），一次 LLM 输出健康度、集中度风险、仓位建议与逐只动作；每次消耗 1 次额度 | ✅ |
| 自选页 | 顶部「AI 组合诊断」卡片；每张自选卡片展示 AI 建议动作、最新摘要、成本/数量与浮动盈亏 | ✅ |

**验收**：后端 **100 passed**；前端 `npm run build` 通过；实测组合诊断返回健康度 20、集中度 100%、`000009` 建议「清仓」，额度 8 / 9999。

### 4.34 选股模块与主力选股（2026-10-21）

**背景**：参考项目有独立的「选股板块」（主力选股、低价擒牛、小市值、净利增长、低估值），我们此前只有单股分析与自选，没有选股模块。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 模块骨架 | 新增 `/screener` 页面与顶部导航「选股」；策略切换，未实现策略标「即将推出」 | ✅ |
| 主力选股 | 新浪个股资金流排行（按超大单净额 `r0_net` 排序）扫描前 300 只，过滤 ST / 创业板 / 科创板 / 北交所与涨幅超过上限的标的，取前 N 只 | ✅ |
| 缓存 | 排行结果写入 Redis `mkt:screener:fundflow_rank`，TTL 60 秒，避免连续点击打出过多请求 | ✅ |
| 数据源 | 东财 push2 当前被临时限流，主力排行改用新浪公开接口；东财恢复后可并列降级链 | ✅ |
| 前端联动 | 结果列表展示现价/涨跌幅/主力净额/净占比；支持一键加入自选、进入详情、勾选批量 AI 分析 | ✅ |
| 复用 | 抽取 `useAIBatch` 组合式函数，自选页与选股页共用批量提交、轮询、失败重试与刷新恢复逻辑 | ✅ |

**验收**：后端 **106 passed**（新增排行解析、过滤规则、策略列表与接口错误映射用例）；前端 `npm run build` 通过；实测接口扫描 300 只、命中 150 只，返回前 5 只候选。

### 4.35 低价擒牛策略（2026-10-21）

**背景**：对齐参考项目选股板块的第二个策略：低价 + 高净利增长，按成交额由小到大排名。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 数据源 | 东财 datacenter 业绩报表 `RPT_LICO_FN_CPD`（最新报告期、`SJLTZ` 净利同比、`YSTZ` 营收同比）+ 腾讯批量报价（50 只/批） | ✅ |
| 筛选规则 | 股价 < 上限（默认 10 元）、净利同比 ≥ 下限（默认 100%）、剔除 ST / 创业板 / 科创板 / 北交所，按成交额升序取前 N | ✅ |
| 接口 | `POST /screener/low-price-bull`，返回报告期、扫描数、候选数与逐只净利/营收增速 | ✅ |
| 前端 | 选股页拆出 `MainForcePanel` / `LowPriceBullPanel` / `ScreenerResults`，策略切换；结果展示净利同比、营收同比、报告期，并复用加入自选、详情与批量分析 | ✅ |

**验收**：后端 **110 passed**；前端 `npm run build` 通过；实测报告期 2026-09-30、业绩记录 46、命中 6、返回 5 只，首条宁波海运 3.29 元 / 净利同比 +135.4%。

### 4.36 小市值策略（2026-10-21）

**背景**：对齐参考项目选股板块的第三个策略：小盘 + 营收/净利双增长，按总市值升序。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 数据源 | 复用东财业绩报表（`SJLTZ` / `YSTZ`，服务端同时过滤营收增速）+ 腾讯批量报价（总市值字段） | ✅ |
| 筛选规则 | 总市值 ≤ 上限（默认 50 亿）、营收同比 ≥ 10%、净利同比 ≥ 100%，剔除 ST / 创业板 / 科创板 / 北交所，按总市值升序取前 N；服务层再校验一次增速阈值 | ✅ |
| 接口 | `POST /screener/small-cap`，返回报告期、业绩记录数、候选数与逐只总市值/净利/营收增速 | ✅ |
| 前端 | 新增 `SmallCapPanel.vue`，表单可调市值上限、净利/营收增速下限与排除项；结果展示总市值、净利同比、营收同比、报告期，复用加入自选/详情/批量分析 | ✅ |

**验收**：后端 **112 passed**；前端 `npm run build` 通过；实测报告期 2026-09-30、业绩记录 38、命中 3、返回 3 只，首条昂立教育 27.4 亿 / 净利同比 +117.2% / 营收同比 +10.2%。

### 4.37 主力选股 AI 深度分析（2026-10-22）

**背景**：对齐参考项目 `main_force_analysis.py` 的完整链路：不是逐只分析，而是对候选池做整体分析——资金流向 / 行业板块 / 财务基本面三位分析师先出报告，再由资深研究员综合精选 3-5 只。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 数据补齐 | 候选池补腾讯 PE/PB/总市值 + 东财最新报告期行业、营收/净利增速，组成分析表格 | ✅ |
| 三位分析师 | `llm/main_force_prompts.py` + 并发调用，分别输出资金面 / 行业板块 / 基本面整体报告，单维度失败不影响其他维度 | ✅ |
| 最终精选 | 资深研究员综合三份报告输出 JSON：rank / symbol / name / reasons / highlights / risks / position / investment_period；编造代码会被过滤，不足时按资金面兜底 | ✅ |
| 接口 | `POST /screener/main-force/analysis`，复用主力筛选参数 + `final_n`（3-10），消耗 1 次 AI 额度 | ✅ |
| 提示词压缩 | 候选池上限 40 只，JSON 改为紧凑表格，分析师报告限制 700 字；单次调用 120s 上限，避免整体超过前端等待时间 | ✅ |
| 推理模型适配 | `sensenova-6.8-flash-lite` 的思考过程同样消耗 completion token（实测 4000 token 内正文为空），分析调用放宽到 6000 token，并在 `finish_reason=length` 时给出明确错误 | ✅ |
| 前端 | 主力选股结果下方新增「AI 深度分析」卡片：精选数量、开始/重新分析、三份分析师报告与精选标的（仓位、周期、理由、亮点、风险） | ✅ |

**验收**：后端 **115 passed**；前端 `npm run build` 通过；服务层实测（40 只候选、精选 3 只）耗时 99.5 秒，返回工业富联 / 中孚实业 / 星网锐捷；HTTP 接口实测 200、耗时 138.9 秒，返回国轩高科 / 移远通信 / 龙蟠科技，理由均引用了实际资金、行业与财务数据。

### 4.38 选股 AI 任务化与记录落库（2026-10-22）

**背景**：同步等待三分析师 + 精选的 HTTP 请求会超时，刷新丢失进度；规则候选在 AI 不足时自动补位，产生「未经 AI 选择的垃圾结果」。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 规则补位移除 | AI 精选几只展示几只，不足不凑数（提示词同步约束）；精选失败直接报错，不再降级为规则结果 | ✅ |
| 后台任务化 | `screener_job_service` + ARQ `run_screener_job`：状态机（排队/运行/成功/失败）、阶段进度、活跃任务续跑、失败信息落 Redis | ✅ |
| 记录落库 | 新表 `screener_records`（user/strategy/filters/result JSON），迁移 `d4e5f6a7b8c9`；每次 AI 选股自动保存，响应带 `record_id` | ✅ |
| 历史与详情 | `GET /screener/records`、`/records/{id}` 通用接口；前端历史列表 + 独立详情抽屉（不覆盖主视图），刷新自动恢复最近一次结果与筛选条件 | ✅ |
| 最终精选重试 | 超时 / JSON 解析失败各重试一次（180s 上限），仍失败返回明确错误 | ✅ |
| 主力面板改版 | 移除「先筛选再可选 AI」两段式，单一「开始 AI 选股」入口；候选规则只用于圈定候选池 | ✅ |

**验收**：后端 **135 passed**（含选股记录、任务状态机、AI 接口→落库→读回集成用例）；浏览器实测刷新续跑、结果恢复、历史详情均正常。

### 4.39 五策略全部 AI 化（2026-10-22）

**背景**：低价擒牛、小市值、净利增长、低估值在参考项目中均为纯规则列表（无 AI）；按产品方向统一升级为「规则圈候选 → 三分析师 → 资深研究员精选」。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 策略泛化 | `_run_ai_selection` 共用 runner：三分析师（按策略切换任务提示词）+ 资深研究员 + 额度/重试/阶段回调；主力选股同链路 | ✅ |
| 低价寻宝 | 东财业绩 + 腾讯报价候选（成交额升序），资金与流动性/行业/业绩成长分析师 | ✅ |
| 小盘精选 | 市值/营收/净利规则候选（市值升序），资金与流动性/行业/成长与估值分析师 | ✅ |
| 业绩高增 | 净利同比 ≥ 阈值候选（成交额升序），资金与流动性/行业/成长质量分析师；重点识别低基数与非经常性损益 | ✅ |
| 价值洼地 | 新增东财估值快照（服务端 PE/PB 过滤）+ 分红计划（近 12 个月已实施分红算股息率）+ 财务负债率，流通市值升序候选；估值质量分析师重点识别价值陷阱 | ✅ |
| 任务与记录 | 各策略独立任务接口、活跃任务隔离、记录按 strategy 落库，历史/详情按策略隔离 | ✅ |
| 前端 | 抽取 `useScreenerAI` / `ScreenerAIResult` / `ScreenerHistory` / `ScreenerJobLoading` 共用组件，五面板同构 | ✅ |

**验收**：后端 **135 passed**；真实链路实测：低价寻宝 6 候选 → 精选 3 只、业绩高增 40 候选 → 精选 5 只、价值洼地 21 候选 → 精选 5 只（首跑 JSON 解析失败由重试兜底）；五条策略各有一条真实记录落库。

### 4.40 策略更名与首页调整（2026-10-22）

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 策略更名 | 主力选股→主力追踪、低价擒牛→低价寻宝、小市值→小盘精选、净利增长→业绩高增、低估值→价值洼地；后端策略列表 / 前端兜底 / 面板空状态 / 历史详情同步 | ✅ |
| 导航更名 | 顶部导航「工作台」→「首页」，页面标题、浏览器标题、各处「返回工作台」同步 | ✅ |
| 模型名移除 | 界面不再展示模型名 / prompt 版本（工作台、报告列表、报告详情、个股页、选股、自选诊断）；保留接口字段 | ✅ |
| Select 组件 | 自研下拉 `ui/Select.vue`（键盘操作 / ARIA / 主题样式），替换原生 select | ✅ |

### 4.41 个人中心弹窗（2026-10-22）

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 全局弹窗 | AppShell 挂载 `AccountCenterModal`，头像菜单「个人中心」打开；左侧账户/安全导航，右侧内容；Esc/遮罩/按钮关闭，滚动锁定，路由变化自动关闭 | ✅ |
| 个人概览 | 头像/昵称/邮箱/角色/状态/注册时间；今日额度进度、近期报告数、自选股数；快捷入口（AI 选股/自选股/历史报告） | ✅ |
| 资料设置 | `PATCH /auth/me` 修改昵称（2–20 字符），保存后全站昵称同步；邮箱只读（登录账号） | ✅ |
| 修改密码 | `POST /auth/password/change`：校验当前密码、密码规则、新旧不同；成功后吊销全部会话并自动退出重登 | ✅ |
| 错误文案 | 选股任务 LLM/数据源失败文案改为用户可读（「AI 服务暂不可用」等），技术细节进日志 | ✅ |

**验收**：后端 **135 passed**（新增编辑昵称、改密端到端用例：错密码拒绝、改密后旧密码失效）；前端 typecheck / build 通过；浏览器实测资料保存、密码表单校验、弹窗开关与数据加载均正常。

### 4.42 个股页与报告体验增强（2026-10-22）

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| K 线指标叠加 | 引入 `klinecharts@9.8.12` 替换自研 MiniKline：MA + BOLL 主图、VOL + MACD 副图，十字光标/缩放，主题色经 `utils/theme.ts` 读取设计 token；K 线加载 120 根；周期/复权切换沿用原逻辑 | ✅ |
| 个股资金流 | `GET /stocks/{symbol}/fund-flow`：东财为主（30 天、300s 缓存），东财按 IP 临时断连时自动降级新浪资金流（仅主力净流入/超大单，页面注明备用源并隐藏空分档）；新增 `FundFlowChart`（SVG 零轴对称柱）与 `FundFlowSection`（指标切换、最新净额与主力净占比、骨架/空态/重试） | ✅ |
| 个股资讯 | 新增东财公告 Provider + 东财新闻搜索 Provider（JSONP，免密钥），`GET /stocks/{symbol}/news` 并发取数、10 分钟缓存、单源失败 `partial=true`；`CompanyNewsPanel` 提供公告/新闻/AI 资讯三个页签 | ✅ |
| 元宝按需检索 | `POST /stocks/{symbol}/news/ai-search`：仅手动按钮触发，结果缓存 6 小时，30 秒冷却；不改变 AI 分析主链路的一次检索策略 | ✅ |
| 6 维雷达 | 自研 `AnalystRadar`（SVG、0–100、缺失维度按 0 并提示），报告页新增「评分概览」卡 | ✅ |
| 报告对比 | 新增 `/reports/compare?ids=a,b`：较新/较早并排展示评级、决策、六维雷达与 delta、关键价位、持仓建议、理由/风险、讨论轮次；详情页「对比上一次」自动找同股上一份，历史页支持勾选两份同股报告（跨股票自动重置） | ✅ |
| PDF 导出 | 报告页「导出 PDF」：`html2canvas-pro@2.5.2` + `jspdf@4`（动态导入，Tailwind 4 的 oklch/color-mix 可渲染），A4 分页、10mm 边距、`data-pdf-hide` 隐藏按钮；文件名 `智盈AI_{名称}_{代码}_{日期}.pdf` | ✅ |
| 组件复用 | 抽取 `utils/theme.ts`、`utils/pdf.ts`、`utils/report.ts::analystScoreTone/decisionLevels`；`ReportListItem` 支持选择模式；删除不再使用的 `MiniKline.vue` | ✅ |

**验收**
- 后端 **153 passed**（新增资讯解析/缓存/单源降级/双源失败、资金流解析与东财→新浪降级、资金流接口、元宝冷却用例）；前端 typecheck 与 `npm run build` 通过
- 真实数据源冒烟（未消耗 LLM/元宝）：东财公告 5 条、东财新闻 5 条均解析成功，公告链接与发布时间正确
- 东财资金流在 2026-10-22 16:30 前后持续 `Server disconnected`；实测已自动降级新浪资金流并返回 30 天数据（最新 2026-10-22，主力净流入 5.31 亿），页面显示「已切换新浪备用源」

### 4.43 体验修复与数据源故障排查（2026-10-22）

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 重新诊断统一进度 | 新增共用组件 `AIJobProgress.vue`（加载动画 + 当前阶段 + 已等待秒数），个股页首次分析与重新诊断分支均使用；重新诊断失败的错误提示显示在报告区，避免无反馈 | ✅ |
| 雷达图标签修复 | `AnalystRadar.vue` 构造轴数据时坐标对象覆盖了字符串 `label`，轴标签渲染成 `{'x':..,'y':..}`；坐标改名 `labelPos` 并 `toFixed(1)` 消除浮点噪声；报告页与对比页两处共用一并修复 | ✅ |
| 耗时跳秒修复 | 选股面板「已用时」直接绑定 2s 轮询的服务端值导致 0→2→4 跳秒；`useScreenerAI` 新增本地 1s 计时 `displayElapsed`（轮询返回时 `Math.max` 单调校准、新任务归零、恢复任务续上），五面板统一改绑 | ✅ |
| 详情页计时校准 | `applyAIJob` 收到推送时直接覆盖本地计时可能轻微回跳，改为同样的 `Math.max` 单调校准（重新提交时先归零，不残留旧值） | ✅ |
| MARKET_UNAVAILABLE 排查 | 选股任务 2s 内失败的定位过程：curl 直连东财/新浪均正常、后端 venv 直跑取数正常 → 锁定 worker 进程环境问题（worker 自上午未重启，启动终端的代理环境变量被 httpx `trust_env` 继承导致出站全部失败）；重启 worker 后恢复 | ✅ |
| 日志落盘 | `core/logging.py` 增加滚动文件输出（stdout 保留）：API 写 `backend/logs/app.log`、worker 写 `worker.log`（分文件避免 Windows 多进程轮转冲突），默认 5MB × 5 份，`LOG_DIR`/`LOG_MAX_BYTES`/`LOG_BACKUP_COUNT` 可配，UTF-8 编码；`.env.example` 同步 | ✅ |
| 定时选股 + 定时分析自选股 | 新表 `user_automation_settings`（迁移 `e5f6a7b8c9d0`）：每用户「每日定时选股」「每日定时分析自选股」开关 + 每策略自定义筛选参数（复用五个 `*AnalysisRequest` 校验）；`GET/PUT /automation/settings`；`daily_automation_service` 由 ARQ cron（默认 17:35，`AUTOMATION_CRON_HOUR/MINUTE` 可配）触发：LLM 检查 → 日期防重键 → 逐用户入队（复用 `start_screener_job`/`start_ai_job`），额度耗尽跳过、单用户失败隔离、时间守卫防提前执行；前端个人中心新增「定时任务」设置区（配置驱动共用表单） | ✅（见 4.44） |

**经验记录**
- `providers/http.py` 的 `trust_env=True` 会继承启动终端的代理变量：worker 必须从干净环境启动，或显式设置 `EGRESS_PROXY_URL`
- 日志已落盘（`backend/logs/app.log` / `worker.log`），排查数据源/worker 故障直接看文件，不必再翻启动终端
- `--reload` 热重载在本机不可靠：backend/logs 日志高频写入 + 成批新增文件会让 watchfiles 静默丢事件（曾导致 API 长时间停留在旧代码）；启动命令已加 `--reload-dir app` 限定监听源码目录（package.json 与 README 同步），改 `.env`/迁移不会触发热重载；成批改动后务必重启 API 确认生效

### 4.44 定时选股与定时分析自选股（2026-10-23）

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 数据模型 | 新表 `user_automation_settings`（user 唯一、`screener_enabled`/`analysis_enabled` 开关、`strategy_settings` JSONB 存每策略参数），迁移 `e5f6a7b8c9d0` | ✅ |
| 设置接口 | `GET/PUT /api/v1/automation/settings`（登录保护）；filters 用五个 `*AnalysisRequest` 校验并补全默认值，非法参数 422；`errors.validation` 工厂 | ✅ |
| 调度器 | `daily_automation_service.run_daily_automation_task`：LLM 检查 → 计划时间守卫（防 worker 重启提前跑）→ `automation:ran:{date}` NX 防重 → 查 `status=active` 且开启开关的用户 → 逐用户入队；选股复用 `start_screener_job`（参数从设置反序列化），分析复用 `start_ai_job(force=False)` 并按剩余额度封顶；`QuotaExceededError` 跳过、`AIWorkerUnavailableError` 中止、单用户异常隔离 | ✅ |
| Worker | `run_daily_automation` 注册进 functions 与 cron（`AUTOMATION_CRON_HOUR=17`/`AUTOMATION_CRON_MINUTE=35`，`run_at_startup=True` 补跑） | ✅ |
| 前端 | 个人中心新增「定时任务」视图：两个总开关（样式化 toggle）、五策略多选 + 配置驱动参数表单（`automationSpecs.ts` 字段描述 + `mergeFilters` 默认值合并），保存一次性 PUT、无刷新回显 | ✅ |
| 测试 | `test_automation_settings.py`（默认回显/读写/非法 filters/未知策略/用户隔离）+ `test_daily_automation.py`（时间守卫/防重/LLM 未配置跳过/入队参数/额度跳过/单用户失败隔离）；后端 **162 passed** | ✅ |

**说明**：自动分析按剩余额度封顶入队（额度检查在缓存命中之前，超出的任务会直接失败，因此不入队）；防重与执行时间均为 per-user 粒度，手动重跑可删 `automation:ran:{日期}:{用户}:{任务}` 键；`AUTOMATION_CRON_HOUR/MINUTE` 仅作为新用户的默认执行时间。

**2026-10-23 增强——用户自定义执行时间**：`user_automation_settings` 新增 4 列（迁移 `f6a7b8c9d0e1`），定时选股与定时分析各自可设执行时间（`screener_run_hour/minute`、`analysis_run_hour/minute`，24 小时制）；调度器从「每日固定 17:35 触发一次 + 全局防重」改为「每 5 分钟触发 + per-user 时间判断与 per-user 防重键（`automation:ran:{date}:{user}:{task}`）」，用户改时间保存后即时生效，无需重启 worker；实际执行可能比设定时间晚至多 5 分钟；前端两个任务卡片各带时间选择器；`AUTOMATION_CRON_HOUR/MINUTE` 降级为新用户默认值。

### 4.45 组合诊断历史留存（2026-10-23）

**背景**：组合诊断此前只在内存中展示，刷新即丢；历史报告页只有个股报告。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 数据模型 | 新表 `portfolio_diagnoses`（`user_id`、`health_score`、`position_count`、`summary`、`model`、`report` JSONB、`created_at`），迁移 `7a1b2c3d4e5f` | ✅ |
| 保存与查询 | 诊断成功即落库；新增 `GET /watchlist/portfolio-analysis/latest`、`/history`、`/history/{id}`，按用户隔离 | ✅ |
| 自选页 | 加载时恢复最近一次诊断（不自动调用 LLM）；有记录时显示「历史诊断」入口 | ✅ |
| 历史报告页 | 新增「组合诊断」页签：健康度、摘要、完整时间、持仓数；点击进入独立详情页 `/reports/portfolio/:id`，标注为历史快照 | ✅ |
| 测试 | 落库/列表/详情/最近一次/用户隔离与接口用例；后端 **164 passed**；前端 `npm run build` 通过 | ✅ |

### 4.46 主力追踪口径对齐（2026-10-23）

**背景**：参考项目主力选股用问财「3/6/12 个月资金净流入前 100 + 市值区间 + 区间涨幅 30%」；我们此前是新浪当日超大单前 300、涨幅 7%、候选 40。用户选择先按东财 3/5/10 日区间对齐。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 数据源 | 东财 push2 编号镜像 + `ut` token，提供今日/3 日/5 日/10 日排行（f62/f267/f164/f174）；默认近 10 日；最多 4 页 400 行，页间间隔 0.3s | ✅ |
| 缓存与限流 | 结果缓存 10 分钟；另存 24h 过期副本，东财限流时回退旧数据；今日窗口额外回退新浪 | ✅ |
| 筛选口径 | 总市值 50–5000 亿、区间涨幅 ≤30%、排除 ST/创业板/科创板/北交所 → 按区间净流入排序取前 100 作为 AI 候选 | ✅ |
| 提示词 | 摘要与表格标注统计区间，输出「区间涨幅 / 区间主力净额」，避免与当日口径混淆 | ✅ |
| 前端 | 选股面板新增「统计区间 + 总市值上下限」，区间涨幅默认 30%；定时任务设置支持区间下拉；历史记录展示区间与市值条件 | ✅ |
| 测试 | 东财三种区间字段解析、市值/涨幅筛选、区间参数用例；后端 **166 passed**；前端 `npm run build` 通过 | ✅ |

**说明**：参考项目的 3/6/12 个月区间只有问财能提供（需 Cookie 且易 403），本次未接入；东财免费直连源最长 10 日（同花顺 20 日需登录 Cookie）。东财 push2 对共享出口限流较敏感，开发机实测出现过临时断连，已用长缓存 + 过期兜底缓解，页面提示为「行情/资金流数据暂不可用，请稍后重试」。候选从 40 增至 100，三位分析师的输入 token 约为原来的 2.5 倍。

### 4.47 后台管理 P0（2026-10-24）

**背景**：P7 管理后台此前完全未开始；用户侧已有报告/选股/组合诊断/定时任务，但缺少用户额度运营、AI 成本与任务历史、管理员操作审计。第一版定位为单管理员内部运营与排障台，配置仍走 `.env`。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 权限 | 复用 `require_admin`；`/api/v1/admin/*` 路由级校验；前端 `/app/admin` 增加 `requiresAdmin` 守卫；用户下拉仅管理员显示入口 | ✅ |
| 管理员 CLI | `backend/app/scripts/create_admin.py`：`--promote` 提升已有账号、`--demote` 取消；不能移除最后一个 active 管理员 | ✅ |
| 用户与额度 | 列表（搜索/状态/角色/额度区间/分页）、详情（额度/用量/报告/自选/定时任务/最近会话）、调整额度、封禁/解封、重置今日额度、强制下线 | ✅ |
| 审计 | `admin_audit_logs` 记录管理员写操作、before/after、IP/UA；后台审计页可筛选与展开；只追加不删除 | ✅ |
| 运营总览 | 今日/近 7 日新增用户、活跃用户、AI 任务成功率、估算成本、Worker/队列/熔断/代理健康、额度 Top 5、最近失败任务 | ✅ |
| 埋点与任务台账 | 新增 `llm_calls`（token/耗时/成本/错误码）、`ai_jobs`（任务生命周期）；LLM 客户端与服务层接入 contextvars，worker 进程批量落库；worker 每 5 分钟回收卡死任务 | ✅ |
| 数据库 | 迁移 `8b2c3d4e5f60`：`llm_calls`、`ai_jobs`、`admin_audit_logs` + 跨用户列表索引 | ✅ |
| 配置修正 | `AUTOMATION_CRON_HOUR/MINUTE` 真正作为新用户默认值生效（此前 `schemas/automation.py` 写死 17:35） | ✅ |
| 测试与验收 | 后端 **214 passed**（含权限/分页/写操作审计/任务台账）；前端 typecheck/build 通过；Chrome 截图验收概览/用户/详情/审计 | ✅ |

**说明**：P0 只做用户类写操作与只读观测；配置修改仍需改 `.env` 并重启 API + worker。LLM 调用与任务数据从上线时刻开始记录，历史不可回填。后续 P1 成本日报/任务中心、P2 跨用户内容库、P3 数据源/日志/配置快照、P4 公告/反馈。

### 4.48 选股 AI 输出截断修复（2026-10-24）

**背景**：生产环境「低价寻宝」多次报「AI 返回结果异常，请稍后重试」。worker 日志显示模型 `sensenova-6.8-flash-lite` 在资深研究员精选时 `completion_tokens=6000 finish_reason=length`，并抛出「LLM 思考过程耗尽 token，未输出正文」。根因是推理模型的思考过程占满了 completion 额度，正文为空；原重试只是重复同样的 6000 token 请求，因此连续两次失败。不是行情源、额度或 JSON 字段问题。

| 事项 | 内容 | 状态 |
| --- | --- | --- |
| 推理力度 | 新增 `LLM_REASONING_EFFORT`（default/none/low/medium/high）；`default` 时代码对 SenseNova 自动使用 `none`，其他模型不传参。SenseNova 6.8 Flash Lite 实测支持 `extra_body.reasoning_effort`，关闭后能明显减少思考 token 并正常返回正文 | ✅ |
| 精选 JSON | 新增 `LLM_FINAL_REASONING_EFFORT`；默认 `default` 时沿用自动策略（SenseNova -> none），可单独设为 none/low 等 | ✅ |
| 输出上限 | 新增 `LLM_ANALYST_MAX_TOKENS=8000`、`LLM_FINAL_MAX_TOKENS=16000`；全局 `LLM_MAX_TOKENS` 默认从 4096 提到 8192 | ✅ |
| 错误提示 | 思考耗尽映射为 `LLM_OUTPUT_TRUNCATED`，提示「AI 思考过程过长，未能生成结果；请重试或减少候选数量」，不再显示泛化的「AI 返回结果异常」 | ✅ |
| 测试 | `test_llm.py` 覆盖默认 none 与显式 low 的 `extra_body`；后端全量测试通过 | ✅ |

**说明**：`max_tokens` 不能真正“无限”；SenseNova 6.8 Flash Lite 的最大输出与上下文仍有上限。生产部署后代码会自动对 SenseNova 使用 `none`；建议同时在 `/opt/zhiying-ai/.env` 设 `LLM_MAX_TOKENS=8192`，然后重启 `zhiying-api` 与 `zhiying-worker`。若仍希望保留部分推理，可设 `LLM_REASONING_EFFORT=low`，但要观察 `finish_reason=length` 是否再次出现。

---

## 五、未完成清单（截至 2026-10-24）

### 5.1 P1 收尾
| 事项 | 说明 | 状态 |
| --- | --- | --- |
| git 初始化 + 推送 | 远端仓库 `github.com/luoyuex/zhiying-ai`，`main` 已推送 | ✅ |
| SMTP 真实发信联调 | `.env` 已配 SMTP（`EMAIL_MODE=smtp`），仍需实测注册验证码能否收件 | 🟡 待实测 |
| admin 账号 | `backend/app/scripts/create_admin.py` 支持创建/提升/取消管理员，并校验最后一个管理员 | ✅ |

### 5.2 P2 行情数据层缺口
| 事项 | 说明 | 状态 |
| --- | --- | --- |
| 新闻/公告结构化 Provider | 已接东财公告 + 东财新闻搜索，10 分钟缓存、单源降级；元宝检索仍只用于 AI 分析与手动按需检索 | ✅（见 4.42） |
| 股票库增量更新 | 当前为手动种子（5925 只），无每日新股/退市增量同步 | ⬜ |
| 已完成部分 | 报价/K 线降级链、财务、资金流、情绪、缓存/限流/熔断、股票搜索 | ✅（见 4.6、4.14、4.21） |

### 5.3 P3 个股页缺口
- ✅ 已上线：报价头、12 项指标面板、日/周/月 K、前/后/不复权、技术诊断、代码/名称/拼音搜索、加入自选
- ✅ K 线叠加 MA/MACD/BOLL（klinecharts，主图 MA+BOLL、副图 VOL+MACD）
- ✅ 个股资金流图表（主力/超大单/大单/中单/小单，近 30 日）
- ✅ 个股新闻/公告列表（东财公告 + 东财新闻 + 元宝手动检索）

### 5.4 P4 任务化与 AI 缺口
- ✅ 已上线：ARQ、SSE、六分析师 LLM、团队讨论、首席决策、报告历史、重新分析、自选批量分析、活跃任务恢复
- ⬜ 定时分析（每日自动分析自选/持仓）
- ⬜ 评级变化标记（与上一次结论对比）
- ⬜ 关键价位提醒
- ⬜ 邮件 / Webhook 通知
- ⬜ 持仓分析历史（持仓变动记录、收益归因）
- ⬜ `llm/crypto.py`：AES-256-GCM 密钥加密（`APP_ENCRYPTION_KEY`）
- 🟡 `llm_calls` / `ai_jobs` / `admin_audit_logs` 已落库并接埋点（P0）；`usage_daily`、`agent_runs`、`llm_providers`、`app_settings` 未做
- ✅ 后端日志落盘（RotatingFileHandler → `backend/logs/`，app/worker 分文件；见 4.43）

### 5.5 P5–P7 缺口
- ✅ 6 维雷达图（报告页评分卡）
- ✅ 同股多次分析并排 diff（详情页「对比上一次」+ 历史页勾选对比）
- ✅ PDF 导出（前端一键下载）
- 🟡 管理后台 P0：运营总览、用户与额度、审计、LLM/任务台账已上线；成本日报、任务中心、内容库、数据源、公告/反馈待做
- ⬜ 生产部署：Nginx 同域反代 + HTTPS、`COOKIE_SECURE=true`、日志轮转、DB 备份、限流压测

### 5.6 P8 选股模块缺口（参考项目对齐）

五条策略（主力追踪 / 低价寻宝 / 小盘精选 / 业绩高增 / 价值洼地）已全部 AI 化并落库，剩余为参考项目其余板块与已知口径差异：

| 策略 / 模块 | 状态 | 说明 |
| --- | --- | --- |
| 主力追踪口径对齐 | ✅ | 东财区间排行（今日/3/5/10 日）+ 总市值 50–5000 亿 + 区间涨幅 ≤30% + 候选前 100；参考项目的 3/6/12 个月依赖问财，暂不接入（免费直连源最长 10 日） |
| 净利增长 / 低价 / 小市值 / 低估值 | ✅ | 规则候选 + AI 精选（参考项目无 AI，属增强） |
| 智策板块 | ⬜ | 板块轮动与概念热点 |
| 智瞰龙虎 | ⬜ | 龙虎榜席位跟踪 |
| 新闻流量 | ⬜ | 新闻热度/舆情选股 |
| 宏观分析 | ⬜ | 宏观指标解读 |
| 宏观周期 | ⬜ | 周期定位与资产配置 |
| 持仓分析 | 🟡 | 组合诊断 + 持仓联动已做；历史/归因/调仓建议未做 |
| AI 盯盘 | ⬜ | 盘中异动监控 |
| 实时监测 | ⬜ | 定时任务 + 评级变化 + 价位提醒 + 通知 |
| 策略监控 / 钉钉通知 | ⬜ | 参考项目低价/小市值带监控与钉钉推送 |

其他账号 / 体验缺口：
- ⬜ 邮箱修改（需验证码流程）、头像上传
- ⬜ 选股结果导出（CSV）
- ⬜ 分析师报告 Markdown 渲染（当前纯文本展示）

### 5.7 明确不做（防止范围膨胀）
- ❌ 交易下单 / 券商接口（永久不做）
- ❌ 港股美股（第二期后再评估）
- ❌ 多租户团队协作
- ❌ 移动端原生 App（响应式网页足够）

---

## 六、风险登记表

| 风险 | 等级 | 对策 | 状态 |
| --- | --- | --- | --- |
| 免费数据源封 IP（公网共享出口） | 高 | 缓存优先 + 熔断时前端显示「数据延迟」而非 500 + 多源降级 + UA 规范 + 预留 `EGRESS_PROXY_URL` | ✅ 缓存/限流/熔断/降级已落地 |
| LLM 成本被刷 | 高 | 日配额 + 6h 结果复用 + 上下文压缩 + max_tokens 上限 + `usage_daily` 记账 | 部分落地（配额/缓存/上限已做，记账待做） |
| LLM 输出格式不稳定 | 中 | 提示词约束 + Pydantic 校验 + json_repair + 失败重试 1 次；仍失败返回 502，不扣额度 | ✅ |
| 慢模型/推理模型导致 HTTP 超时 | 高 | 改后台 job + 轮询；单次 LLM 180s、job 420s；SDK 不自动重试；空响应不重复重试 | ✅ |
| 元宝搜索成本/结果质量 | 中 | 一次分析最多 1 次；30min 搜索缓存 + 6h AI 缓存优先；来源带日期/站点；失败/未配置自动跳过 | ✅ |
| AKShare 同步线程无法取消 | 中 | socket timeout + 线程池上限 8 + 超时丢弃 | ✅ 不适用（未引入 AKShare） |
| 验证码被爆破 | 中 | 已实现三重限流 + 5 次作废 | ✅ |
| refresh 被盗用 | 中 | 已实现轮换 + 重放检测全吊销 | ✅ |
| QQ/163 判垃圾邮件 | 低 | 规范发信人、纯 HTML 无外链、先发自己邮箱测试 | 待 SMTP 联调 |
| AKShare 接口变更 | 中 | 解析失败归 `SchemaDrift` 告警；关键路径用直连 HTTP | ✅ 不适用（已改东财直连） |
| 端口冲突 | 低 | 前端 5288 strictPort、后端 8010；改端口需同步 4 处（package.json / Makefile / vite proxy / README） | ✅ |
| worker 进程继承坏代理环境 | 高 | `trust_env` 会读启动终端的 HTTP(S)_PROXY；启动 worker 用干净终端，或 `.env` 显式配置 `EGRESS_PROXY_URL`；症状为全部数据源 2s 内失败 | 🟡 已定位（4.43），防重复发需日志落盘 + 启动预检 |

---

## 七、关键决策记录（ADR 摘要）

1. **不用 SQLite**：公网多用户并发写会排队，直接上 PostgreSQL 16。
2. **不用 Celery / WebSocket**：单机规模下 ARQ + Redis + SSE 足够，少三个运维面。
3. **不用 shadcn-vue / Element Plus**：手写 5~8 个基础组件 + token 化样式，控制「后台模板感」。
4. **邮箱存小写字符串而非 citext**：统一在 service 边界 `strip().lower()`，跨库可移植。
5. **service 层显式 commit**：FastAPI 0.106+ 的 yield 依赖在响应发出后才执行收尾，依赖里自动提交有「已返回 200 但提交失败」的风险。
6. **验证码不落库**：Redis TTL 天然过期，省清理任务；哈希存储防止 Redis 泄露即验证码泄露。
7. **不引入 AKShare**：热点行情、财务、资金流全部走腾讯/新浪/东财直连，速度快、依赖少、解析可控。

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

## 九、下一步计划（按建议顺序）

### 第一优先：收尾与交付保障
1. ⬜ 提交并推送当前改动（后台 P0 与既有体验修复尚未提交）
2. 🟡 SMTP 真实收信实测（注册验证码能否收到）
3. ✅ admin 账号生成脚本（`create_admin.py`，支持创建/提升/取消）

### 第二优先：选股模块增强（五策略已完成）
4. ✅ 主力追踪口径对齐（2026-10-23，见 4.46；3/6/12 个月区间因依赖问财暂未接入）
5. ⬜ 选股结果导出 CSV、报告 Markdown 渲染
6. ⬜ 参考项目其余板块按需评估：智策板块、智瞰龙虎、新闻流量、宏观分析、宏观周期
7. ⬜ 个人中心增强：邮箱修改（验证码流程）、头像上传

### 第三优先：AI 决策闭环
8. ✅ 定时选股（ARQ cron：每日自动跑策略并落记录，见 4.44）
9. ✅ 定时分析（每日自动分析自选股，用户可开关，见 4.44）
10. ⬜ 评级变化标记（本次结论 vs 上次结论）
11. ⬜ 关键价位提醒 + 邮件/Webhook 通知
12. ⬜ 持仓分析历史（持仓变动、收益归因、调仓记录）

### 第四优先：体验与技术债
13. ✅ K 线叠加 MA/MACD/BOLL、个股资金流图、个股新闻列表（2026-10-22，见 4.42）
14. ✅ 报告 6 维雷达、同股并排 diff、PDF 导出（2026-10-22，见 4.42）
15. ✅ 后端日志落盘（RotatingFileHandler，配合 worker 环境问题排查，见 4.43）
16. ⬜ `llm/crypto.py` 密钥加密、`usage_daily` 用量记账
17. 🟡 管理后台 P0 已上线；生产部署（Nginx/HTTPS/备份/压测）仍未开始
18. ⬜ 后台 P1：LLM 成本日报、任务中心（实时态/重跑）、定时任务执行记录
19. ⬜ 后台 P2：跨用户内容库（报告/选股/组合诊断/自选）
20. ⬜ 后台 P3：数据源/代理/熔断/缓存、配置快照、日志查看
21. ⬜ 后台 P4：公告/反馈
