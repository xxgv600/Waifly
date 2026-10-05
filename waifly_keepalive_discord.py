#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Waifly 账号自动保活脚本 (Discord OAuth Token 版 + Telegram 通知)
================================================================
原理: Waifly 在 15 天无活跃后停用账号。本脚本每 7~10 天自动走
Discord OAuth 流程登录一次:用 Discord user token 直接调用
discord.com/api/v9/oauth2/authorize 完成授权,拿到 code 后打开
Waifly 回调链接完成登录。登录即算活跃,防止账号被停用。

Waifly Discord OAuth 配置(2026-10-05 实测):
  client_id    = 1153754167689629716
  redirect_uri = https://dash.waifly.com/login
  scope        = identify guilds.join email

用法:
  1. 设置环境变量(不要硬编码 token):
     export DISCORD_TOKEN="你的 Discord user token"
     可选: export TG_BOT_TOKEN="bot123:abc..." TG_CHAT_ID="123456789"
           export GH_TOKEN="github pat"  # 自动更新 SESSION_TOKEN 用
  2. 手动测试:
     python3 waifly_keepalive_discord.py
  3. 定时执行(示例:每 7 天凌晨 3 点):
     crontab -e
     0 3 */7 * * cd /脚本目录 && DISCORD_TOKEN=... TG_BOT_TOKEN=... TG_CHAT_ID=... python3 waifly_keepalive_discord.py

