# Video Editing

面向手机使用的个人 AI 视频剪辑平台：手机上传素材、描述要求、查看进度、预览和下载，计算在服务器完成。

当前已从需求文档补到**可运行的开源引擎验证工作台**：素材探测 → 结构化方案 → 覆盖校验 → 中文字幕/转场/声音处理 → MP4 与质量报告。手机页面、服务器队列、订阅执行器和点播对接仍待实现，尚未部署。

## 先运行，不需要模型 API 或 GPU

准备 Git、uv、Python 3.11–3.14、FFmpeg/ffprobe 和中文字体，然后在本仓库运行：

```sh
uv sync --locked
uv run editing doctor
uv run editing demo
uv run ruff check --no-cache .
uv run pytest
```

`demo` 使用自动生成的合成素材，实际调用 vedit 和 FFmpeg，检查 MP4 后自动清理临时文件。它不是 AI 动作理解测试。要保留可看的演示，使用 `uv run editing demo --output /交付目录/demo.mp4`。

首次安装固定 Git 提交的 vedit 和锁定依赖，需要网络。Python 依赖由 uv 共享缓存、硬链接复用；不下载大型识别模型、不读取模型登录状态、不调用付费 API。

[完整运行与交接手册](docs/agent-handoff.md) · [其他 agent 从这里开始](AGENTS.md)

下面是实际渲染的合成素材检查图，用来验证文字与片段切换，不是手机产品界面：

![合成素材渲染检查](docs/assets/render-preview.jpg)

## 本次补齐的能力

- 通用 `Plan` 与 JSON Schema，不绑定执行者或聊天会话；生成覆盖表、输入散列和规则快照。
- 按泳姿、出发、转身、辅助练习、水中技能分类；必需内容不能默默遗漏。
- 原素材与参考片严格区分；以连续画面确认完整动作，ASR/OCR 只作辅助证据。
- 自动计算重叠转场后的时长，禁止为了凑时长偷偷加速或截断已标记的完整动作区间。
- 当前动作标签与“接下来”预告分开；原声、静音、音乐、旁白模式明确。
- 复用固定提交的 vedit；适配 FFmpeg 9 参数变化，使用 Pillow 叠加中文字幕，兼容缺少 drawtext/libass 的环境。
- 输出技术检查与语义/观感审核分开。技术成功不会自动标记“所有动作正确”。

## 两个平台、两个仓库

| 平台 | 职责 |
| --- | --- |
| [video-2022](https://github.com/makewheels/video-2022) | 视频点播：上传、存储、转码、播放、下载 |
| video-editing | 剪辑：手机入口、工程、要求、规则、任务、版本、编辑方案、执行及质量报告 |

原素材和成片不提交 Git。用户只有现有编程助手订阅，没有模型 API 凭证；服务端订阅执行路线要单独验证，不能把付费 API 当默认前提。优先开源复用，不先重写完整编辑器。

## 文档与下一步

| 文档 | 内容 |
| --- | --- |
| [需求基线](docs/requirements.md) | 已确认目标、用户最新反馈、未决问题 |
| [架构与数据归属](docs/architecture.md) | 独立剪辑平台与已有点播平台的边界 |
| [服务端实施设计](docs/execution-design.md) | 任务包、状态机、版本、租约、手机 API 与验收 |
| [工具链](docs/toolchain.md) | FFmpeg 之外需要什么；必需、下一步与可选能力 |
| [开源调研与实测](docs/research.md) | 固定版本、实际故障与验证边界 |
| [开发交接](docs/agent-handoff.md) | 可直接执行的命令、输入输出与错误处理 |
| [下一步清单](docs/next-steps.md) | 分阶段工作与具体退出条件 |
| [游泳完整覆盖提示词](prompts/swimming-full-coverage.md) | 场景模板，不自动修改个人长期偏好 |
| [方案示例](examples/plan.json) / [JSON Schema](schemas/edit-plan.schema.json) | 编码与剪辑 agent 共用的结构化协议 |

当前验证范围请看 `docs/research.md`。本地实现、自动测试、真实素材语义审核、部署和手机真机验收分别记录。
