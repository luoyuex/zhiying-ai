# 智盈 AI 生产部署指南

> 目标：在一台 Linux 云服务器上部署官网、工作台、API、AI worker、PostgreSQL 与 Redis。
>
> 文档对应 2026-10 的代码；配置项以仓库当前 `.env.example` 与 `backend/pyproject.toml` 为准。
>
> 基线：Ubuntu 22.04 / 24.04 LTS + Nginx + systemd + Docker Compose（本文只用它跑 PostgreSQL / Redis，全栈 Compose 见 DOCKER.md）。
>
> 只想快速跑起来：用 **[DOCKER.md](DOCKER.md)** 的全栈 Compose，一条命令拉起全部服务。本文是裸机 + systemd 的精调部署，二者共用同一份 `.env` 与数据库结构。
>
> 使用宝塔 / 1Panel 时，Nginx 站点与证书申请可以换成面板操作；Python、systemd、Docker 步骤不变。
>
> 下文用 `[root]`、`[zhiying]` 标注命令执行身份。应用进程只以 `zhiying` 运行，不加入 sudo 组；Nginx、systemd、证书等系统操作使用 root。
>
> 域名示例统一写 `example.com`，请替换成实际域名。

部署顺序：服务器准备 → 生产 `.env` → PostgreSQL / Redis → 迁移与股票种子 → systemd → 前端构建 → Nginx → HTTPS → 验收。

---

## 1. 部署架构

```text
浏览器
  │ HTTPS 443
  ▼
Nginx (example.com)
  ├─ /              frontend/dist/index.html   产品官网
  ├─ /app/*         frontend/dist/app.html     Vue 工作台
  ├─ /api/*         → 127.0.0.1:8010           FastAPI
  └─ /health        → 127.0.0.1:8010           健康检查
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
     PostgreSQL 16                    Redis 7
     (127.0.0.1:5432)                 (127.0.0.1:6379)
                                              ▲
                                              │
                                  ARQ worker (systemd)
                                  ├─ AI 分析 / AI 选股任务
                                  ├─ 每日定时选股 / 定时分析
                                  └─ 心跳 ai:worker:alive
```

关键约束：

- **API 只负责入队**，AI 分析、AI 选股、每日定时任务都由独立的 ARQ worker 执行。
- **worker 停止时**，定时任务不会运行；worker 心跳过期（TTL 120 秒）后，新建 AI 分析 / 选股会返回 `503`。
- 前端、API、官网必须**同域部署**（`https://example.com` + `/api` 反代）。不要把 API 拆到独立域名：刷新令牌是 `SameSite=Lax` 的 httpOnly Cookie，跨站会失效。
- 后端只监听 `127.0.0.1:8010`，不直接对公网开放；PostgreSQL / Redis 也只绑定本机回环地址。

---

## 2. 服务器准备

### 2.1 推荐配置

| 项目 | 最低 | 推荐 |
| --- | --- | --- |
| CPU / 内存 | 2 核 4 GB | 4 核 8 GB |
| 磁盘 | 40 GB SSD | 60 GB+ SSD |
| 系统 | Ubuntu 22.04 / 24.04 LTS | 同左 |

AI 调用本身走外部 LLM API，不占 GPU；主要内存消耗来自 1 个 API 进程、1 个 worker 进程、PostgreSQL、Redis，以及前端构建时的 Node。

如果内存只有 2 GB，建议先加 2 GB swap，否则 `npm run build` 可能被 OOM 杀掉。

### 2.2 系统依赖、时区、防火墙 `[root]`

```bash
apt update
apt install -y git curl ca-certificates nginx ufw

timedatectl set-timezone Asia/Shanghai
timedatectl

# 先确认 SSH 端口；下面默认 22
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
ufw status
```

> 云厂商的安全组还需要单独放行 `22`、`80`、`443`。**不要**放行 `5432`、`6379`、`8010`。
>
> Docker 发布的端口可能绕过 UFW，所以真正可靠的做法是让容器只绑定 `127.0.0.1`（见第 4 节），而不是依赖 UFW 拦截。

### 2.3 Docker、Node.js `[root]`

```bash
# Docker + Compose 插件
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker
docker --version
docker compose version

# Node.js 22 LTS（用于构建前端）
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt install -y nodejs
node -v
npm -v
```

### 2.4 创建应用用户与目录 `[root]`

```bash
useradd --create-home --shell /bin/bash zhiying
usermod -aG docker zhiying

mkdir -p /opt/zhiying-ai
chown zhiying:zhiying /opt/zhiying-ai

# 数据库备份目录（第 11 节会用到）
install -d -o zhiying -g zhiying /var/backups/zhiying
```

`docker` 组等同于 root 权限，这是 Docker 的常规取舍；不要把 `zhiying` 再加入 sudo 组。

### 2.5 拉代码、安装 uv 与 Python `[zhiying]`

```bash
sudo -iu zhiying
git clone https://github.com/luoyuex/zhiying-ai.git /opt/zhiying-ai
cd /opt/zhiying-ai

curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
uv --version

uv python install 3.12
```

> 如果服务器访问 GitHub 不稳定，可以在本地打包源码后上传，但不要上传 `.venv`、`node_modules`、`frontend/dist`。这些产物在服务器上重新生成。
>
> `git clone` 只包含远端分支已有的提交。如果本地还有未提交改动，先提交并推送，或改用源码包 / rsync 上传；否则服务器上会缺少这些功能。部署前用 `git status` 和 `git log -1` 确认服务器代码与本地要发布的版本一致。

---

## 3. 生产 `.env`

配置文件必须放在**仓库根目录** `/opt/zhiying-ai/.env`，不是 `backend/.env`。后端 `app/core/config.py` 固定读取仓库根目录的 `.env`。

