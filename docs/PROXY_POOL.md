# 出站代理池设计

> 目标：为「行情类」出站请求提供多出口 IP，避免单 IP 被目标站封禁。
> 状态：P1 + 提取 API 已实施（2026-10-23）。当前来源为携趣提取 API（`EGRESS_PROXY_SOURCE=api`），实际落地范围与差异见文末「P1 实装记录」。

## 1. 问题

行情数据来自东财、腾讯、新浪三个免费源，全部从同一台服务器的固定 IP 发出。

- 单 IP 的请求特征高度集中：同一 UA、同一出口、固定路径、固定节奏
- 免费源的反爬阈值不公开，但「单 IP 日请求量 + 突发速率」是最主要的判定依据
- 一旦被封，表现不是 429，而是 **403 / 返回空 body / 返回验证码页**，现有的 `raise_for_status()` 拦不住空 body
- 目前靠令牌桶（腾讯 5/s、新浪 3/s、东财 5/s）+ 缓存把量压住，属于「尽量不触发」而非「封了能恢复」

用户规模上来后，单 IP 必然成为瓶颈。

## 2. 目标与非目标

**目标**

- 行情请求可轮换多个出口 IP，单个 IP 被封不影响整体可用性
- 被封的 IP 自动冷却、自动恢复，无需人工介入
- 与现有缓存 / 令牌桶 / 熔断 / 单飞协同，不破坏既有语义
- 代理池全部不可用时，能回落直连（降级而非雪崩）

**非目标**

- 不代理元宝搜索（WSA）与 LLM：两者有自己的鉴权与配额，且按 API Key 计费，不按 IP 封禁
- 不做浏览器指纹伪装（当前是纯 HTTP 抓取，不需要 JS 渲染）
- 不做全球多区域调度（目标站都在国内，出口 IP 也在国内即可）

## 3. 架构总览

```
                    providers/*.py  (14 处调用)
                            │
                            ▼
                  app/providers/http.py :: fetch()
                            │
                   ┌────────┴────────┐
                   │  EgressRouter   │  ← 按 URL 域名判定 provider
                   └────────┬────────┘
              ┌─────────────┴──────────────┐
              ▼                            ▼
      直连通道（元宝/LLM）          代理通道（行情）
      get_http_client()                    │
                                           ▼
                                  ProxyPool.acquire(provider)
                                           │
                          ┌────────────────┼────────────────┐
                          ▼                ▼                ▼
                   ProxyHealthStore   ProxySelector   ProxyClientCache
                      (Redis)         (打分选优)      (每代理一个 AsyncClient)
                          ▲
                          │
                    ProxySource
              (static / file / 服务商 API)
```

**关键设计：只改 `fetch()` 一个函数。** 所有 provider 都通过 `fetch(url, params, headers)` 出站，因此代理路由可以按 URL 域名自动判定，14 个调用点零改动：

```python
_PROVIDER_HOSTS = (
    ("eastmoney.com", "eastmoney"),
    ("gtimg.cn", "tencent"),
    ("sina.com.cn", "sina"),
)
```

## 4. 核心组件

### 4.1 ProxyEndpoint

```python
@dataclass(frozen=True, slots=True)
class ProxyEndpoint:
    id: str          # 稳定标识（host:port 的 hash），用于 Redis key
    url: str         # http://user:pass@host:port
    kind: Literal["datacenter", "residential", "self-hosted"] = "datacenter"
```

### 4.2 ProxySource — 代理从哪来

```python
class ProxySource(Protocol):
    async def fetch(self) -> list[ProxyEndpoint]: ...
```

三种实现，用 `EGRESS_PROXY_SOURCE` 切换：

| 实现 | 用途 |
| --- | --- |
| `static` | `.env` 里逗号分隔，适合 5-20 个固定 IP 起步 |
| `file` | 运维放 `config/proxies.json`，热加载，适合自建多机 |
| `provider`（实装名 `api`） | 调服务商提取 API（携趣等），按需拉取 |

### 4.3 ProxyHealthStore — 健康度（Redis）

```python
# 全局维度：代理本身死活
mkt:proxy:{id}                 → hash{ok, fail, consecutive_fail, latency_ms, cooldown_until}

# 按 provider 维度：某个 IP 是否被某站封
mkt:proxy:{id}:ban:{provider}  → 到期时间戳
```

**为什么要两个维度**：代理挂了是全局问题（所有站都不通），但「被东财封」不代表「被腾讯封」。分开记，才能做到只换受影响的那条链路。

### 4.4 ProxySelector — 怎么选

过滤 → 打分 → 加权随机：

