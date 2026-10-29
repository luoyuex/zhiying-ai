# Docker 一键部署

> 目标：克隆仓库后，用一套 `docker compose` 在 Linux 服务器上拉起官网、工作台、API、AI worker、PostgreSQL 与 Redis。
>
> 适合 2 核 4 GB 起步的机器；AI 调用走外部 LLM API，不需要 GPU。
>
> 需要 Docker 24+ 与 Docker Compose 2.24+（`docker compose version` 查看）。证书、域名与备案不在本文范围，见第 7 节。
>
> 首次构建会拉取 Node / Python / PostgreSQL / Redis 镜像并安装依赖，通常需要几分钟；内存只有 2 GB 时建议先加 2 GB swap，否则前端构建可能被 OOM 杀掉。

---

## 1. 三步启动

```bash
git clone https://github.com/luoyuex/zhiying-ai.git
cd zhiying-ai

# 生成 .env：随机 JWT_SECRET / OTP_SECRET / 数据库密码
./scripts/docker-init.sh

# 编辑 .env，至少填 LLM 三项（见第 2 节）
vi .env

# 构建并启动；首次会跑数据库迁移
docker compose up -d --build
```

浏览器打开 `http://服务器IP:8088/` 是官网，`http://服务器IP:8088/app/` 是工作台。第一个账号在注册页创建。

检查：

```bash
docker compose ps -a
curl -fsS http://127.0.0.1:8088/health; echo
```

预期：

- `postgres`、`redis`、`api`、`worker`、`web` 都是 `healthy`；
- `migrate` 是 `exited (0)`，迁移已跑完；
- 健康检查返回 `{"status":"ok","db":"ok","redis":"ok"}`。

> `migrate` 是故意的一次性容器，每次 `docker compose up` 都会把数据库迁到最新版本；它显示 `exited (0)` 是正常状态。

---

## 2. 最小配置

`./scripts/docker-init.sh` 已经填好下面三项，不需要再改：

```env
JWT_SECRET=<64 位随机串>
OTP_SECRET=<64 位随机串>
POSTGRES_PASSWORD=<32 位随机串>
```

必须自己填的是 LLM（不填时 AI 分析不可用）：

```env
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-替换成你的密钥
LLM_MODEL=deepseek-chat
```

公网访问时再改这三项，否则邮件里的报告链接会指向本地：

```env
PUBLIC_APP_URL=http://服务器IP:8088
CORS_ORIGINS=http://服务器IP:8088
```

其余键都有默认值，按需对照 `.env.example` 增加：邮箱验证码（`EMAIL_MODE=smtp` + `SMTP_*`）、元宝搜索（`WSA_*`）、行情出站代理（`EGRESS_PROXY_*`）、模型价格（`LLM_PRICE_*`）。

> `POSTGRES_PASSWORD` 只在第一次创建数据卷时生效。之后改它不会改数据库密码；要改密码，要么删卷重建（会丢数据），要么进库执行 `ALTER USER`，并同步修改 `.env` 里的 `DATABASE_URL`。

---

## 3. 首次初始化股票列表

股票名称/拼音搜索依赖本地股票表。启动后执行一次：

```bash
docker compose exec api .venv/bin/python -m app.scripts.seed_stocks
```

- 会从东方财富拉取约 5900 只 A 股代码、名称、拼音；需要容器能访问外网。
- 不执行也能按 6 位代码查行情，只是名称/拼音搜索为空。
- 新股、退市后重跑同一命令即可增量刷新。
- 如果服务器访问东财不稳定，先跑 `docker compose exec api .venv/bin/python -m app.scripts.check_proxy` 看结论，再决定是否开 `EGRESS_PROXY_*`。

---

## 4. 日常命令

```bash
# 查看状态与健康
docker compose ps -a
curl -fsS http://127.0.0.1:8088/health; echo
docker compose exec redis redis-cli GET ai:worker:alive   # 返回 1 表示 worker 心跳正常

# 日志（API / worker / web）
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f web

# 改完 .env 后重建 API 与 worker（配置在进程启动时读取）
docker compose up -d --force-recreate api worker

# 更新代码：拉取后重建，migrate 会自动执行
git pull --ff-only
docker compose up -d --build

# 停止（保留数据卷）
docker compose down

# 彻底清空数据（会删除 PostgreSQL / Redis 数据，谨慎）
docker compose down -v
```

发布或重启 worker 时，进行中的 AI 任务最多有 120 秒收尾时间（`stop_grace_period`）；大任务仍可能被取消，尽量避开使用高峰。

---

## 5. 备份与恢复

```bash
# 备份（建议加到 crontab，每天一次）
docker compose exec -T postgres pg_dump -U zhiying -d zhiying -Fc \
  | gzip > zhiying-$(date +%F).dump.gz

# 恢复（会覆盖当前库）
docker compose stop api worker
gunzip -c zhiying-2026-10-29.dump.gz \
  | docker compose exec -T postgres pg_restore -U zhiying -d zhiying --clean --if-exists
docker compose start api worker
```