### 3.1 生成密钥 `[zhiying]`

```bash
cd /opt/zhiying-ai
cp .env.example .env
chmod 600 .env

openssl rand -hex 32   # 填 JWT_SECRET
openssl rand -hex 32   # 填 OTP_SECRET
openssl rand -hex 16   # 填数据库密码，同时用于 DATABASE_URL 和 POSTGRES_PASSWORD
```

### 3.2 最小可用配置

编辑 `.env`，保留下面这些键即可；其余键都有默认值，需要时再对照 `.env.example` 增加。

```env
# ===== 数据库 / 缓存 =====
DATABASE_URL=postgresql+asyncpg://zhiying:REPLACE_DB_PASSWORD@127.0.0.1:5432/zhiying
REDIS_URL=redis://127.0.0.1:6379/0

# Docker Compose 读取该键作为数据库密码；应用本身不读这个键
POSTGRES_PASSWORD=REPLACE_DB_PASSWORD

# ===== 安全 =====
JWT_SECRET=REPLACE_WITH_64_HEX
OTP_SECRET=REPLACE_WITH_ANOTHER_64_HEX

# ===== 邮件验证码 =====
EMAIL_MODE=smtp
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=REPLACE_WITH_YOUR_EMAIL
SMTP_PASSWORD=REPLACE_WITH_SMTP_AUTH_CODE
SMTP_FROM_NAME="智盈 AI"

# ===== 应用 =====
APP_NAME="智盈 AI"
# 定时任务结果邮件里的报告链接前缀（站点根地址，不带 /app）
PUBLIC_APP_URL=https://example.com
CORS_ORIGINS=https://example.com
COOKIE_SECURE=true
DEBUG=false

# ===== LLM（AI 分析核心）=====
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=REPLACE_WITH_LLM_KEY
LLM_MODEL=deepseek-chat
# 推理力度：default/none/low/medium/high；default 时 SenseNova 自动按 none
LLM_REASONING_EFFORT=default
LLM_FINAL_REASONING_EFFORT=default
LLM_MAX_TOKENS=8192
LLM_ANALYST_MAX_TOKENS=8000
LLM_FINAL_MAX_TOKENS=16000
# 可选：当前模型每百万 token 单价（人民币）；两项都填才启用后台成本估算
LLM_PRICE_INPUT_PER_M=
LLM_PRICE_OUTPUT_PER_M=

# ===== 任务队列 =====
AI_JOB_EXECUTION=arq
# 同时执行的任务数；实际模型并发 ≈ 本值 × LLM_ANALYST_CONCURRENCY
# 出现「LLM 服务限流」（LLM_BUSY）时先调小本值
AI_WORKER_MAX_JOBS=4
AI_DAILY_QUOTA_OVERRIDE=0
```

可选集成（不需要就整段不写）：

```env
# 元宝搜索（腾讯云 WSA，可选）
WSA_SECRET_ID=
WSA_SECRET_KEY=

# 行情出站代理（默认关闭；服务器直连腾讯/新浪/东财失败时再开）
EGRESS_PROXY_ENABLED=false
# EGRESS_PROXY_SOURCE=api
# EGRESS_PROXY_API_URL=
# EGRESS_PROXY_API_TTL_SECONDS=25
```

> 应用对行情请求使用 `trust_env=False`，不会读取 shell 的 `HTTP_PROXY` / `HTTPS_PROXY`；要代理行情请用 `EGRESS_PROXY_*`。LLM 与元宝搜索始终直连，不走行情代理。代理池细节见 [PROXY_POOL.md](PROXY_POOL.md)。

注意事项：

- `REPLACE_DB_PASSWORD` 必须是同一串密码，而且只使用十六进制字符；这样不会触发 URL 编码和 Compose 插值问题。
- `POSTGRES_PASSWORD` 只在第一次初始化 PostgreSQL 数据卷时生效；数据卷已存在时改它不会修改数据库密码。
- `COOKIE_SECURE=true` 表示刷新 Cookie 只通过 HTTPS 发送。**在 HTTPS 完成前不要用浏览器测试登录**，否则刷新会失败；这是预期行为。
- `CORS_ORIGINS` 写完整 origin，不要带末尾斜杠。只使用一个主域名；如需 `www`，统一 301 到主域名。
- 值里包含 `#`、空格等特殊字符时用双引号包起来。
- `.env` 里的 `AUTOMATION_CRON_HOUR` / `AUTOMATION_CRON_MINUTE` 当前版本不参与调度；定时任务实际按用户在个人中心保存的时间执行（默认 17:35）。
- 改完 `.env` 后必须重启 API 和 worker，配置在进程启动时读取并缓存。

---

## 4. 启动 PostgreSQL 与 Redis

### 4.1 密码与端口

项目自带的 `docker-compose.yml` 是**全栈编排**（postgres / redis / migrate / api / worker / web）。裸机部署只用其中的数据库与缓存，注意两点：

- `5432`、`6379` **已经只绑定 `127.0.0.1`**，不需要再写覆盖文件；
- 数据库密码从 `.env` 的 `POSTGRES_PASSWORD` 读取，缺失时回退到弱口令 `zhiying`。

所以只要按 3.1 把 `POSTGRES_PASSWORD` 设成强密码，并保证 `DATABASE_URL` 使用同一个密码即可。

> 如果你从旧版本升级、本地还留着 `docker-compose.override.yml`（用 `!override` 改端口的那种），它仍然兼容，但已经不是必需；不需要时删掉，避免两套配置互相干扰。

### 4.2 第一次启动

**只启动数据库与缓存**：不要执行不带服务名的 `docker compose up -d`，那会把 API、worker、web 也一起拉起来，和 systemd 里的进程重复。

