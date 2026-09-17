# 本地成片交付到 video-2022

当前流程是本地剪辑后交付已有点播平台。手机自助上传、后台任务和自动对话调度仍未实现。用户明确要求上传后执行；不能只交电脑文件路径。

## 安装与账户

复用已有 `video-2022/cli` 的 profile 和 token，不重新登录、不输出 token。上传插件按需安装；纯渲染不需要网络依赖。

```sh
uv sync --locked --extra delivery
uv run --extra delivery --with /path/to/video-2022/cli editing deliver --help
```

`--with` 引用用户现有 CLI checkout；它提供 requests、oss2、账户配置与 API helpers。路径包含空格时加引号。CI 的离线适配器测试不依赖私人 CLI 配置；实际接入版本要由执行环境记录。`truststore` 使用操作系统可信证书，不关闭 TLS 验证。

## 上传与检查

```sh
uv run --extra delivery --with /path/to/video-2022/cli editing deliver /成片/v2.mp4 --receipt /工程/v2.delivery.json --title "动作展示·简洁版" --profile prod
```

- 默认 `UNLISTED`（持链接可看），不会出现在公开视频列表；需要登录保护时显式 `--visibility PRIVATE`。公开发布只有明确要求时使用 `PUBLIC`。
- 先完整解码检查，再创建视频、更新可见性、上传原片、通知完成；转码由现有平台执行，使用其正常资源。未新增付费模型接口或部署服务。
- 回执绑定文件 SHA-256 和目标环境，保存 video/file/watch ID；不保存 token、STS、签名 URL。回执放工程交付目录，勿入 Git。
- 默认等候 READY 最多 300 秒，可用 `--wait-seconds` 调整。超时或转码失败返回非零，并保留回执。
- READY 后检查所有 HLS 档位、时长与首尾分片解码。它不代替完整远端播放或手机真机验收；PRIVATE 链接要求对应账号登录。

只读复查已有视频：

```sh
uv run --extra delivery --with /path/to/video-2022/cli editing check-delivery --profile prod --video-id VIDEO_ID --watch-id WATCH_ID --expected-seconds 128.03
```

## 网络、失败与重试

2026-09-17 实测：直连站点失败；代理下 Python 默认 CA 验证失败，操作系统证书解决该问题。首条代理线路能调用 API，但 OSS PUT 写入超时；切换备用线路后完成上传。**API 能通不证明文件上传能通。**代理地址沿用执行环境的工作区配置，不写死在项目源码里。

PowerShell 示例（地址取当前环境的可用代理，不输出带密码的代理 URL）：

```powershell
$env:HTTP_PROXY = 'http://proxy-host:port'
$env:HTTPS_PROXY = $env:HTTP_PROXY
# 修复连接后，重新执行完全相同的 deliver 命令和 --receipt 路径
```

重试行为：

1. 收到创建响应后先保存 ID；以后复用该记录，不另建同名视频。
2. 创建请求响应丢失时，回执停在 `create_pending`。先核对平台记录并恢复 ID，工具不会盲目再次创建。
3. 上传失败时本次 SDK 分片记录放系统临时目录并清理；尽力取消本次未完成 multipart upload。断网导致远端取消失败时可能仍需 OSS 生命周期清理。下一进程重新传原片，不宣称跨进程分片续传。
4. 原片上传成功而通知失败时，`raw_uploaded` 阶段保留，不重传原片。已转码的视频重试只做状态和播放检查。
5. 同一回执只能由一个进程操作；没有分布式锁、队列、租约或 exactly-once 保证。损坏回执要人工核对，不丢弃后自动重建。

平台返回的 bucket/endpoint 才是上传目标；不能凭 profile 名或旧 README 猜测实际 bucket。不要将失败改成默认公开，也不要使用 `verify=False` 绕过证书问题。

## 交付话术

给出本次最终版本的播放页链接、时长、声音状态和本次主要改动。仅在平台 READY 且视频流检查通过后说“已可播放”。如果没有实际拿手机操作，写“视频流已检查，手机真机未测”，不要声称手机保存相册已通过。
