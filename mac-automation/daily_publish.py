#!/usr/bin/env python3
"""每日全平台自动发视频（AiToEarn v2 新接口版）。

流程：
 1. 先跑 check_api.py —— 接口和上次不一样就停下并弹通知，绝不带病发布
 2. 读 queue/ 里最旧的一个任务文件（JSON），内容示例见 queue/example.json
 3. 查询已授权账号，按任务里的 platforms 挑出账号
 4. 调 POST /v2/channels/publish/flows 一次发到所有平台
 5. 任务文件挪到 done/（失败挪到 failed/），日志写 logs/

用法：
  python3 daily_publish.py            # 发布队列里最旧的一个任务
  python3 daily_publish.py --all      # 把队列全部发完
  python3 daily_publish.py --dry-run  # 只演练不真发
"""

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys

from aitoearn_client import ApiError, client_from_config, load_config

HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE = os.path.join(HERE, "queue")
DONE = os.path.join(HERE, "done")
FAILED = os.path.join(HERE, "failed")
LOGS = os.path.join(HERE, "logs")


def log(msg):
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line)
    os.makedirs(LOGS, exist_ok=True)
    with open(os.path.join(LOGS, "publish.log"), "a") as f:
        f.write(line + "\n")


def run_api_check():
    r = subprocess.run([sys.executable, os.path.join(HERE, "check_api.py")],
                       capture_output=True, text=True)
    print(r.stdout, end="")
    if r.returncode != 0:
        log(f"接口检查未通过 (exit {r.returncode})，停止发布。")
        sys.exit(r.returncode)


def pick_accounts(client, wanted_platforms):
    accounts = client.list_accounts()
    if isinstance(accounts, dict):
        accounts = accounts.get("list") or accounts.get("items") or []
    chosen = []
    for acc in accounts:
        platform = acc.get("type") or acc.get("platform")
        acc_id = acc.get("id") or acc.get("_id") or acc.get("accountId")
        status = acc.get("status")
        if not platform or not acc_id:
            continue
        if wanted_platforms and platform not in wanted_platforms:
            continue
        if status not in (None, 1, "normal", "NORMAL", "active"):
            log(f"跳过失效账号 {platform}/{acc.get('nickname', acc_id)} (status={status})")
            continue
        chosen.append({"platform": platform, "accountId": acc_id,
                       "nickname": acc.get("nickname", "")})
    return chosen


def publish_one(client, task_path, dry_run=False):
    with open(task_path) as f:
        task = json.load(f)

    title = task["title"]
    body = task.get("body", "")
    media = task["media"] if isinstance(task["media"], list) else [task["media"]]
    platforms = task.get("platforms")  # 不填 = 发所有已授权平台
    publish_at = task.get("publishAt") or (
        datetime.datetime.now().astimezone() + datetime.timedelta(minutes=2)
    ).isoformat(timespec="seconds")

    items = pick_accounts(client, platforms)
    if not items:
        raise RuntimeError("没有匹配到任何已授权账号，请先在 AiToEarn 里授权平台账号")

    names = ", ".join(f"{i['platform']}({i['nickname']})" for i in items)
    log(f"任务 {os.path.basename(task_path)} -> {len(items)} 个账号: {names}")

    if dry_run:
        log("dry-run，未真正发布")
        return None

    flow_items = [{"platform": i["platform"], "accountId": i["accountId"]} for i in items]
    result = client.create_publish_flow(
        title=title, body=body, media_urls=media, items=flow_items,
        publish_at=publish_at, cover_url=task.get("cover"),
    )
    flow_id = result.get("flowId") or result.get("id") if isinstance(result, dict) else None
    log(f"已创建发布 Flow: {flow_id or result}")
    return flow_id


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="发布队列中全部任务")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-api-check", action="store_true")
    args = ap.parse_args()

    if not args.skip_api_check:
        run_api_check()

    cfg = load_config(os.path.join(HERE, "config.json"))
    client = client_from_config(cfg)

    os.makedirs(QUEUE, exist_ok=True)
    os.makedirs(DONE, exist_ok=True)
    os.makedirs(FAILED, exist_ok=True)

    tasks = sorted(
        f for f in os.listdir(QUEUE)
        if f.endswith(".json") and not f.startswith("example")
    )
    if not tasks:
        log("队列为空，没有要发布的任务。")
        return

    for name in (tasks if args.all else tasks[:1]):
        path = os.path.join(QUEUE, name)
        try:
            publish_one(client, path, dry_run=args.dry_run)
            if not args.dry_run:
                shutil.move(path, os.path.join(DONE, name))
        except (ApiError, RuntimeError, KeyError) as e:
            log(f"任务 {name} 失败: {e}")
            shutil.move(path, os.path.join(FAILED, name))
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "任务 {name} 发布失败，详见 logs/publish.log" '
                 'with title "AiToEarn 发布失败"'],
                capture_output=True,
            )
            sys.exit(1)


if __name__ == "__main__":
    main()
