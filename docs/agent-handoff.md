# 其他 agent 的运行手册

## 编码 agent：干净环境启动

需要 Git、Python 3.11–3.14、uv、系统 FFmpeg/ffprobe、中文字体。Linux 建议先验证 Ubuntu 24.04；macOS 可用于开发；Windows 优先 WSL，原生 Windows 暂无端到端证据。

```sh
git clone https://github.com/makewheels/video-editing.git
cd video-editing
uv sync --locked
uv run editing doctor
uv run editing demo
uv run ruff check --no-cache .
uv run pytest
```

Linux 缺系统依赖时安装 `ffmpeg` 和 `fonts-noto-cjk`。已有 FFmpeg 不要盲目重装。`doctor` 会显示滤镜和字体能力；支持 `EDITING_FONT` 或命令的 `--font` 参数指定中文字体。不能只因字体文件存在就宣称所有字符显示正确，仍需检查预览。

`demo` 真正生成两条视频，创建方案，调用 vedit 编译及 FFmpeg 渲染，检查时长、画面规格、静音和完整解码。默认所有演示文件自动清理；需要查看成片时明确给出持久输出路径：

```sh
uv run editing demo --output /你选择的交付目录/demo.mp4
```

输出包括视频和 `.report.json`。合成源文件会清理；重现演示重新执行同一命令。这个演示没有执行 AI 理解，不是产品已完成的证明。

## 剪辑 agent：真实素材协议

1. 从工程任务包读取本次需求、素材清单、素材角色、规则快照和未决问题。工程必须能脱离对话会话恢复。
2. 对所有素材执行 `inspect`，再按需要生成代理、场景边界和连续短预览。联系表只用于定位，不能仅凭一帧确认完整动作。
3. 列出 `contents`：每种独有内容、类别、确认状态和证据区间。同一内容可以有多个候选区间；独有角度或教学要点单独列项。
4. 写入 `Plan`。连续画面证据的区间表示要完整保留的动作周期；ASR、OCR 仅作辅助证据。先解决 `uncertain` 项，不能伪造已确认状态以绕过校验。
5. 按相关内容组织片段，在动作周期外安排转场和字幕预告。标签语义对应当前画面；预告必须带“接下来”字样。
6. `validate` 成功后再 `render`，交付前复核所有独有内容和剪辑边界。

```sh
uv run editing inspect /素材根目录/视频.mp4 --sheet /交付目录/联系表.jpg
uv run editing schema
uv run editing validate /工程目录/plan.json --asset-root /素材根目录
uv run editing render /工程目录/plan.json --asset-root /素材根目录 --output /交付目录/v1.mp4
```

`examples/plan.json` 是完整结构示例，可对照 `schemas/edit-plan.schema.json` 编写。素材路径相对 `--asset-root`；禁止绝对路径、外部 URL 和逃逸根目录的符号链接。服务端将视频 ID 下载到受限任务目录后再调用这套协议，不直接把用户提交的下载地址交给 FFmpeg。

## 输入和结果

| 数据 | 约定 |
| --- | --- |
| 时间 | 秒；片段是 `[source_in, source_out)`；源时间、成片时间、ASR 时间分别保存 |
| 转场 | `transition_out` 是当前片段尾部与下一片段重叠的时长；总时长须减去重叠 |
| 动作证据 | 与选取素材相同的 `continuous_visual` 区间必须完整位于无转场覆盖的区间内 |
| 参考视频 | 默认禁止入成片；例外必须在本次需求中有依据，并保存 `reference_use_reason` |
| 声音 | `mute` / `source` / `music` / `voiceover`，必须明确；外加音轨要求素材 ID 与来源说明 |
| 音轨不足 | 报错，不偷偷循环或拉伸旁白；旁白生成应放到画面确认之后 |
| 输出 | MP4 + 报告，覆盖表包含源时间与成片时间、类别、素材散列、规则快照和引擎版本 |
| 完成标志 | 技术检查通过只代表文件正确；报告的语义、视觉审核仍为 `pending`，不能自动改成通过 |

字幕按内容类别显示，出发技巧不会被计入泳姿。工具不会自动纠正一个被错误分类的动作；这仍需语义审核。

## 失败与交接

命令成功返回退出码 0 和 JSON；环境缺失、验证失败或执行失败返回非零。取消返回 130，超时终止当前子进程并清理临时目录。当前 CLI 没有常驻队列或自动重试；不要宣传关闭服务器进程后任务会继续。

发生问题保存：工程 ID/版本、可分享的错误类型、已验证阶段、输入散列、工具版本、下一步。不要打印登录信息或带签名的素材 URL。不依赖之前的执行者、聊天 ID 或隐藏提示。

改动 `contracts.py` 后更新 schema：

```sh
uv run editing schema > schemas/edit-plan.schema.json
```

增加能力时遵循 `inspect → plan → validate → render → verify → review`。模型负责证据和决策；工具执行可检查的方案。不要为每个模型维护一套剪辑实现。