```bash
cd /opt/zhiying-ai
docker compose up -d postgres redis
docker compose ps

# 确认只监听回环地址；如果看到 0.0.0.0:5432 或 0.0.0.0:6379，说明有旧覆盖文件或旧容器还在
ss -lntp | grep -E ':5432|:6379'

docker compose exec -T postgres pg_isready -U zhiying -d zhiying
docker compose exec -T redis redis-cli ping
```

预期：

- `docker compose ps` 中两个容器都是 `healthy`。
- `ss` 显示 `127.0.0.1:5432`、`127.0.0.1:6379`。
- `pg_isready` 输出 `accepting connections`。
- `redis-cli ping` 输出 `PONG`。

> 如果提示 Docker 权限不足，说明当前 shell 没吃到 `docker` 组：`exit` 后重新 `sudo -iu zhiying`，或用 root 执行 compose 命令。
>
> `docker compose down` 会保留数据卷；**不要使用 `docker compose down -v`**，它会删除 PostgreSQL 和 Redis 的数据卷。

> 如果数据卷在此之前已经用弱口令 `zhiying` 初始化过，数据库密码不会跟着 `.env` 变。此时要么删除数据卷重建（会丢数据），要么进入容器执行：
>
> ```bash
> docker compose exec postgres psql -U zhiying -d postgres \
>   -c "ALTER USER zhiying WITH PASSWORD 'REPLACE_DB_PASSWORD';"
> ```
>
> 然后同步修改 `.env` 里的 `DATABASE_URL` 和 `POSTGRES_PASSWORD`，重启 API / worker。

### 4.3 使用云数据库时

如果使用云厂商的托管 PostgreSQL / Redis：

- 跳过 4.1 / 4.2 的 Docker 启动。
- 把 `DATABASE_URL`、`REDIS_URL` 改成托管实例地址（Redis 有密码时使用 `redis://:密码@host:6379/0`）。
- 在云数据库安全组中只放行应用服务器的内网 IP。
- 仍然需要执行第 5 节的迁移与种子。

> 托管数据库密码包含 `@`、`:`、`/`、`#` 等字符时，需要先做 URL 编码再写入 `DATABASE_URL`；Redis 密码同理。自建 Docker 数据库按 3.1 使用十六进制密码，不需要编码。

---

## 5. 初始化后端

### 5.1 安装依赖 `[zhiying]`

```bash
cd /opt/zhiying-ai/backend
uv sync --frozen --no-dev --python 3.12
```

如果提示找不到 `uv`，使用绝对路径：

```bash
~/.local/bin/uv sync --frozen --no-dev --python 3.12
```

生产环境不安装 dev 依赖（pytest / ruff）。不要在服务器上跑测试。

### 5.2 数据库迁移

```bash
cd /opt/zhiying-ai/backend
.venv/bin/alembic upgrade head
```

迁移是幂等的；以后每次更新代码后都要重跑。

### 5.3 同步 A 股基础列表

```bash
cd /opt/zhiying-ai/backend
.venv/bin/python -m app.scripts.seed_stocks
```

- 会从东方财富拉取约 5900 只 A 股代码 / 名称 / 拼音，用于代码和名称搜索。
- 需要 Redis 已启动，并且服务器能访问东方财富。如果启用了出站代理，种子请求也会走代理。
- 先检查网络可以加 `--dry-run`：

```bash
.venv/bin/python -m app.scripts.seed_stocks --dry-run
```

- 不执行种子不影响按 6 位代码查询行情，但名称 / 拼音搜索会是空的。
- 新股、退市后重新执行同一命令即可增量刷新。

> 数据库没有预置管理员账号，第一个账号通过注册页创建。需要调整某个用户的每日额度时：
>
> ```bash
> cd /opt/zhiying-ai
> docker compose exec -T postgres psql -U zhiying -d zhiying \
>   -c "UPDATE users SET daily_analysis_quota=20 WHERE email='user@example.com';"
> ```

### 5.4 首次启动前自检

```bash
cd /opt/zhiying-ai/backend
.venv/bin/python -c "from app.main import app; print(app.title)"
```

能打印 `智盈 AI API` 说明 `.env`、Python 依赖和应用导入正常。这个命令不会连接数据库。

---

## 6. systemd 常驻服务

> 以下命令切回 root 终端执行：如果当前还是 `zhiying` 的登录 shell，执行 `exit` 回到 root；之后需要操作应用文件时，再用 `sudo -iu zhiying` 进入。

### 6.1 API 服务 `[root]`

```bash
tee /etc/systemd/system/zhiying-api.service >/dev/null <<'EOF'
[Unit]
Description=Zhiying AI API (FastAPI)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=zhiying
Group=zhiying
WorkingDirectory=/opt/zhiying-ai/backend
Environment=TZ=Asia/Shanghai
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/zhiying-ai/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010 --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=always
RestartSec=5
TimeoutStopSec=30
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
```

### 6.2 ARQ worker `[root]`

```bash
tee /etc/systemd/system/zhiying-worker.service >/dev/null <<'EOF'
[Unit]
Description=Zhiying AI Worker (ARQ)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=zhiying
Group=zhiying
WorkingDirectory=/opt/zhiying-ai/backend
Environment=TZ=Asia/Shanghai
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/zhiying-ai/backend/.venv/bin/arq app.worker.WorkerSettings
Restart=always
RestartSec=10
TimeoutStopSec=120
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
```

> 两个服务都从 `/opt/zhiying-ai/.env` 读取配置，不要再写 `EnvironmentFile=`，避免两套配置不一致。

> `AI_WORKER_MAX_JOBS` 决定单个 worker 进程内同时跑几个任务（当前 4）。队列积压时优先调大它，但模型实际并发约为它 × `LLM_ANALYST_CONCURRENCY`（默认 3），要低于模型服务商的限流阈值；worker 日志出现「LLM 服务限流」或任务大面积 `LLM_BUSY` 失败就回调。改完只需 `systemctl restart zhiying-worker`，不用重启 API。

