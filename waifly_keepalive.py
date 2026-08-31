#!/usr/bin/env python3
"""
Waifly 账号自动保活脚本
========================
原理: Waifly 在 15 天无活跃后停用账号。本脚本每 7~10 天自动调用
官方登录 API(source=app 通道,无需 reCAPTCHA),登录即算活跃,
从而防止账号被停用。

用法:
  1. 设置环境变量(不要硬编码密码):
     export WAIFLY_EMAIL="你的邮箱"
     export WAIFLY_PASSWORD="你的密码"
  2. 手动测试:
     python3 waifly_keepalive.py
  3. 定时执行(示例:每 7 天凌晨 3 点):
     crontab -e
     0 3 */7 * *  cd /路径 && WAIFLY_EMAIL=你的邮箱 WAIFLY_PASSWORD=你的密码 python3 waifly_keepalive.py >> waifly_keepalive.log 2>&1
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


def get_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        print(f"[FAIL] 缺少环境变量 {name},请先设置 WAIFLY_EMAIL / WAIFLY_PASSWORD")
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


def main() -> None:
    email = get_env("WAIFLY_EMAIL")
    password = get_env("WAIFLY_PASSWORD")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        data = login(email, password)
        token = data.get("token", "")
        user_id = data.get("id", "?")
        print(f"[OK] {now} 登录成功 → userId={user_id}, token长度={len(token)}")
        print("     账号活跃状态已刷新,15 天停用计时器已重置。")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        print(f"[FAIL] {now} 登录失败 HTTP {e.code}: {detail}")
        sys.exit(2)
    except Exception as e:
        print(f"[FAIL] {now} 异常: {type(e).__name__}: {e}")
        sys.exit(3)


if __name__ == "__main__":
    main()