# Waifly Account Keepalive

防止 Waifly 账号因 **15 天不活跃被停用** 的自动保活项目。

通过调用 Waifly 官方登录 API(`source=app` 通道,免 reCAPTCHA),每周自动登录一次,刷新活跃状态,避免账号被标记为 inactive。执行结果通过 **Telegram Bot 推送到你的 TG**。

## 原理

Waifly 会在账号连续 15 天无登录/无面板活动后发送停用邮件(账号数据保留,可手动在 Account Settings 点 Reactivate 恢复)。

本脚本周期性调用 `POST https://api.dash.waifly.com/login`(payload 中 `source: "app"`),登录即视为活跃,从而避免停用。

> 注:`source=app` 是应用端登录通道,不需要 Google reCAPTCHA 验证码,因此可以纯脚本实现。

## 项目结构

```
waifly-keepalive/
├── waifly_keepalive.py          # 保活脚本(纯标准库,零依赖,含TG通知)
├── .github/workflows/
│   └── waifly-keepalive.yml     # GitHub Actions 定时调度
├── requirements.txt             # 无第三方依赖(占位)
└── README.md
```

## 部署(public 仓库)

### 1. 创建 GitHub 仓库(Public / Private 均可)

本项目 **不包含任何密码**,凭证通过 GitHub Secrets 注入,公开仓库不会泄露信息。

### 2. 创建 Telegram Bot(如已有可跳过)

1. 在 Telegram 里找 **@BotFather**
2. 发送 `/newbot`,按提示起名,得到 Bot Token(格式 `123456:ABC...`)
3. 把你的 TG 用户 ID 发给机器人一次(或直接给机器人发条消息),用于获取 chat_id:
   - 也可以访问 `https://api.telegram.org/bot<TOKEN>/getUpdates` 查看 `chat.id`

### 3. 配置 Secrets

仓库 **Settings → Secrets and variables → Actions → New repository secret**,添加 4 个:

| Secret 名 | 值 |
|-----------|-----|
| `WAIFLY_EMAIL` | Waifly 登录邮箱 |
| `WAIFLY_PASSWORD` | Waifly 登录密码 |
| `TG_BOT_TOKEN` | Telegram Bot Token |
| `TG_CHAT_ID` | 你的 Telegram 用户/群组 ID |

### 4. 推送代码

```bash
git init
git add .
git commit -m "Add Waifly keepalive with TG notification"
git remote add origin https://github.com/<你的用户名>/waifly-keepalive.git
git push -u origin main
```

### 5. 手动触发测试

**Actions 页 → Waifly Account Keepalive → Run workflow**,观察:
- Actions 任务绿色通过;
- TG 收到 `✅ Waifly 保活成功` 通知。

### 6. 之后自动运行

| 触发方式 | 时间 |
|----------|------|
| 定时调度 | 每周一、周四 UTC 20:00(北京时间周二、周五 04:00) |
| 手动 | Actions 页随时 Run workflow |

## Telegram 通知效果

- **成功**:`✅ Waifly 保活成功 / 时间 / userId`
- **失败**:`❌ Waifly 保活失败 / HTTP 错误码 / 详情`
- 未配置 TG Secrets 时,通知自动跳过,不影响保活本身

## 本地运行(可选)

```bash
export WAIFLY_EMAIL="your@email.com"
export WAIFLY_PASSWORD="your-password"
export TG_BOT_TOKEN="123456:ABC..."
export TG_CHAT_ID="123456789"
python3 waifly_keepalive.py
```

## 安全说明

- 密码与 Bot Token **永不写入代码/仓库**,仅存于 GitHub Secrets
- 脚本支持环境变量注入,便于迁移到任何 CI/CD 平台(如 Northflank cron)
- 登录失败会以非零退出码退出,触发 GitHub 失败告警邮件

## 常见问题

**Q: 登录失败(401 Invalid email or password)?**
A: 检查 Secrets 中的邮箱/密码是否正确;若账号已停用,先在 dash.waifly.com 手动激活一次。

**Q: TG 没收到通知?**
A: 检查 `TG_BOT_TOKEN` / `TG_CHAT_ID` 是否已配置;Bot 是否已与你的账号建立会话(向 Bot 发过消息);Chat ID 是否正确(可能带 `-` 前缀用于群组)。

**Q: 会不会太频繁触发风控?**
A: 每周 2 次远低于人工登录频率;15 天窗口留足余量,即使某次失败也有下一次兜底。

**Q: 为什么用 `source=app`?**
A: 网页端登录强制 Google reCAPTCHA(需浏览器+人机验证),应用端通道允许 `recaptchaToken: null`,适合纯脚本自动化。

## License

MIT