### 6.3 启动与检查

```bash
systemctl daemon-reload
systemctl enable --now zhiying-api zhiying-worker

systemctl status zhiying-api --no-pager
systemctl status zhiying-worker --no-pager

# 本地健康检查
curl -fsS http://127.0.0.1:8010/health; echo
```

预期健康检查返回：

```json
{"status":"ok","db":"ok","redis":"ok"}
```

如果返回 `degraded`，先检查 PostgreSQL / Redis 和 `.env` 里的连接串。

### 6.4 为什么只开 1 个 API worker

当前行情缓存、限流、出站代理池、HTTP 客户端和全局并发闸门都包含**进程内状态**。多开 uvicorn worker 会导致：

- 每个进程各自维护代理池和 HTTP 连接；
- Redis 令牌桶虽然共享，但全局并发闸门和部分熔断状态在进程内，实际出站并发会成倍增加；
- 数据库连接池按进程翻倍（每个进程 `pool_size=10 + max_overflow=20`）；
- 出站代理提取频率成倍增加。

初期保持 `--workers 1`。确实需要扩容时，先压测并确认代理服务商额度、PostgreSQL `max_connections` 和 Redis 负载。

> 不要在生产环境使用 `--reload`，也不要把 `AI_JOB_EXECUTION` 设为 `inline`。`inline` 会在 API 进程里执行 AI 任务，API 重启即中断。

---

## 7. 构建前端

> 7.1 以 `zhiying` 身份执行（root 下用 `sudo -iu zhiying` 进入）；7.2 切回 root 执行权限修正。

### 7.1 构建 `[zhiying]`

```bash
cd /opt/zhiying-ai/frontend
npm ci
npm run build

ls -lh dist/index.html dist/app.html
```

前端没有构建期环境变量；API 地址固定为同域 `/api/v1`，由 Nginx 反代。换域名在功能上只需要改 Nginx 和 `.env`，不需要重新构建；如果改动了官网的 canonical / OG 等 SEO 信息，才需要重新构建（见 13.3）。

正式域名确定后，如果还要改官网的 canonical / OG 分享图（见 13.3），先改 `frontend/index.html` 再执行 `npm run build`，否则改动不会进入 `dist`。

如果构建被内存杀掉，可以加大 Node 堆：

```bash
NODE_OPTIONS=--max-old-space-size=2048 npm run build
```

### 7.2 让 Nginx 能读取静态文件 `[root]`

```bash
chmod 755 /opt/zhiying-ai /opt/zhiying-ai/frontend /opt/zhiying-ai/frontend/dist
find /opt/zhiying-ai/frontend/dist -type d -exec chmod 755 {} \;
find /opt/zhiying-ai/frontend/dist -type f -exec chmod 644 {} \;

# 确保应用能写日志
install -d -o zhiying -g zhiying /opt/zhiying-ai/backend/logs
```

`.env` 保持 `600`，Nginx 不需要也不应该读取它。

---

## 8. Nginx 同域反向代理

> 以下命令以 root 身份执行。

### 8.1 站点配置 `[root]`

```bash
tee /etc/nginx/sites-available/zhiying.conf >/dev/null <<'EOF'
upstream zhiying_api {
    server 127.0.0.1:8010;
    keepalive 16;
}

server {
    listen 80;
    server_name example.com;

    root /opt/zhiying-ai/frontend/dist;
    index index.html;

    server_tokens off;
    client_max_body_size 10m;

    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options SAMEORIGIN always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    # /app 统一补斜杠
    location = /app {
        return 302 /app/$is_args$args;
    }

    # 工作台深链全部回退到 app.html
    location ^~ /app/ {
        try_files $uri /app.html;
    }

    # API 反代
    location /api/ {
        proxy_pass http://zhiying_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        # Nginx 是唯一入口时覆盖 X-Forwarded-For，
        # 防止客户端伪造 IP 绕过验证码的 IP 限流。
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";

        # AI 任务 SSE 最长约 12 分钟，Nginx 必须比它长
        proxy_read_timeout 900s;
        proxy_send_timeout 900s;
        proxy_buffering off;
    }

    # 健康检查；如不需要公网探测可以删掉
    location = /health {
        proxy_pass http://zhiying_api;
        access_log off;
    }

    # Vite 产物带内容哈希，可以长缓存
    location /assets/ {
        try_files $uri =404;
        expires 30d;
    }

    # HTML 不能长缓存，否则发布后仍引用旧资源
    location = /index.html { expires -1; }
    location = /app.html { expires -1; }

    # 官网其余路径
    location / {
        try_files $uri $uri/ /index.html;
    }

    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css application/json application/javascript text/javascript application/xml image/svg+xml;
}
EOF

ln -sf /etc/nginx/sites-available/zhiying.conf /etc/nginx/sites-enabled/zhiying.conf

nginx -t
systemctl reload nginx
```

> `example.com` 要替换成正式域名。如果这是全新服务器、不需要 Nginx 默认站点，可以再执行 `rm -f /etc/nginx/sites-enabled/default`；如果服务器上还有别的站点，不要删除它，用 `server_name` 区分即可。
>
> 如果要支持 `www.example.com`，把它加入 `server_name` 和证书，并单独做 301 到 `https://example.com`；应用只认一个主域名，避免 Cookie 落到两个 host 上。

### 8.2 为什么这样配