依赖: pip install seleniumbase requests
"""

import os
import re
import sys
import time
import json
import subprocess
import urllib.parse
from datetime import datetime

import requests

try:
    from seleniumbase import SB
except ImportError:
    print("[FAIL] 缺少 seleniumbase,请先 pip install seleniumbase")
    sys.exit(1)

# ================= 配置区 =================
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN") or ""
GH_TOKEN      = os.environ.get("GH_TOKEN") or ""
TG_CHAT_ID    = os.environ.get("TG_CHAT_ID") or ""
TG_BOT_TOKEN  = os.environ.get("TG_BOT_TOKEN") or ""
SESSION_TOKEN = os.environ.get("SESSION_TOKEN") or ""

# 解析 DISCORD_TOKEN(兼容 "xxx,token" 格式)
DC_TOKEN = ""
if DISCORD_TOKEN:
    DC_TOKEN = DISCORD_TOKEN.split(",", 1)[-1].strip()

if not SESSION_TOKEN and not DC_TOKEN:
    print("[FAIL] 未配置 SESSION_TOKEN 和 DISCORD_TOKEN,脚本终止。")
    sys.exit(1)

# ---- Waifly Discord OAuth 配置 ----
DISCORD_CLIENT_ID  = "1153754167689629716"
OAUTH_REDIRECT_URI = "https://dash.waifly.com/login"
OAUTH_SCOPE        = "identify guilds.join email"
DISCORD_API        = "https://discord.com/api/v9/oauth2/authorize"
WAIFLY_LOGIN_URL   = "https://dash.waifly.com/login"
WAIFLY_DASH_URL    = "https://dash.waifly.com/"

DISCORD_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
)
STATE_RE = re.compile(r"[?&]state=([^&]+)")

_LOGIN_METHOD = "SESSION_TOKEN"


# ================= 工具函数 =================
def send_telegram_message(message: str):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("[TG] 未配置,跳过通知")
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": message,
                                 "disable_web_page_preview": True}, timeout=10)
        print("[TG] 通知发送成功")
    except Exception as e:
        print(f"[TG] 通知发送失败: {type(e).__name__}: {e}")


def format_notification(status: str, extra: str = "", error: str = "") -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = ["🔄 Waifly 保活通知", "", f"{status}"]
    if _LOGIN_METHOD != "SESSION_TOKEN":
        lines.append(f"🔐 登录方式: {_LOGIN_METHOD}")
    if extra:
        lines.append(extra)
    if error:
        lines.append(f"⚠️ 错误信息: {error}")
    lines.append(f"⏱️ 时间: {now}")
    return "\n".join(lines)


def update_github_secret(secret_name, new_value):
    if not new_value:
        return False
    print(f"🔄 更新 Secret: {secret_name}")
    try:
        env = os.environ.copy()
        if GH_TOKEN:
            env["GH_TOKEN"] = GH_TOKEN
        proc = subprocess.run(
            ["gh", "secret", "set", secret_name, "--body", new_value],
            capture_output=True, text=True, timeout=30, env=env)
        return proc.returncode == 0
    except Exception as e:
        print(f"❌ 更新异常: {e}")
        return False


# ================= Discord OAuth =================
def capture_discord_state(sb) -> str:
    """打开 Waifly 登录页,点击 Discord 按钮,从跳转 URL 提取 state"""
    print("🔎 打开 Waifly 登录页...")
    sb.uc_open_with_reconnect(WAIFLY_LOGIN_URL, reconnect_time=4)
    time.sleep(2)

    try:
        sb.click("#discordLogin")
        print("✅ 已点击 Discord 登录按钮")
    except Exception as e:
        print(f"❌ 点击 Discord 按钮失败: {e}")
        sb.save_screenshot("waifly_no_button.png")
        return ""

    time.sleep(3)
    url = sb.get_current_url()
    if "discord.com" not in url:
        print(f"⚠️ 未跳转到 Discord,当前 URL: {url[:100]}")
        sb.save_screenshot("waifly_no_redirect.png")
        return ""

    m = STATE_RE.search(url)
    if not m:
        print("❌ 未能从 URL 解析 state")
        return ""

    state = urllib.parse.unquote(m.group(1))
    print(f"✅ 已捕获 state: {state[:8]}...")
    return state


def discord_authorize(state: str) -> str:
    """用 Discord user token 直接完成授权,返回 Waifly 回调 URL"""
    query = urllib.parse.urlencode({
        "client_id":     DISCORD_CLIENT_ID,
        "response_type": "code",
        "redirect_uri":  OAUTH_REDIRECT_URI,
        "scope":         OAUTH_SCOPE,
        "state":         state,
    })
    authorize_url = f"{DISCORD_API}?{query}"

    headers = {
        "accept":           "*/*",
        "authorization":    DC_TOKEN,
        "content-type":     "application/json",
        "origin":           "https://discord.com",
        "referer":          f"https://discord.com/oauth2/authorize?{query}",
        "user-agent":       DISCORD_UA,
        "x-discord-locale": "zh-CN",
    }
    body = json.dumps({"permissions": "0", "authorize": True})

    try:
        resp = requests.post(authorize_url, headers=headers, data=body, timeout=20)
        if resp.status_code != 200:
            print(f"❌ Discord 授权失败: HTTP {resp.status_code} - {resp.text[:300]}")
            return ""
        location = resp.json().get("location", "")
    except Exception as e:
        print(f"❌ Discord 授权异常: {e}")
        return ""

    if not location:
        print("❌ 授权响应中无 location")
        return ""

    masked = re.sub(r"code=[^&]+", "code=***", location)
    print(f"✅ 拿到回调 URL: {masked[:90]}...")
    return location


def do_discord_login(sb) -> bool:
    """完整 Discord OAuth 登录流程"""
    global _LOGIN_METHOD
    _LOGIN_METHOD = "Discord Token"
    print("\n🔑 通过 Discord Token 登录 Waifly...")

    state = capture_discord_state(sb)
    if not state:
        return False

    location = discord_authorize(state)
    if not location:
        return False

    print("↩️ 打开回调链接完成登录...")
    sb.uc_open_with_reconnect(location, reconnect_time=4)
    time.sleep(4)

    for _ in range(60):
        url = sb.get_current_url()
        path = urllib.parse.urlparse(url).path
        if "dash.waifly.com" in url and path not in ("/login", "/login/"):
            print(f"✅ Discord OAuth 登录成功!当前页面: {url[:80]}")
            return True
        if "error" in url.lower():
            print(f"❌ 回调返回错误: {url[:120]}")
            sb.save_screenshot("waifly_oauth_error.png")
            return False
        time.sleep(0.5)

    print(f"❌ 登录超时: {sb.get_current_url()[:120]}")
    sb.save_screenshot("waifly_login_timeout.png")
    return False


# ================= 主流程 =================
def main():
    print("#" * 30)
    print("   Waifly Discord OAuth 自动保活")
    print("#" * 30)

    global _LOGIN_METHOD
    HEADLESS = os.environ.get("HEADLESS", "true").lower() == "true"

    with SB(uc=True, headless=HEADLESS) as sb:
        login_ok = False

        # 方式1: 已有 Waifly session 直接访问
        if SESSION_TOKEN:
            print("🍪 尝试用 SESSION_TOKEN 访问...")
            sb.open(WAIFLY_DASH_URL)
            time.sleep(3)
            url = sb.get_current_url()
            if "/login" not in urllib.parse.urlparse(url).path:
                login_ok = True
                print("✅ SESSION_TOKEN 仍有效")
            else:
                print("❌ SESSION_TOKEN 已失效")

        # 方式2: Discord OAuth
        if not login_ok and DC_TOKEN:
            print("\n🔄 尝试 Discord OAuth 登录...")
            if do_discord_login(sb):
                login_ok = True
            else:
                print("❌ Discord OAuth 登录失败")

        if not login_ok:
            send_telegram_message(format_notification("❌ 登录失败", error="所有登录方式均失败"))
            sys.exit(2)

        print("\n✅ 登录成功,账号已活跃")
        sb.open(WAIFLY_DASH_URL)
        time.sleep(3)

        # 尝试提取 session 供下次使用
        print("🔄 检查 session cookie...")
        for c in sb.get_cookies():
            name = c.get("name", "")
            if "session" in name.lower() or "token" in name.lower():
                val = c.get("value", "")
                print(f"📋 发现: {name} = {val[:6]}...{val[-4:]}")
                if GH_TOKEN and _LOGIN_METHOD == "Discord Token":
                    if update_github_secret("WAIFLY_" + name.upper(), val):
                        print(f"✅ {name} 已更新到 GitHub Secrets")

        send_telegram_message(format_notification("✅ 保活成功", extra="登录即算活跃,下次 7~10 天后再来"))
        print("🏁 执行完毕")


if __name__ == "__main__":
    main()
