# Mac mini 每日全平台自动发视频（AiToEarn v2 新接口版）

AiToEarn 2.5 之后接口全面换成了 `/api/v2/` 开放平台接口（发布改为"创建发布
Flow"模型），旧接口的自动化脚本会全部失效。本目录是针对新接口重写的自动化，
并自带**接口变化哨兵**：AiToEarn 服务实时暴露的 OpenAPI 规范一旦和上次不同，
自动发布会立刻暂停并在 Mac 上弹通知，不会再出现"接口悄悄变了、发布静默失败"。

## 文件说明

| 文件 | 作用 |
|---|---|
| `aitoearn_client.py` | v2 接口客户端（纯标准库，无需 pip install） |
| `daily_publish.py` | 每日发布主脚本：检查接口 → 读队列 → 全平台发布 |
| `check_api.py` | 接口变化哨兵：对比实时 OpenAPI 规范指纹 |
| `config.example.json` | 配置模板 |
| `queue/example.json` | 发布任务模板 |
| `com.deerhui.aitoearn.daily.plist` | launchd：每天 9:00 自动发布 |
| `com.deerhui.aitoearn.apiwatch.plist` | launchd：每 30 分钟检测一次接口变化 |

## Mac mini 上的安装步骤

```bash
# 1. 把本目录拷到 Mac mini（示例路径，可自定，但要同步改两个 plist 里的路径）
mkdir -p ~/aitoearn-automation
cp -r mac-automation/* ~/aitoearn-automation/
cd ~/aitoearn-automation

# 2. 配置
cp config.example.json config.json
# 编辑 config.json：
#   base_url    = Docker 部署默认 http://127.0.0.1:8080/api（nginx 统一入口）
#   api_key     = AiToEarn 网页 设置 -> API Key 里生成（推荐）
#   openapi_url = Docker 部署为 http://127.0.0.1:8080/api/docs/openapi.json
#
# 注意：Docker 默认配置未开启 openapi 文档，需要在后端的 config.yaml
# （project/aitoearn-backend/apps/aitoearn-server/config/config.yaml）加上：
#     openapi:
#       enable: true
# 然后 docker restart aitoearn-server

# 3. 初始化接口快照（同时验证服务连通）
python3 check_api.py --accept

# 4. 演练一次（不真发）
cp queue/example.json queue/test.json   # 改成你的真实视频地址和文案
python3 daily_publish.py --dry-run

# 5. 装定时任务（先把两个 plist 里的 "你的用户名" 改成真实路径）
cp com.deerhui.aitoearn.*.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.deerhui.aitoearn.daily.plist
launchctl load ~/Library/LaunchAgents/com.deerhui.aitoearn.apiwatch.plist
```

## 日常使用

每天只需往 `queue/` 里放任务 JSON（一个文件 = 一次全平台发布）：

```json
{
  "title": "视频标题",
  "body": "文案 #话题",
  "media": ["https://视频地址.mp4"],
  "platforms": ["douyin", "tiktok", "youtube", "xhs", "wxSph", "bilibili"]
}
```

- `platforms` 不填 = 发到所有已授权账号
- 平台代号：`douyin` 抖音 / `xhs` 小红书 / `wxSph` 视频号 / `KWAI` 快手 /
  `bilibili` B站 / `wxGzh` 公众号 / `tiktok` / `youtube` / `facebook` /
  `instagram` / `threads` / `twitter` / `pinterest` / `linkedin`
- 视频 URL 必须是 AiToEarn 服务能访问到的地址（公网 URL，或云端版要求
  assets.aitoearn.ai / assets.aitoearn.cn 域名的素材地址）
- 发完的任务自动挪到 `done/`，失败的挪到 `failed/` 并弹通知
- 日志在 `logs/publish.log`

## 接口再变时会发生什么

1. `apiwatch` 每 30 分钟对比一次接口指纹，变了立刻弹 macOS 通知
2. 每天发布前 `daily_publish.py` 也会先检查，不一致就**停止发布**并通知，
   任务留在队列里不丢失
3. 你确认脚本仍兼容（或升级脚本后），运行 `python3 check_api.py --accept`
   保存新基准，发布自动恢复
4. 若接口路径整个消失，`check_api.py` 会把实时规范里疑似的新发布接口
   路径直接打印出来，方便快速对照修改