- **`/app/` 回退到 `app.html`**：Vue Router 的 base 是 `/app/`，刷新 `/app/reports/xxx` 必须命中 `app.html`；其余路径回退到官网 `index.html`。
- **`/assets/` 长缓存、HTML 不缓存**：Vite 资源名带哈希；HTML 若缓存会导致发布后加载已删除的旧资源。
- **SSE 关闭缓冲**：AI 进度通过 `GET /api/v1/ai/jobs/{id}/events` 推送。`proxy_buffering off` 与后端返回的 `X-Accel-Buffering: no` 共同保证进度实时到达；否则会变成任务结束后一次性输出。
- **覆盖 `X-Forwarded-For`**：后端用 XFF 做验证码 IP 限流；如果直接追加客户端传来的 XFF，攻击者可以伪造 IP。Nginx 是唯一入口时用 `$remote_addr` 覆盖。
- **`/health` 不在 `/api/` 下**：后端健康检查是 `/health`，需要单独反代。

> 如果调大了 `LLM_JOB_TIMEOUT_SECONDS`，SSE 的持续时间也会变长，需要同步调大 Nginx 的 `proxy_read_timeout`（当前 900s 对应默认 600s 任务超时，余量约 3 分钟）。

> 如果前面还有 CDN / WAF / 云负载均衡，需要先配置 `ngx_http_realip_module`，让 `$remote_addr` 变成真实客户端 IP，否则所有用户会被算成同一个出口 IP，验证码 IP 限流会误伤。
>
> 如果 TLS 在云负载均衡终止，Nginx 只监听 80 也能工作；此时确保负载均衡把 `X-Forwarded-Proto` 传下来，并把 `COOKIE_SECURE` 保持为 `true`。

### 8.3 HTTP 阶段验证

```bash
curl -I http://example.com/
curl -sS -o /dev/null -w '%{http_code}\n' http://example.com/app/login
curl -sS -o /dev/null -w '%{http_code}\n' http://example.com/api/v1/ai/config
curl -sS http://example.com/health; echo
```

预期：

- 官网 `/` 返回 200；
- `/app/login` 返回 200（内容应是工作台 HTML，不是官网）；
- `/api/v1/ai/config` 未登录返回 **401**；
- `/health` 返回 `{"status":"ok","db":"ok","redis":"ok"}`。

> 此阶段不要测试登录：`COOKIE_SECURE=true` 的刷新 Cookie 不会通过 HTTP 发送，表现为登录后刷新掉线。完成 HTTPS 后再测。

---

## 9. HTTPS

### 9.1 前置条件

- 域名 A 记录已经指向服务器公网 IP；
- 安全组 / UFW 放行 80、443；
- Nginx 的 `server_name` 已改成正式域名。

### 9.2 申请证书 `[root]`

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d example.com --redirect
```

Certbot 会自动：

- 申请 Let's Encrypt 证书；
- 增加 443 server 配置；
- 把 HTTP 请求 301 到 HTTPS。

检查：

```bash
nginx -t
curl -I https://example.com/
curl -sS -o /dev/null -w '%{http_code}\n' https://example.com/app/login
```

### 9.3 确认 Cookie 配置 `[zhiying]`

`.env` 中已经是：

```env
COOKIE_SECURE=true
CORS_ORIGINS=https://example.com
DEBUG=false
```

如果之前为了 HTTP 调试改成了 `false`，现在改回 `true`，然后 `[root]` 重启：

```bash
systemctl restart zhiying-api zhiying-worker
```

### 9.4 续期

```bash
certbot renew --dry-run
systemctl list-timers | grep certbot
```

Let's Encrypt 证书有效期 90 天，Certbot 包会自动安装续期 timer，不要手动删除。

> 如果域名套了 Cloudflare 等 CDN，HTTP-01 验证可能受代理影响；必要时先把记录的代理状态切到 DNS-only，证书签发后再恢复。
>
> HSTS 可以在确认 HTTPS 稳定后再加；不要在上线前直接开启长期 HSTS 并包含子域。

---

## 10. 上线验收清单

### 10.1 服务与基础设施

```bash
# [root]
systemctl status zhiying-api --no-pager
systemctl status zhiying-worker --no-pager
curl -fsS http://127.0.0.1:8010/health; echo

# [zhiying] 进入项目目录后再执行 compose，确保自动加载 override
cd /opt/zhiying-ai
docker compose ps
docker compose exec -T redis redis-cli GET ai:worker:alive
```

- [ ] 两个 systemd 服务都是 `active (running)`
- [ ] `/health` 返回 `status: ok`，`db` / `redis` 都是 `ok`
- [ ] PostgreSQL / Redis 容器 `healthy`，端口只监听 `127.0.0.1`
- [ ] Redis 中 `ai:worker:alive` 返回 `1`（worker 心跳正常）

### 10.2 官网与工作台

- [ ] `https://example.com/` 显示官网
- [ ] `https://example.com/app/` 显示工作台
- [ ] 直接访问 `https://example.com/app/login`、`/app/reports` 刷新不 404
- [ ] 浏览器 Network 中 `/assets/*.js`、`*.css` 均为 200
- [ ] 浏览器 Console 无 CORS / 混合内容报错

### 10.3 注册、登录与会话

- [ ] 注册页能收到真实邮件验证码（`EMAIL_MODE=smtp`）
- [ ] 注册成功后进入工作台
- [ ] 登录后刷新整页仍保持登录（依赖 `/api/v1/auth/refresh` + httpOnly Cookie）
- [ ] Cookie `zy_refresh` 的属性为 `HttpOnly`、`Secure`、`SameSite=Lax`、`Path=/api/v1/auth`
- [ ] 退出登录后刷新回到登录页

如果收不到邮件，先看第 12 节。临时排查可以把 `EMAIL_MODE=console`，验证码会打印到 `backend/logs/app.log`，但生产环境必须改回 `smtp`。

### 10.4 行情与 AI