1. 过滤：`cooldown_until > now` 的、`ban:{provider}` 未过期的直接排除
2. 打分：`score = 成功率 × (1 / (1 + latency_ms/500))`，再乘一个「最近使用次数」的衰减，避免总打同一个
3. 加权随机：按 score 抽样，而不是永远取最高分（防止惊群到同一个 IP）

### 4.5 ProxyClientCache — 连接复用

每个代理维护一个 `httpx.AsyncClient`，保持 keep-alive：

```python
class ProxyClientCache:
    def __init__(self, limit: int = 64) -> None: ...
    def get(self, endpoint: ProxyEndpoint) -> httpx.AsyncClient: ...
    async def aclose_all(self) -> None: ...
```

理由：`httpx 0.28` 的 per-request `proxy=` 会为每次请求新建 transport，失去连接复用；而行情请求是高频短请求，TCP/TLS 握手成本占比很高。代理数量在几十的量级，每个一个 client 完全可控。

## 5. 失败语义（最关键的部分）

不同失败要归到不同的账上，否则代理抖动会把整个 provider 熔断掉。

| 现象 | 归因 | 动作 | 是否计入 provider 熔断 |
| --- | --- | --- | --- |
| `ConnectError` / `ProxyError` / 407 | 代理坏了 | 该代理**全局**冷却 60s，换代理重试 | ❌ 否 |
| 403 / 429 / 验证码页 / 空 body | 该 IP 被目标站限 | 该 **(代理 × provider)** 冷却 15min，换代理重试 | ❌ 否 |
| 5xx | 目标站故障 | 换代理重试 1 次，仍失败则记熔断 | ✅ 是 |
| 404 / 业务空数据 | 正常结果 | 直接返回，不换代理 | ❌ 否 |

```python
class FailureKind(StrEnum):
    DEAD = "dead"        # 代理不可用
    BANNED = "banned"    # 目标站封了这个 IP
    UPSTREAM = "upstream"  # 目标站 5xx
```

重试上限 `EGRESS_PROXY_MAX_ATTEMPTS = 2`（含首次），避免「换 IP 重试」把流量放大。

**空 body 判定**：东财/腾讯被封时经常返回 200 + 空字符串。需要在 `fetch()` 里补一条：行情类 JSON 接口响应体为空或长度异常小，按 `BANNED` 处理。

## 6. 限速模型改造

现状：`TokenBucket(redis, rate, burst, name)` 按 provider 全局限速，多 IP 共享同一个桶 —— 代理白买了。

改成双层：

| 层 | key | 作用 |
| --- | --- | --- |
| 全局桶 | `mkt:tb:{provider}` | 总量保护，防止代理池把总 QPS 顶穿 |
| 出口桶 | `mkt:tb:{provider}:{proxy_id}` | 单 IP 节奏，模拟正常用户 |

吞吐上限 = `min(全局桶, N × 单 IP 桶)`。

**保守起步**：全局桶先维持现状（5/s），代理池稳定运行一周后再放宽到 15-20/s。不要一上线就把上限拉满，否则被封的是代理 IP，钱白花。

## 7. 配置

```env
# 总开关（默认关闭，关闭时行为与现在完全一致）
EGRESS_PROXY_ENABLED=false

# 来源：static | api
EGRESS_PROXY_SOURCE=static
EGRESS_PROXY_STATIC=http://user:pass@1.2.3.4:8080,http://user:pass@5.6.7.8:8080
EGRESS_PROXY_FILE=./config/proxies.json
EGRESS_PROXY_REFRESH_SECONDS=300

# 提取 API（source=api）：完整提取链接含 vkey，只放 .env
EGRESS_PROXY_API_URL=
# IP 有效期 30s → TTL 25s
EGRESS_PROXY_API_TTL_SECONDS=25
EGRESS_PROXY_API_ERROR_COOLDOWN_SECONDS=5

# 策略
EGRESS_PROXY_MAX_ATTEMPTS=2
EGRESS_PROXY_COOLDOWN_SECONDS=60        # 代理坏了的全局冷却
EGRESS_PROXY_BAN_SECONDS=900            # 被某站封的冷却
EGRESS_PROXY_PER_IP_RATE=2              # 单 IP 每秒请求数
EGRESS_PROXY_PROVIDERS=eastmoney,tencent,sina   # 空=全部行情源

# 兼容：单代理模式（旧配置，保留）
EGRESS_PROXY_URL=
```

> P1 实现 `static`；P2 已实现 `api`（携趣）；`file` 仍未实现。

## 8. 可观测性

