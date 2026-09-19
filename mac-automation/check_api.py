#!/usr/bin/env python3
"""接口变化哨兵：对比本地 AiToEarn 服务实时暴露的 OpenAPI 规范和上次快照。

原理：AiToEarn 后端在 {openapi_url}（默认 /docs/openapi.json）实时输出全部
接口定义。本脚本抽取发布脚本依赖的那几个接口的定义做指纹；接口一旦被
升级改动（路径没了、字段变了），指纹就对不上——立刻弹 macOS 通知并让
发布流程停下，而不是带着旧接口瞎发失败。

用法：
  python3 check_api.py            # 检查；有变化 -> 通知 + 退出码 2
  python3 check_api.py --accept   # 确认当前接口没问题，保存为新快照
退出码：0 一致 / 2 接口有变化 / 3 服务打不开
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT = os.path.join(HERE, ".api_snapshot.json")
CONFIG = os.path.join(HERE, "config.json")

# 发布脚本实际依赖的接口（method, path 后缀匹配）
WATCHED = [
    ("post", "/v2/channels/publish/flows"),
    ("get", "/v2/channels/publish/flows/{flowId}"),
    ("get", "/v2/channels/accounts"),
]


def notify(title, message):
    """macOS 桌面通知；非 mac 或失败时静默降级为打印。"""
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{message}" with title "{title}"'],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass
    print(f"[NOTIFY] {title}: {message}")


def resolve_refs(node, spec, depth=0):
    """浅层展开 $ref，让指纹覆盖请求体字段结构。"""
    if depth > 6:
        return node
    if isinstance(node, dict):
        if "$ref" in node and node["$ref"].startswith("#/"):
            target = spec
            for part in node["$ref"][2:].split("/"):
                target = target.get(part, {})
            return resolve_refs(target, spec, depth + 1)
        return {k: resolve_refs(v, spec, depth + 1) for k, v in sorted(node.items())}
    if isinstance(node, list):
        return [resolve_refs(v, spec, depth) for v in node]
    return node


def fingerprint(spec):
    paths = spec.get("paths", {})
    picked = {}
    missing = []
    for method, suffix in WATCHED:
        found = None
        for path, ops in paths.items():
            if path.endswith(suffix) and method in ops:
                found = resolve_refs(ops[method], spec)
                picked[f"{method.upper()} {path}"] = found
                break
        if found is None:
            missing.append(f"{method.upper()} ...{suffix}")
    digest = hashlib.sha256(
        json.dumps(picked, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return digest, picked, missing


def suggest_candidates(spec):
    """接口没了的时候，从实时规范里找疑似替代的发布接口报给用户。"""
    hits = []
    for path, ops in spec.get("paths", {}).items():
        if "publish" in path or "flows" in path:
            for method, op in ops.items():
                summary = op.get("summary", "") if isinstance(op, dict) else ""
                hits.append(f"  {method.upper()} {path}  {summary}")
    return hits[:15]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--accept", action="store_true", help="保存当前接口为新基准")
    args = ap.parse_args()

    with open(CONFIG) as f:
        cfg = json.load(f)
    openapi_url = cfg.get("openapi_url")
    if not openapi_url:
        # 默认从 base_url 推导: http://host:port/api -> http://host:port/docs/openapi.json
        root = cfg["base_url"].rstrip("/")
        if root.endswith("/api"):
            root = root[:-4]
        openapi_url = root + "/docs/openapi.json"

    try:
        with urllib.request.urlopen(openapi_url, timeout=30) as resp:
            spec = json.load(resp)
    except Exception as e:
        notify("AiToEarn 接口检查失败", f"打不开 {openapi_url}: {e}")
        print(f"无法获取 OpenAPI 规范 {openapi_url}: {e}", file=sys.stderr)
        print("请确认 AiToEarn 服务在运行，且配置里 openapi.enable 为 true。", file=sys.stderr)
        return 3

    digest, picked, missing = fingerprint(spec)

    if missing:
        notify("AiToEarn 接口变了", f"以下接口在服务里找不到了: {', '.join(missing)}")
        print("以下依赖接口不存在了：")
        for m in missing:
            print(f"  {m}")
        print("实时规范里疑似相关的接口：")
        for line in suggest_candidates(spec):
            print(line)
        return 2

    if args.accept or not os.path.exists(SNAPSHOT):
        with open(SNAPSHOT, "w") as f:
            json.dump({"digest": digest, "spec_version": spec.get("info", {}).get("version"),
                       "endpoints": sorted(picked)}, f, ensure_ascii=False, indent=2)
        print(f"已保存接口快照 ({len(picked)} 个接口, digest {digest[:12]}…)")
        return 0

    with open(SNAPSHOT) as f:
        old = json.load(f)

    if old["digest"] != digest:
        notify("AiToEarn 接口有改动",
               "发布接口的定义和上次不一样了，今天的自动发布已暂停，请检查。")
        print("接口指纹变化：")
        print(f"  旧: {old['digest'][:16]}…  (版本 {old.get('spec_version')})")
        print(f"  新: {digest[:16]}…  (版本 {spec.get('info', {}).get('version')})")
        print("当前接口列表：")
        for name in sorted(picked):
            print(f"  {name}")
        print("确认脚本兼容后运行: python3 check_api.py --accept")
        return 2

    print("接口无变化 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
