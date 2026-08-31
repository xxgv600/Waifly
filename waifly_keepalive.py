#!/usr/bin/env python3
"""
Waifly 账号自动保活脚本(含 Telegram 通知)
==========================================
原理: Waifly 在 15 天无活跃后停用账号。本脚本每 7~10 天自动调用
官方登录 API(source=app 通道,无需 reCAPTCHA),登录即算活跃,
从而防止账号被停用。执行结果可选推送到 Telegram。

用法:
  1. 设置环境变量(不要硬编码密码):
     export WAIFLY_EMAIL="你的邮箱"
     export WAIFLY_PASSWORD="你的密码"
     可选: export TG_BOT_TOKEN="bot123:abc..." TG_CHAT_ID="123456789"
  2. 手动测试:
     python3 waifly_keepalive.py
  3. 定时执行(示例:每 7 天凌晨 3 点):
     crontab -e
     0 3 */7 * *  cd /路径 && WAIFLY_EMAIL=... WAIFLY_PASSWORD=... TG_BOT_TOKEN=... TG_CHAT_ID=... python3 waifly_keepalive.py
"""
import os
import sys
import json
import datetime
import urllib.request
import urllib.error

API_URL = "https://api.dash.waifly.com/login"
ORIGIN = "https://dash.waifly.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

TG_BASE = "https://api.telegram.org/bot{token}/sendMessage"


def get_env(name: str, required: bool = True) -> str:
    val = os.environ.get(name, "").strip()
    if not val and required:
        print(f"[FAIL] 缺少环境变量 {name},请先设置")
        sys.exit(1)
    return val


def login(email: str, password: str) -> dict:
    """调用 Waifly 官方登录 API(source=app 免验证码通道)"""
    body = json.dumps({
        "email": email,
        "password": password,
        "recaptchaToken": None,   # app 通道允许 null
        "source": "app",
    }).encode("utf-8")

    req = urllib.request.Request(API_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Origin", ORIGIN)
    req.add_header("Referer", ORIGIN + "/login")
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "application/json, text/plain, */*")

    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def send_tg_notification(text: str) -> None:
    """发送 Telegram 通知;未配置 token/chat_id 则静默跳过"""
    token = os.environ.get("TG_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TG_CHAT_ID", "").strip()
    if not token or not chat_id:
        return

    url = TG_BASE.format(token=token)
    body = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }).encode("utf-8")

    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        print("[TG] 通知发送成功")
    except Exception as e:
        print(f"[TG] 通知发送失败: {type(e).__name__}: {e}")


def main() -> None:
    email = get_env("WAIFLY_EMAIL")
    password = get_env("WAIFLY_PASSWORD")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    node = "GitHub Actions" if os.environ.get("GITHUB_ACTIONS") == "true" else "本地"

    try:
        data = login(email, password)
        token = data.get("token", "")
        user_id = data.get("id", "?")
        msg = f"✅ Waifly 保活成功\n时间: {now} ({node})\nuserId: {user_id}"
        print(f"[OK] {now} 登录成功 → userId={user_id}, token长度={len(token)}")
        send_tg_notification(msg)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        err = f"❌ Waifly 保活失败\n时间: {now} ({node})\nHTTP {e.code}: {detail}"
        print(f"[FAIL] {now} 登录失败 HTTP {e.code}: {detail}")
        send_tg_notification(err)
        sys.exit(2)
    except Exception as e:
        err = f"❌ Waifly 保活异常\n时间: {now} ({node})\n{type(e).__name__}: {e}"
        print(f"[FAIL] {now} 异常: {type(e).__name__}: {e}")
        send_tg_notification(err)
        sys.exit(3)


if __name__ == "__main__":
    main()