- [ ] 输入 6 位代码能打开个股详情
- [ ] 报价、日/周/月 K 线、技术面诊断正常返回
- [ ] 名称 / 拼音搜索有结果（说明种子已同步）
- [ ] 自选股添加 / 删除、批量分析可用
- [ ] 发起 AI 分析后，进度条通过 SSE 实时更新，最终生成六分析师报告
- [ ] 报告写入历史报告，刷新页面后仍可查看
- [ ] 再发起一次同股分析，命中 6 小时缓存（不重复消耗额度）
- [ ] AI 选股五种策略可以发起任务并返回结果
- [ ] 报告对比、PDF 导出、组合诊断可用
- [ ] 「公开信息」面板有来源列表，或明确标注本次未收录 / 数据缺口

### 10.5 定时任务

- [ ] 在个人中心开启定时选股 / 定时分析，设置一个 5 分钟后的时间
- [ ] 到点后（最多延迟 5 分钟）在选股历史 / 报告历史看到结果
- [ ] `backend/logs/worker.log` 或 `journalctl -u zhiying-worker` 有「定时任务入队」日志

邮件通知（2026-10-24 新增）：

- [ ] 个人中心 → 定时任务能看到「邮件通知」，开启后显示接收地址（默认账号邮箱），保存后刷新仍保留
- [ ] `.env` 已配置 `PUBLIC_APP_URL`，邮件里的报告链接指向正式站点
- [ ] 填写可收信地址并等任务跑完，收到当天汇总邮件
- [ ] `backend/logs/worker.log` 有「定时任务汇总邮件已发送」日志

完整更新步骤见 [RELEASE_NOTES.md](RELEASE_NOTES.md)。

定时任务依赖：

- worker 正在运行；
- LLM 已配置（`LLM_BASE_URL` + `LLM_API_KEY` + `LLM_MODEL`）；
- 用户已开启对应任务线；
- 当天额度未用完。

任务时间按 `Asia/Shanghai` 解释，调度器每 5 分钟检查一次；如果 worker 在设定时间之后才启动，当天尚未跑过的任务会在下一次检查时补跑。

### 10.6 发布后排障

- [ ] `journalctl -u zhiying-api -n 100 --no-pager` 无未捕获异常
- [ ] `journalctl -u zhiying-worker -n 100 --no-pager` 无反复重连 / 心跳失败
- [ ] Nginx 错误日志无 502 / 504
- [ ] `df -h` 磁盘余量充足

---

## 11. 日常运维

### 11.1 日志位置

| 来源 | 位置 |
| --- | --- |
| API 应用日志 | `/opt/zhiying-ai/backend/logs/app.log` |
| worker 应用日志 | `/opt/zhiying-ai/backend/logs/worker.log` |
| systemd stdout | `journalctl -u zhiying-api` / `journalctl -u zhiying-worker` |
| Nginx | `/var/log/nginx/access.log`、`/var/log/nginx/error.log` |
| PostgreSQL / Redis | `docker compose logs postgres` / `docker compose logs redis` |

应用日志按 `LOG_MAX_BYTES` / `LOG_BACKUP_COUNT` 自动滚动（默认 5 MB × 5）。

```bash
tail -f /opt/zhiying-ai/backend/logs/app.log
tail -f /opt/zhiying-ai/backend/logs/worker.log
journalctl -u zhiying-worker -f
tail -f /var/log/nginx/error.log
```

### 11.2 发布更新

更新前先备份数据库；前端构建可以放在停服之前，迁移必须在停服之后。下面的代码块标注了执行身份。

```bash
# [zhiying] 备份数据库（备份目录已在 2.4 创建）
cd /opt/zhiying-ai
docker compose exec -T postgres pg_dump -U zhiying -d zhiying -Fc \
  | gzip > /var/backups/zhiying/zhiying-$(date +%F-%H%M).dump.gz

# [zhiying] 拉代码、装依赖、构建前端
cd /opt/zhiying-ai
git pull --ff-only

cd backend
~/.local/bin/uv sync --frozen --no-dev --python 3.12

cd ../frontend
npm ci
npm run build
```

```bash
# [root] 低峰期停服务、迁移、启动
systemctl stop zhiying-api zhiying-worker
cd /opt/zhiying-ai/backend
.venv/bin/alembic upgrade head
systemctl start zhiying-worker zhiying-api
```

启动后按第 10 节做快速验收。

发布注意：

- 每个版本需要手动补充的配置与专项验收见 **[RELEASE_NOTES.md](RELEASE_NOTES.md)**。
- **不要运行 `git clean -fdx`**：`.env`、日志、以及可能存在的 `docker-compose.override.yml` 都在忽略列表中，会被删除。
- 更新后对照 `.env.example`，如果新增了配置键，需要手动补到 `.env`。
- **worker 必须重启**：定时任务调度、汇总邮件、价位提醒检查等 cron 在 worker 进程内注册，只重启 API 不会加载新代码。
- 当前 ARQ worker 没有设置 `job_completion_wait`，`systemctl stop/restart zhiying-worker` 会立即取消正在跑的 AI / 选股任务。发布尽量避开用户使用高峰。
- worker 启动时会立即执行一次定时任务调度。若当天已过用户设定的时间且尚未跑过，启动后会补跑；发布尽量避开默认的 17:35 等任务时间点。
- API 重启不会中断 worker 中的 AI 任务，但会断开浏览器 SSE 连接；前端会自动回退到轮询，刷新页面也能恢复。

### 11.3 回滚

- 代码回滚：切换到上一个稳定 commit 后，重新执行依赖安装、前端构建、迁移和重启。
- 数据库回滚：如果新版本迁移不兼容，停服务后用发布前备份恢复；不要只回滚代码而保留新 schema。
- 回滚前先 `git status` 确认服务器上没有未提交的本地修改，不要用 `reset --hard` 覆盖未知改动。

