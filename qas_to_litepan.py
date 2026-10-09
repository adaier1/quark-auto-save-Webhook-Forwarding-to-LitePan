#!/usr/bin/env python3
"""接收 quark-auto-save 的自定义通知 Webhook,转发给 LitePan 的自动联动接口。

用法:
    python qas_to_litepan.py

quark-auto-save 配置(系统设置 - 通知):
    WEBHOOK_URL    = http://<本机IP>:8000/webhook
    WEBHOOK_METHOD = POST
    WEBHOOK_CONTENT_TYPE = application/json
    WEBHOOK_BODY   = {"title":"$title","content":"$content","path":"/tv"}

环境变量:
    LITEPAN_URL      LitePan 地址, 默认 http://127.0.0.1:5211
    LITEPAN_API_KEY  LitePan 后台 - 系统设置 - API 秘钥(普通秘钥), 必填
    EVENT_NAME       转发给 LitePan 的事件名, 需与 LitePan 自动联动规则里的事件名一致, 默认 quarkauto
    LISTEN_PORT      监听端口, 默认 8000
    SHARED_TOKEN     可选, QAS 的 WEBHOOK_URL 带上 ?token=xxx 校验
    FEISHU_WEBHOOK   飞书机器人 webhook, 转发成功/失败都会推送
"""

import json
import os
import re
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

LITEPAN_URL = os.environ.get("LITEPAN_URL", "http://127.0.0.1:5211").rstrip("/")
LITEPAN_API_KEY = os.environ.get("LITEPAN_API_KEY", "")
EVENT_NAME = os.environ.get("EVENT_NAME", "quarkauto")
SOURCE = os.environ.get("SOURCE", "qas")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "8000"))
SHARED_TOKEN = os.environ.get("SHARED_TOKEN", "")
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")


def forward_litepan(event: dict) -> tuple[int, str]:
    body = json.dumps(event).encode("utf-8")
    req = urllib.request.Request(
        f"{LITEPAN_URL}/api/open/automation/events",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LITEPAN_API_KEY}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except Exception as exc:
        return 502, str(exc)


def feishu_notify(title: str, content: str) -> None:
    if not FEISHU_WEBHOOK:
        return
    data = json.dumps({"msg_type": "text", "content": {"text": f"{title}\n\n{content}"}}).encode("utf-8")
    req = urllib.request.Request(
        FEISHU_WEBHOOK,
        data=data,
        headers={"Content-Type": "application/json;charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8", "replace"))
        if result.get("StatusCode") == 0 or result.get("code") == 0:
            print("飞书 推送成功")
        else:
            print(f"飞书 推送失败: {result}")
    except Exception as exc:
        print(f"飞书 推送失败: {exc}")


def should_skip(content: str) -> bool:
    lines = [line for line in content.splitlines() if line.strip()]
    return bool(lines) and all("好友已取消了分享" in line for line in lines)


def extract_path(content: str, payload: dict) -> str:
    if payload.get("path"):
        return str(payload["path"])
    match = re.search(r"(/[^\n]*?)(?:新增|更新|$title|文件)", content) or re.search(r"^(/[^\s]+)", content)
    return match.group(1).strip() if match else ""


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        parsed = urlparse(self.path)
        if SHARED_TOKEN and parse_qs(parsed.query).get("token", [""])[0] != SHARED_TOKEN:
            self.reply(403, json.dumps({"error": "invalid token"}))
            return

        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            payload = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            payload = {"content": raw.decode("utf-8", "replace")}

        if not isinstance(payload, dict):
            payload = {"content": str(payload)}

        content = str(payload.get("content", ""))
        if should_skip(content):
            print(f"[{self.log_date_time_string()}] 跳过(仅好友已取消了分享): {content}")
            self.reply(200, json.dumps({"success": True, "skipped": True}, ensure_ascii=False))
            return
        event = {
            "event": str(payload.get("event") or EVENT_NAME),
            "source": str(payload.get("source") or SOURCE),
            "path": extract_path(content, payload),
            "message": str(payload.get("message") or content),
        }

        status, text = forward_litepan(event)
        print(f"[{self.log_date_time_string()}] {json.dumps(event, ensure_ascii=False)} -> {status} {text}")

        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            result = None
        ok = status == 200 and isinstance(result, dict) and result.get("success")
        notify_title = "QAS→LitePan 转发成功" if ok else "QAS→LitePan 转发失败"
        notify_content = f"{payload.get('title', '')}\n{content}"
        if ok:
            triggered = (result.get("data") or {}).get("triggered") or []
            names = ", ".join(str(t.get("name")) for t in triggered)
            if names:
                notify_content += f"\n触发规则: {names}"
        else:
            notify_content += f"\nHTTP {status} {text[:200]}"
        feishu_notify(notify_title, notify_content)

        self.reply(status, text)

    def reply(self, status: int, text: str):
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    if not LITEPAN_API_KEY:
        raise SystemExit("请设置环境变量 LITEPAN_API_KEY")
    print(f"监听 :{LISTEN_PORT} -> {LITEPAN_URL}/api/open/automation/events (event={EVENT_NAME})")
    ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), Handler).serve_forever()
