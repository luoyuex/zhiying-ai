#!/usr/bin/env sh
# 首次部署：生成 .env（随机密钥）并提示下一步。
# 用法：./scripts/docker-init.sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

if [ -f .env ]; then
    echo ".env 已存在，未覆盖。"
    echo "如需重新生成，先备份并删除 .env 再执行本脚本。"
    exit 0
fi

if ! command -v openssl >/dev/null 2>&1; then
    echo "缺少 openssl，无法生成随机密钥。请安装 openssl，或手动复制 .env.example 并填写 JWT_SECRET / OTP_SECRET。"
    exit 1
fi

cp .env.example .env
chmod 600 .env 2>/dev/null || true

jwt_secret=$(openssl rand -hex 32)
otp_secret=$(openssl rand -hex 32)
db_password=$(openssl rand -hex 16)

sed -i "s|^JWT_SECRET=.*|JWT_SECRET=${jwt_secret}|" .env
sed -i "s|^OTP_SECRET=.*|OTP_SECRET=${otp_secret}|" .env
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${db_password}|" .env
sed -i "s|^DATABASE_URL=.*|DATABASE_URL=postgresql+asyncpg://zhiying:${db_password}@localhost:5432/zhiying|" .env

echo "已生成 .env：JWT_SECRET / OTP_SECRET / 数据库密码均为随机值。"
echo
echo "下一步："
echo "  1. 编辑 .env，至少填写 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL"
echo "     （邮箱验证码如需真实发信，再改 EMAIL_MODE=smtp 与 SMTP_*）"
echo "  2. 设置 PUBLIC_APP_URL=http://服务器IP:8088（或正式域名），否则邮件里的报告链接指向本地"
echo "  3. 启动：docker compose up -d --build"
echo "  4. 首次启动后同步股票列表："
echo "     docker compose exec api .venv/bin/python -m app.scripts.seed_stocks"