### 11.4 数据库备份与恢复

备份目录已在 2.4 创建并设置属主。如果跳过了那一步，用 root 补建：

```bash
# [root]
install -d -o zhiying -g zhiying /var/backups/zhiying
```

手动备份：

```bash
# [zhiying]
cd /opt/zhiying-ai
docker compose exec -T postgres pg_dump -U zhiying -d zhiying -Fc \
  | gzip > /var/backups/zhiying/zhiying-$(date +%F).dump.gz
```

加入每日定时备份（`[root]` 执行 `crontab -u zhiying -e`；如果当前就是 zhiying，可用 `crontab -e`）：

```cron
0 3 * * * cd /opt/zhiying-ai && docker compose exec -T postgres pg_dump -U zhiying -d zhiying -Fc | gzip > /var/backups/zhiying/zhiying-$(date +\%F).dump.gz
30 3 * * * find /var/backups/zhiying -type f -name '*.dump.gz' -mtime +14 -delete
```

恢复（**会覆盖当前数据库，先确认备份文件**）：

```bash
# [root]
systemctl stop zhiying-api zhiying-worker

cd /opt/zhiying-ai
gunzip -c /var/backups/zhiying/zhiying-2026-10-23.dump.gz \
  | docker compose exec -T postgres pg_restore -U zhiying -d zhiying --clean --if-exists

systemctl start zhiying-worker zhiying-api
```

`.env` 里有 JWT / OTP / SMTP / LLM 等密钥，建议单独加密备份；不要只依赖数据库备份。

Redis 保存验证码、任务状态、额度和心跳。Redis 丢失不会丢账号和报告，但会中断进行中的 AI 任务、让当天额度计数重置；Compose 已启用 AOF。

### 11.5 监控建议

```bash
# [root] API 健康
curl -fsS http://127.0.0.1:8010/health; echo

# [zhiying] worker 心跳
cd /opt/zhiying-ai
docker compose exec -T redis redis-cli GET ai:worker:alive

# 资源（root 或 zhiying 均可）
free -h
df -h
docker stats --no-stream
```

建议接入云监控或 UptimeRobot，探测 `https://example.com/health`。该接口会暴露数据库 / Redis 状态，如果不想公开，可以在 Nginx 限制来源 IP。

---

## 12. 故障排查

> 下面命令默认在 `/opt/zhiying-ai` 执行；`systemctl` / `journalctl` 用 root，`.venv` 与 `docker compose` 用 `zhiying`。

| 现象 | 优先检查 | 处理 |
| --- | --- | --- |
| 502 Bad Gateway | API 是否运行、端口是否 8010 | `systemctl status zhiying-api`、`journalctl`、`ss -lntp \| grep 8010` |
| `/health` 返回 `db: down` | 数据库容器、密码、`DATABASE_URL` | `docker compose ps`、`pg_isready`、确认 `POSTGRES_PASSWORD` 与 URL 一致 |
| `/health` 返回 `redis: down` | Redis 容器 / 连接串 | `docker compose ps`、`redis-cli ping`、确认 `REDIS_URL` |
| 登录成功但刷新掉线 | 是否 HTTPS、Cookie 是否 Secure、域名是否一致 | 用 `https://` 访问；确认 `COOKIE_SECURE=true` 与 `CORS_ORIGINS` 域名一致 |
| 注册收不到验证码 | SMTP 配置 / 授权码 / 网络 | 看 `app.log` 是否 `MAIL:console`；QQ 邮箱使用授权码；试 465 或 587 |
| AI 分析返回 503 | worker 是否运行、心跳是否存在 | `systemctl status zhiying-worker`；`docker compose exec -T redis redis-cli GET ai:worker:alive` |
| AI 分析一直不结束 | LLM Key / 网络 / 超时 | 看 worker 日志；确认服务器可访问 `LLM_BASE_URL`；检查 `LLM_JOB_TIMEOUT_SECONDS` |
| AI 进度不实时更新 | Nginx 是否缓冲 SSE | 确认 `/api/` 有 `proxy_buffering off`；刷新后自动回退轮询属于正常兜底 |
| 页面空白 / 刷新 404 | Nginx root、`/app/` 回退 | 确认 `root` 指向 `frontend/dist`；`/app/` 回退到 `app.html` |
| 发布后样式丢失 | HTML 被缓存、旧 assets 不存在 | 确认 `index.html` / `app.html` 使用 `expires -1`，重新生成 `dist` |
| 所有行情源失败 | 服务器出站网络 / 代理 | `curl` 腾讯 / 东财；检查安全组出站；必要时开启 `EGRESS_PROXY_ENABLED` |
| 选股报「行情/资金流数据暂不可用」 | 东财资金流排行是否可达、代理白名单 | 跑 `python -m app.scripts.check_proxy`，按结论开代理或给服务商加白名单 IP |
| 选股/分析报「AI 思考过程过长」 | 推理模型把 completion 额度用于思考，`finish_reason=length` | SenseNova 在 `default` 时会自动按 `none`；其他模型可显式设 `LLM_REASONING_EFFORT=none`，或提高 `LLM_ANALYST_MAX_TOKENS` / `LLM_FINAL_MAX_TOKENS`；重启 API + worker |
| 种子同步失败 | 东财访问被拦截 | 先 `--dry-run`；检查出站网络；启用行情代理后重试 |
| 定时任务不执行 | worker / LLM / 用户开关 / 额度 | 看 worker 日志；确认 LLM 已配置、任务已开启、当天额度未用完 |
| 迁移失败 | 数据库密码 / 连接 / 版本 | `pg_isready`、检查 `DATABASE_URL`；迁移前先备份 |
| 磁盘满 | 日志 / 备份 / Docker 层 | `du -sh /opt/zhiying-ai/backend/logs /var/backups/zhiying`；清理旧备份 |
| 邮件发出但进垃圾箱 | SPF / DKIM / 发件人 | 使用邮箱服务商建议配置；不要用登录密码代替授权码 |

