#!/usr/bin/env python3
"""AiToEarn v2 开放接口客户端（仅用 Python 标准库，Mac 自带 python3 即可运行）。

对应 2.5+ 版本的新接口：
  POST /api/v2/channels/publish/flows   创建多平台发布 Flow
  GET  /api/v2/channels/publish/flows/{flowId}  查询 Flow 状态
  GET  /api/v2/channels/accounts        已授权账号列表

认证方式二选一（写在 config.json 里）：
  "api_key": "..."  -> 请求头 X-Api-Key
  "token": "..."    -> 请求头 Authorization: Bearer
"""

import json
import ssl
import urllib.error
import urllib.request

DEFAULT_TIMEOUT = 60


class ApiError(RuntimeError):
    def __init__(self, status, url, body):
        super().__init__(f"HTTP {status} {url}: {body[:300]}")
        self.status = status
        self.url = url
        self.body = body


class AiToEarnClient:
    def __init__(self, base_url, api_key=None, token=None, verify_tls=True):
        # base_url 例: http://127.0.0.1:3000/api  (含全局前缀，不含 /v2)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.token = token
        self.ctx = None
        if not verify_tls:
            self.ctx = ssl.create_default_context()
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE

    def _request(self, method, path, payload=None):
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT, context=self.ctx) as resp:
                body = resp.read().decode()
        except urllib.error.HTTPError as e:
            raise ApiError(e.code, url, e.read().decode(errors="replace")) from e
        result = json.loads(body) if body else {}
        # 兼容 {code, data, message} 包装和裸数据两种返回
        if isinstance(result, dict) and "data" in result and ("code" in result or "message" in result):
            return result["data"]
        return result

    # ---- 账号 ----
    def list_accounts(self):
        return self._request("GET", "/v2/channels/accounts")

    # ---- 发布 ----
    def create_publish_flow(self, title, body, media_urls, items,
                            publish_at, cover_url=None, flow_id=None):
        """items: [{"platform": "douyin", "accountId": "..."}, ...]
        publish_at: ISO8601 字符串, 例 2026-09-20T09:00:00+08:00"""
        content = {
            "title": title,
            "body": body,
            "media": [{"url": u} for u in media_urls],
        }
        if cover_url:
            content["cover"] = {"url": cover_url}
        payload = {
            "content": content,
            "publishAt": publish_at,
            "items": items,
        }
        if flow_id:
            payload["flowId"] = flow_id
        return self._request("POST", "/v2/channels/publish/flows", payload)

    def get_flow(self, flow_id):
        return self._request("GET", f"/v2/channels/publish/flows/{flow_id}")


def load_config(path):
    with open(path) as f:
        return json.load(f)


def client_from_config(cfg):
    return AiToEarnClient(
        base_url=cfg["base_url"],
        api_key=cfg.get("api_key"),
        token=cfg.get("token"),
        verify_tls=cfg.get("verify_tls", True),
    )
