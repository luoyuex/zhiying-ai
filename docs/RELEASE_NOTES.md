# 发布记录

本文记录需要服务器执行的更新步骤。日常发布流程见 [DEPLOYMENT.md](DEPLOYMENT.md) 第 11.2 节。

---

## 2026-10-24 · 定时任务结果邮件通知

### 本次更新

- 个人中心 → 定时任务新增「邮件通知」开关与「接收地址」，默认预填账号邮箱。
- 定时选股中已启用的策略默认收起参数，点「设置」展开，减少配置完成后的页面长度。
- 每日定时选股 / 定时分析自选股跑完后，把当天结果汇总成一封邮件发送：
  - 同一天、同一条任务线只发一封，不会每只股票发一封；
  - 同一时间段完成的选股与分析会合并成一封；
  - 等当天该任务线全部任务结束后再发；超过 `AUTOMATION_MAIL_WAIT_MINUTES`（默认 120 分钟）仍有任务在跑时，先发送已完成部分并注明；
  - 邮件包含个股评级 / 置信度 / 操作建议 / 摘要、各策略推荐名单与亮点、失败原因，以及报告详情和选股页链接。
- 设置接口新增 `email_notify_enabled`、`notify_email` 字段，数据库新增同名列。
- 邮件通知是可选能力：未开启或未填写地址时，定时任务照常执行，不会报错、也不会发信。
- 邮件发送逻辑与验证码邮件共用同一套 SMTP 配置。

### 影响范围

| 项目 | 说明 |
| --- | --- |
| 数据库 | `user_automation_settings` 新增 2 列，迁移版本 `a7b8c9d0e1f2` |
| 后端 API | 定时任务设置接口读写新字段 |
| 后端 worker | 新增每 5 分钟执行的汇总邮件检查 `run_automation_mail` |
| 前端 | 个人中心定时任务页新增邮件通知卡片，需要重新构建 |
| 依赖 | 无新增 Python / npm 依赖 |

> **worker 必须重启**：新邮件任务是 ARQ worker 的 cron，只重启 API 不会生效。

### 更新前确认

`.env` 中邮件配置可用（与注册验证码共用，未配置时邮件只会打印到日志）：

```env
EMAIL_MODE=smtp
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=你的发件邮箱
SMTP_PASSWORD=邮箱授权码
```

### 服务器更新步骤

按顺序执行，方括号内为执行身份。

#### 1. 备份数据库 `[zhiying]`

```bash
cd /opt/zhiying-ai
docker compose exec -T postgres pg_dump -U zhiying -d zhiying -Fc \
  | gzip > /var/backups/zhiying/zhiying-$(date +%F-%H%M).dump.gz
```

#### 2. 拉代码、装依赖、构建前端 `[zhiying]`

```bash
cd /opt/zhiying-ai
git pull --ff-only

cd /opt/zhiying-ai/backend
~/.local/bin/uv sync --frozen --no-dev --python 3.12

cd /opt/zhiying-ai/frontend
npm ci
npm run build
```

#### 3. 补充 `.env` 配置 `[zhiying]`

编辑 `/opt/zhiying-ai/.env`，新增以下键（`.env` 不在仓库中，必须手动添加）：

```env
# 站点根地址，用于邮件里的报告链接；不要带 /app 和末尾斜杠
PUBLIC_APP_URL=https://你的域名

# 可选：等待当天定时任务全部完成的最长分钟数，超时先发已完成部分
AUTOMATION_MAIL_WAIT_MINUTES=120
```

| 配置键 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `PUBLIC_APP_URL` | 是 | `http://127.0.0.1:5288` | 建议显式配置；不配置时邮件里的链接会指向本机地址 |
| `AUTOMATION_MAIL_WAIT_MINUTES` | 否 | `120` | 等待任务完成的上限；超出后发送已完成部分 |

#### 4. 停服务、执行迁移、启动 `[root]`

```bash
systemctl stop zhiying-api zhiying-worker
cd /opt/zhiying-ai/backend
.venv/bin/alembic upgrade head
systemctl start zhiying-worker zhiying-api
```

确认迁移只新增列、没有重建表：

```bash
cd /opt/zhiying-ai/backend
.venv/bin/alembic current
# 期望输出包含 a7b8c9d0e1f2 (head)
```

#### 5. 验收

- [ ] 个人中心 → 定时任务能看到「邮件通知」开关；打开后显示接收地址，默认是账号邮箱
- [ ] 保存后刷新页面，开关与地址仍然保留
- [ ] 数据库已新增列：

```bash
cd /opt/zhiying-ai
docker compose exec -T postgres psql -U zhiying -d zhiying -c \
  "select email_notify_enabled, notify_email from user_automation_settings limit 5;"
```

- [ ] 开启定时分析（或定时选股），把执行时间设到 5 分钟后，并填写可正常收信的地址
- [ ] 到点后（最多延迟 5 分钟）在历史报告 / 选股历史看到结果
- [ ] 收到汇总邮件，报告链接打开后指向 `PUBLIC_APP_URL` 对应的站点
- [ ] worker 日志出现发信记录：

```bash
grep -E "定时任务汇总邮件已发送|定时任务汇总邮件发送失败" \
  /opt/zhiying-ai/backend/logs/worker.log | tail
```

#### 6. 手动触发检查（可选）

如果不想等到设定时间，可在任务已落库后手动跑一次汇总检查。该命令有当天去重保护，重复执行不会重复发信：

```bash
cd /opt/zhiying-ai/backend
.venv/bin/python -c "
import asyncio
from app.db.redis import close_redis, get_redis
from app.services.automation_mail_service import send_due_digests

async def main():
    sent = await send_due_digests(get_redis())
    print('sent =', sent)
    await close_redis()

asyncio.run(main())
"
```

### 常见问题

| 现象 | 排查 |
| --- | --- |
| 完全没收到邮件 | 确认 `EMAIL_MODE=smtp`、SMTP 账号与授权码有效；看垃圾箱；日志出现 `[MAIL:console]` 说明没有走真实 SMTP |
| 邮件链接是 `127.0.0.1` | `.env` 的 `PUBLIC_APP_URL` 没配置或改完没重启 API / worker |
| 任务到点后一直不发 | 还在等待当天全部任务完成；到 `AUTOMATION_MAIL_WAIT_MINUTES` 后会先发已完成部分 |
| 当天改完设置但没有邮件 | 汇总邮件只针对「定时任务」，手动发起的分析不发邮件；同一天同一任务线已有发送记录时不会重发 |
| 重启后依旧没有新 cron | 确认重启的是 `zhiying-worker`，不是只重启了 `zhiying-api` |
| 想重发当天邮件 | 删除对应去重键后手动触发：`docker compose exec -T redis redis-cli --scan --pattern 'automation:mail:*'` 找到后 `DEL` |

### 回滚

1. 停服务：`systemctl stop zhiying-api zhiying-worker`
2. 代码切回上一个稳定 commit，`.env` 中删除 `PUBLIC_APP_URL` / `AUTOMATION_MAIL_WAIT_MINUTES`（可选）
3. 回滚迁移（会删除新列及已填写的接收地址）：`cd /opt/zhiying-ai/backend && .venv/bin/alembic downgrade -1`
4. 重新构建前端、启动服务：`systemctl start zhiying-worker zhiying-api`

如只回滚代码、不回滚数据库，旧代码会忽略新增列，功能不受影响，但建议保持 schema 与代码一致。
