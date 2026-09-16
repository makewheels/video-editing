# 开源项目与 Codex 调研

调研日期：2026-09-16。以下基于仓库和官方文档，未安装或实测，不构成可用性保证。

## 优先候选

| 项目 | 文档描述的能力 | 评估重点 |
| --- | --- | --- |
| [vedit / editorvideo-ai](https://github.com/metiu1/editorvideo-ai) | 网页时间线、工程保存、FFmpeg 渲染、CLI/MCP，Codex 可调用，MIT | 优先验证真实素材剪辑、服务端渲染、工程重开和手机适配；不能因功能表完整就假设成熟 |
| [AI Video Editor](https://github.com/MartinDelophy/ai-video-editor) | 网页编辑、可保存时间线、字幕音轨、Codex 技能、浏览器导出 | 检查能否将渲染留在服务器，避免手机承担主要计算 |
| [Video Edit CLI](https://github.com/computerlovetech/video-edit-cli) | Agent 技能、素材分析、剪辑计划、字幕、音频和导出，MIT | 适合作为服务器执行底座；手机页面和任务管理需要补充 |

建议先验证 vedit；底座尚未最终选定。采用代码时保留上游许可证和署名要求，检查依赖许可证。

## 其它参考

- [CutAI](https://github.com/mindsurf0176/cutai)：EDITSTYLE.md 风格文件、计划与对话剪辑；项目自述 alpha，可借鉴规则表达。
- [Auto-Editor](https://github.com/WyattBlue/auto-editor)：基于音量等信号的自动裁切；不能直接解决泳姿语义分类。
- [OpenCut](https://github.com/OpenCut-app/OpenCut)：开源网页编辑器候选，尚未深入核对服务器执行路径。
- [Multica](https://github.com/multica-ai/multica)：Agent 任务与协作管理，不是剪辑工程数据库，也不是第一期必需依赖。
- Copyparty、File Browser、Uppy/tusd 曾作为文件上传下载备选调研；既有 video-2022 可复用，暂不计划额外部署网盘。

## Codex 订阅约束

用户没有模型 API Key。此前“直接调用 GPT-6 API”的建议已被纠正，不作为实施前提。

官方资料：

- [Authentication](https://learn.chatgpt.com/docs/auth)：支持 ChatGPT 登录及远程环境设备码登录；官方对程序化工作流推荐 API 认证。
- [Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)：codex exec 可用于脚本执行。
- [GPT-6 Astra guidance](https://developers.openai.com/api/docs/guides/latest-model)：模型能力背景，不代表用户拥有对应 API 使用权。

候选路线为用户自己的服务器运行官方 Codex，驱动开源剪辑工具，手机通过私人入口提交任务。需要实测账号可用性、模型权限、额度及执行方式；不能将订阅等同于可对外提供的通用 API 服务，不提取登录令牌冒充 API Key。

## 本次已有证据

- Windows 素材目录有 10 条素材和 1 条参考视频。
- Mac 下载目录发现当天游泳成片，ffprobe 显示约 120.15 秒、720×1280、H.264/AAC。
- 通过抽帧观察标题和画面，发现泳姿、出发及其它技能混排；没有完整听看，音画错位判断来自用户反馈。
- video-2022 本地代码和文档已有上传、存储、转码、播放、原片下载链接及视频管理 Agent；本次未发现现有 Agent 中已有剪辑执行能力。
- 没有执行手机保存相册验证，没有跑候选开源项目测试，没有部署服务。