- **日志**：每次换代理记一行 `proxy={id} provider={p} reason={kind} attempt={n}`，便于回溯某天为什么大量换 IP
- **指标**（Redis hash，管理接口读取）：
  - 可用代理数、各 provider 的封禁数
  - 每代理的成功率 / 平均延迟 / 今日请求数
- **管理接口**：`GET /api/v1/admin/proxy-pool`（`require_admin`），返回池子快照
- **告警条件**：可用代理 < 2，或 30 分钟内 `BANNED` 比例 > 30%

## 9. 落地阶段

| 阶段 | 内容 | 产出 |
| --- | --- | --- |
| P1 | 静态池 + 健康存储 + 失败换 IP + 双层限速 | 可用的代理池骨架，`EGRESS_PROXY_ENABLED` 控制 |
| P2 | 服务商 API 自动补充 + 管理接口 + 指标 | 代理可自动扩缩 |
| P3 | 按 provider 独立池、延迟优选、看板 | 精细化调度 |

P1 的验收标准：把 `EGRESS_PROXY_STATIC` 配一个坏代理 + 一个好代理，请求应自动跳过坏的并成功返回，日志里能看到 `reason=dead`。

## 10. 选型与成本

先估算量级（日活 100、人均 20 次页面访问）：

- 请求数：约 2-5 万/天（缓存命中后实际出站远低于此）
- 流量：单次 5-20KB，约 **1-2 GB/月**

| 类型 | 单价量级 | 适用 |
| --- | --- | --- |
| 数据中心代理 | 几十元/月（10-20 IP 不限流量） | 首选，先验证目标站是否识别机房 IP |
| 住宅代理 | ¥15-30/GB | 机房 IP 被封后的备选，流量小反而划算 |
| 自建（多台云主机 + squid） | 每台 ¥30-60/月 | IP 段固定、可控，但仍是机房 IP |

**建议路径**：先用 10 个数据中心 IP 跑两周，观察 `BANNED` 率；低于 5% 就够用，超过 30% 再换住宅代理。

## 11. 风险与兜底

| 风险 | 应对 |
| --- | --- |
| 代理池全挂 | `acquire()` 返回 `None` 时**回落直连**，保证可用性优先于隐蔽性 |
| 代理延迟高于直连 | 单 IP 延迟 > 3s 自动降权；`market_provider_timeout=6s` 保持不变 |
| 代理认证信息泄漏 | 日志只打 `proxy_id`，绝不打 `url`（含账号密码）；配置从 `.env` 读，不入库 |
| HTTPS 经代理 | 走 CONNECT 隧道，httpx 原生支持，无需额外配置 |
| 代理成为新瓶颈 | 连接池上限 + 全局并发闸门 8 不变，代理层不额外增加并发 |
| 被封后误判为业务失败 | 空 body / 验证码页必须在 `fetch()` 里显式识别，否则会当成「无数据」静默吞掉 |

## 12. 代码改动清单

| 文件 | 改动 |
| --- | --- |
| `app/providers/proxy_pool.py` | **新增**：`ProxyEndpoint` / `ProxySource` / `ProxyHealthStore` / `ProxySelector` / `ProxyPool` |
| `app/providers/egress.py` | **新增**：`EgressRouter` + `ProxyClientCache` + 失败分类 |
| `app/providers/http.py` | `fetch()` 改为走 `EgressRouter`；保留 `get_http_client()` 给元宝/LLM 直连 |
| `app/providers/resilience.py` | `TokenBucket` 增加 `scope` 参数（provider / provider×proxy） |
| `app/providers/registry.py` | 获取出口桶并 acquire；失败分类后决定是否记熔断 |
| `app/core/config.py` | 新增 `egress_proxy_*` 配置项 |
| `app/api/v1/admin.py` | **新增**：代理池快照接口 |

对现有调用方（14 个 provider 文件）**零改动**。

> 本节是完整目标清单；P1 的实际改动以第 13 节为准（`file` / `provider` 来源、管理接口、registry 改造未在 P1 落地）。

## 13. P1 实装记录（2026-10-23）

**已落地**

| 能力 | 文件 |
| --- | --- |
| 静态入口解析、Redis 健康度、加权选择、代理池 | `app/providers/proxy_pool.py` |
| 域名路由、失败分类、换出口、回落直连、每入口 client 缓存与令牌桶 | `app/providers/egress.py` |
| `fetch()` 接入路由；200 + 空 body 不再静默当无数据 | `app/providers/http.py` |
| `TokenBucket` 取令牌逻辑抽取（行为不变，Redis 故障仍放行） | `app/providers/resilience.py` |
| `egress_proxy_*` 配置 | `app/core/config.py`、`.env.example` |

