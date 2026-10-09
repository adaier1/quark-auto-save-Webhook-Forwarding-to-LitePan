# quark-auto-save Webhook Forwarding to LitePan

将 [quark-auto-save](https://github.com/Cp0220/quark-auto-save) 的自定义通知转发到 LitePan 的自动联动接口，并在转发成功或失败时推送飞书机器人通知。

## 功能

- 接收 quark-auto-save 的自定义通知 Webhook
- 转发给 LitePan `/api/open/automation/events`
- 解析 `path`，支持从消息中提取路径
- 转发成功 / 失败时推送飞书机器人通知
- 如果消息内容仅为「好友已取消了分享」，则跳过转发
- 无第三方依赖，仅使用 Python 标准库

## 安装

```bash
python3 qas_to_litepan.py
```

## 环境变量

可复制 `.env.example` 并按实际情况修改：

| 变量 | 说明 |
| --- | --- |
| `LITEPAN_URL` | LitePan 地址，默认 `http://127.0.0.1:5211` |
| `LITEPAN_API_KEY` | LitePan 后台的 API 秘钥，必填 |
| `EVENT_NAME` | LitePan 自动联动规则里的事件名，默认 `quarkauto` |
| `SOURCE` | 事件来源标识，默认 `qas` |
| `LISTEN_PORT` | 监听端口，默认 `8000` |
| `SHARED_TOKEN` | 可选，Webhook 查询参数 `?token=xxx` 校验 |
| `FEISHU_WEBHOOK` | 可选，飞书机器人 Webhook，配置后成功或失败都会推送 |

## quark-auto-save 配置

系统设置 → 通知：

```text
WEBHOOK_URL = http://<本机IP>:8000/webhook
WEBHOOK_METHOD = POST
WEBHOOK_CONTENT_TYPE = application/json
WEBHOOK_BODY = {"title":"$title","content":"$content","path":"/tv"}
```

如果设置了 `SHARED_TOKEN`，`WEBHOOK_URL` 需要带上：

```text
http://<本机IP>:8000/webhook?token=你的token
```

## 跳过规则

当消息内容每一行都包含「好友已取消了分享」时，不会转发，直接返回：

```json
{"success": true, "skipped": true}
```

如果消息中同时包含新增、更新、文件路径等内容，则继续转发。

## systemd 开机自启

1. 复制脚本：

```bash
cp qas_to_litepan.py /opt/qas_to_litepan.py
```

2. 创建环境变量文件，权限设为 600：

```bash
cp .env.example /etc/qas-proxy.env
chmod 600 /etc/qas-proxy.env
```

3. 安装 service：

```bash
cp qas-proxy.service.example /etc/systemd/system/qas-proxy.service
systemctl daemon-reload
systemctl enable --now qas-proxy
```

4. 查看日志：

```bash
journalctl -u qas-proxy -f
```

## 测试

```bash
curl -X POST http://127.0.0.1:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{"title":"测试","content":"/tv test","path":"/tv"}'
```

## 安全提示

请勿把 `.env`、API 秘钥、飞书机器人 Webhook 提交到仓库。`.gitignore` 已忽略 `.env`。