`.env` 里有 JWT、SMTP、LLM 密钥，请单独备份并限制权限（`chmod 600 .env`）。

---

## 6. 端口与数据

| 服务 | 宿主机 | 说明 |
| --- | --- | --- |
| web | `${WEB_PORT:-8088}` | 唯一的公网入口，Nginx 静态站点 + `/api` 反代 |
| api | 不发布 | 仅容器网络内 `api:8010` |
| worker | 不发布 | 仅消费 Redis 队列 |
| postgres | `127.0.0.1:${POSTGRES_PORT:-5432}` | 只绑回环，供宿主机开发直连 |
| redis | `127.0.0.1:${REDIS_PORT:-6379}` | 只绑回环 |

数据都在命名卷里：`<项目名>_pgdata`、`<项目名>_redisdata`。项目名默认取仓库目录名（标准克隆是 `zhiying-ai_pgdata`），所以已有开发环境升级时数据卷不会丢。

本地开发可以只起依赖，后端仍用 `uv` 在宿主机跑：

```bash
docker compose up -d postgres redis
# 然后按 README 的本地开发步骤启动 API / worker / Vite
```

---

## 7. HTTPS

Compose 只暴露 HTTP。生产环境用下面任一方式终结 TLS，再把请求转到 `127.0.0.1:8088`：

- 宿主机已有 Nginx / 宝塔 / 1Panel：新建站点反代到 `http://127.0.0.1:8088`；
- 云负载均衡 / CDN：回源到服务器 `8088`，并透传 `X-Forwarded-Proto`；
- Caddy 自动证书：`Caddyfile` 最小配置如下。

```caddyfile
example.com {
    reverse_proxy 127.0.0.1:8088 {
        flush_interval -1   # AI 进度是 SSE，不能缓冲
    }
}
```

启用 HTTPS 后改 `.env`：

```env
PUBLIC_APP_URL=https://example.com
CORS_ORIGINS=https://example.com
COOKIE_SECURE=true
```

然后重建 API 与 worker：

```bash
docker compose up -d --force-recreate api worker
```

> **前置反代时注意真实 IP**：容器内 Nginx 会把 `X-Forwarded-For` 覆盖成直连 IP。如果前面还有 Nginx/Caddy/CDN，所有用户会被算成同一个 IP，验证码 IP 限流会误伤。需要按实际链路调整 `frontend/docker/nginx.conf` 或配置 `realip` 模块。
>
> `COOKIE_SECURE=true` 后刷新 Cookie 只走 HTTPS；在证书就绪前不要用浏览器测登录。

---

## 8. 常见问题

| 现象 | 排查 |
| --- | --- |
| `docker compose up` 报 `.env` 不存在 | 先执行 `./scripts/docker-init.sh`，或 `cp .env.example .env` |
| 8088 被占用 | 在 `.env` 里改 `WEB_PORT`，再 `docker compose up -d` |
| `migrate` 退出码非 0 | `docker compose logs migrate`；多半是数据库密码与 `DATABASE_URL` 不一致 |
| `/health` 返回 `db: down` | `docker compose ps` 看 postgres 是否 healthy；看 `POSTGRES_PASSWORD` 是否改过 |
| `/health` 返回 `redis: down` | 看 redis 是否 healthy；`docker compose exec redis redis-cli ping` |
| 发起 AI 分析返回 503 | worker 没起来或心跳过期；`docker compose ps worker`、`docker compose logs worker` |
| 登录后刷新掉线 | 是否 HTTPS、`COOKIE_SECURE` 与访问协议是否一致、域名是否一致 |
| 页面空白 / 刷新 404 | `docker compose logs web`；确认 `/app/` 回退到 `app.html` 的配置未被改坏 |
| AI 进度不实时 | 确认 `/api/` 反代有 `proxy_buffering off`（容器内 Nginx 已配）；Caddy 需 `flush_interval -1` |
| 构建很慢或拉不到依赖 | 给 Docker 配镜像加速；前端 npm、后端 uv 均在构建阶段联网 |
| 想用云数据库 | 在 compose 里去掉 `postgres`/`redis`，把 `DATABASE_URL`、`REDIS_URL` 改成托管地址（此时要覆盖 compose 里的同名 `environment`） |

---

## 9. 与裸机部署的关系

- **本文（Docker 全栈）**：一条命令拉起全部服务，适合快速部署、演示、给小团队用。
- **[DEPLOYMENT.md](DEPLOYMENT.md)（Nginx + systemd + Docker 仅跑数据库）**：适合需要精细控制进程、日志和发布节奏的生产环境。

两者共用同一份 `.env` 与数据库结构，迁移文件一致，可以互相切换；切换前先备份数据库。