未实现（按计划留到后续）：`file` 来源、管理接口、按 provider 独立池、看板。

**隧道代理接入时的差异（static 源）**

- 隧道入口背后由服务商换 IP，403/429 **不冷却整个入口**，只把同一入口再试一次（受 `EGRESS_PROXY_MAX_ATTEMPTS` 限制）。目标站建立隧道后主动断开（`RemoteProtocolError`、读超时）同样按 `UPSTREAM` 处理，不冷却入口；只有连不上 / 407 才按 `DEAD` 冷却 60s。
- 隧道入口禁用 keep-alive（`max_keepalive_connections=0`），否则快代理等隧道会固定在一个出口 IP；静态池仍保持连接复用。
- 看不到真实出口 IP，双层限速退化为「全局桶 + 隧道入口桶」。单入口时 `EGRESS_PROXY_PER_IP_RATE` 就是隧道总速率，默认 2/s；供应商允许更高时调到 5，或设 0 关闭单出口限速。
- 东财 `push2` 报价接口会偶发主动断开 httpx（直连与代理都会）；报价链本来就是腾讯优先，K 线会换出口重试后走东财或腾讯，属于预期降级。
- 单入口不可用时回落直连，可用性优先。
- 只代理东财/腾讯/新浪（含 `sinajs.cn`、`quotes.sina.cn`）；元宝搜索与 LLM 始终直连。

**P2：提取 API（2026-10-23 已实施）**

- `EGRESS_PROXY_SOURCE=api`：`ApiProxySource` 调携趣提取接口，`ApiProxyPool` 进程内按 TTL 缓存；每次取 1 个 IP，`time=30` 为秒，TTL 默认 25s（提前 5 秒换）。
- **API/worker 各自持有进程内池，各用各的 IP**，不通过 Redis 共享。
- 按请求懒提取：不预热、后台不刷新；只有行情请求到来且当前 IP 过期/被移除时才提取。同一进程的并发请求共用一把锁，只提取一次。
- DEAD/BANNED 丢弃当前 IP 并重新提取（同一请求内最多重试一次）；UPSTREAM（目标站 5xx/断开）保留 IP，避免为站点故障消耗提取次数。
- 代理请求超时压到 provider 超时以内（provider 6s → 代理 4.5s、connect 2s），坏 IP 会先失败并被换掉，不会被外层 `asyncio.timeout` 直接取消。
- 提取链接含 vkey，只放 `.env`；`httpx` 的 INFO 请求日志已关闭，日志只打脱敏后的 host:port。
- 提取链接目前是 `http://`（服务商不支持 HTTPS），vkey 会明文经过网络；只在可信网络使用并定期轮换。
- 实测：提取 IP 有时本身连不上（DEAD），会自动换一个重试；腾讯报价、东财 K 线可通过代理或回落直连完成。东财 `push2` 报价仍偶发重置，报价链降级到腾讯。

**配置示例（提取 API）**

```env
EGRESS_PROXY_ENABLED=true
EGRESS_PROXY_SOURCE=api
EGRESS_PROXY_API_URL=http://api.xiequ.cn/VAD/GetIp.aspx?...完整参数...
EGRESS_PROXY_API_TTL_SECONDS=25
```

**配置示例（隧道代理）**

```env
EGRESS_PROXY_ENABLED=true
EGRESS_PROXY_STATIC=http://账号:密码@隧道入口:端口
EGRESS_PROXY_ROTATE_PER_REQUEST=true
EGRESS_PROXY_PER_IP_RATE=2
```

也可以继续用旧变量 `EGRESS_PROXY_URL`：开启代理池且 `EGRESS_PROXY_STATIC` 为空时，它作为唯一入口；关闭代理池时保持旧的全局代理语义。`socks5://` 入口需要先执行 `uv add "httpx[socks]"`。

**验收**

- 单测：`tests/test_proxy_pool.py` 覆盖入口/提取响应解析、TTL 复用、懒提取（无请求不刷新）、并发只提取一次、失败换 IP、域名路由、失败分类、403 换出口、隧道 403 重试、限速跳过、全挂回落直连、Redis 健康度、空 body 识别。
- 实网自检：`uv run --directory backend python -m app.scripts.check_proxy`，对比「直连」与「代理」的出口 IP，并实际拉一次东财行情。
- 应用内：触发一次行情请求后，`backend/logs/app.log` 会出现 `代理出口已确认可用 proxy=... provider=...`（每个出口首次成功一次）；DEBUG 级别下每次成功都有 `代理请求成功`，失败/切换有 `reason=banned/dead`。
- 本地单测不访问外网。