常用诊断命令：

```bash
# API 日志
journalctl -u zhiying-api -n 200 --no-pager
journalctl -u zhiying-worker -n 200 --no-pager

# 端口
ss -lntp | grep -E ':80|:443|:8010|:5432|:6379'

# 后端配置自检
cd /opt/zhiying-ai/backend
.venv/bin/python -c "from app.core.config import settings; print(settings.llm_configured, settings.email_mode)"

# 行情出站代理自检（会实际请求一次东财；需要 .env，不需要数据库）
.venv/bin/python -m app.scripts.check_proxy

# 独立代理连通性（不读 .env、不连数据库）
.venv/bin/python scripts/test_proxy.py "http://user:pass@host:port"
```

---

## 13. 安全与上线前检查

### 13.1 必须确认

- [ ] `JWT_SECRET`、`OTP_SECRET` 已替换为随机值，未复用本地开发配置
- [ ] 数据库密码不是默认 `zhiying`，且 `DATABASE_URL` 与 `POSTGRES_PASSWORD` 一致
- [ ] PostgreSQL / Redis 只监听 `127.0.0.1`，云安全组未开放 5432 / 6379 / 8010
- [ ] `.env` 权限为 `600`，属主为 `zhiying`
- [ ] `DEBUG=false`、`COOKIE_SECURE=true`
- [ ] 全站 HTTPS，HTTP 自动跳转 HTTPS
- [ ] `CORS_ORIGINS` 只写正式域名，不使用 `*`
- [ ] `EMAIL_MODE=smtp`，不要把验证码长期打印到日志
- [ ] `/docs`、`/openapi.json` 没有对公网开放（本文只反代 `/api/` 与 `/health`）
- [ ] 服务器 SSH 使用密钥登录，按需关闭密码登录
- [ ] 数据库备份已配置，备份文件包含用户邮箱和报告，妥善保管
- [ ] 境内外数据源访问策略已确认；行情免费源和搜索服务的使用条款已阅读

### 13.2 公网运营注意

- 境内服务器绑定域名对外提供网站，通常需要完成 ICP 备案；未备案可能被云厂商拦截 80 / 443。
- 注册是开放的，新用户默认每天 5 次分析额度（`users.daily_analysis_quota`）。公网开放前评估 LLM 成本，必要时调整额度或限制注册。
- 当前没有全局限流；公网开放后建议在云 WAF / Nginx 对 `/api/v1/auth/email/send-code` 额外做频率限制，避免验证码接口被刷。
- 产品输出仅为技术研究参考，不构成投资建议；上线页面保留免责声明。

### 13.3 官网 SEO / 分享信息

正式域名确定后，修改 `frontend/index.html`：

- `canonical` 改为 `https://example.com/`
- `hreflang` 改为正式地址
- `og:image`、`twitter:image` 改为正式域名的绝对地址（建议同时补 `og:url`）
- 如需 sitemap，在 `frontend/public/sitemap.xml` 写入官网首页，并在 `robots.txt` 增加 `Sitemap: https://example.com/sitemap.xml`

改完重新执行 `npm run build`。

---

## 14. 命令速查

> `systemctl` / `journalctl` / `nginx` / `certbot` 用 root；`docker compose`、`npm`、`.venv` 用 `zhiying`。

```bash
# 服务
systemctl status zhiying-api zhiying-worker --no-pager
systemctl restart zhiying-api zhiying-worker
journalctl -u zhiying-worker -f

# 健康与心跳
curl -fsS http://127.0.0.1:8010/health; echo
cd /opt/zhiying-ai && docker compose exec -T redis redis-cli GET ai:worker:alive

# 数据库 / 缓存
cd /opt/zhiying-ai
docker compose ps
docker compose exec -T postgres pg_isready -U zhiying -d zhiying
docker compose exec -T redis redis-cli ping

# 迁移 / 种子
cd /opt/zhiying-ai/backend
.venv/bin/alembic upgrade head
.venv/bin/python -m app.scripts.seed_stocks

# 前端
cd /opt/zhiying-ai/frontend
npm ci
npm run build

# Nginx
nginx -t
systemctl reload nginx
tail -f /var/log/nginx/error.log

# 证书
certbot renew --dry-run
```

---

## 15. 目录与端口

```text
/opt/zhiying-ai/
├─ .env                        # 生产配置，600，zhiying:zhiying
├─ backend/
│  ├─ .venv/                   # uv 创建的虚拟环境
│  ├─ app/                     # FastAPI 应用
│  ├─ alembic/                 # 数据库迁移
│  └─ logs/                    # app.log / worker.log
├─ frontend/
│  ├─ dist/                    # npm run build 产物，Nginx root
│  └─ src/
├─ docker-compose.yml         全栈编排；裸机部署只用 postgres / redis
├─ scripts/docker-init.sh      生成 .env 与随机密钥
├─ docs/DOCKER.md              Docker 全栈一键部署
└─ docs/DEPLOYMENT.md          本文
```

| 端口 | 服务 | 暴露范围 |
| --- | --- | --- |
| 22 | SSH | 公网（按安全组限制来源） |
| 80 | Nginx HTTP | 公网，跳转 HTTPS / ACME |
| 443 | Nginx HTTPS | 公网 |
| 8010 | FastAPI | 仅 `127.0.0.1` |
| 5432 | PostgreSQL | 仅 `127.0.0.1` |
| 6379 | Redis | 仅 `127.0.0.1` |
| 5288 | Vite 开发服务器 | 仅本地开发，生产不使用 |
