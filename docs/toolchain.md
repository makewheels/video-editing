# AI 剪辑工具链

FFmpeg 负责执行剪辑，但不会判断“这个动作是不是蛙泳”或“周期是否完整”。需要把视觉理解、音频理解、可编辑时间线和验收工具配在一起。下表区分本仓库已接入与候选，避免默认安装全部大型模型。

## 最小必需工具

| 工具 | 用来解决什么问题 | 当前状态 |
| --- | --- | --- |
| [FFmpeg](https://ffmpeg.org/ffmpeg.html) | 裁切、缩放、转场、音频、H.264 导出、完整解码检查 | 已运行；CPU 基线，不强制 GPU |
| [ffprobe](https://ffmpeg.org/ffprobe.html) | 时长、旋转、帧率、编码、音轨和 HDR 元数据 | 已接入；不能仅按扩展名或文件大小验收 |
| [vedit](https://github.com/metiu1/editorvideo-ai) | 持久化原生工程、时间线、转场和 FFmpeg 图编译 | 已固定 Git 提交接入验证层，产品底座未最终定案 |
| [Pillow](https://pillow.readthedocs.io/en/stable/) + [Noto CJK](https://github.com/notofonts/noto-cjk) | 清楚的中文字幕、分组标签、联系表 | 已接入；PNG 叠加可适应不含 drawtext 的 FFmpeg |
| 结构化方案、散列、测试 | 可重跑、内容覆盖、版本追踪、自动发现坏片 | 已接入；自动检查不替代语义审片 |

完整服务器 FFmpeg 可额外启用 libass；用于多行字幕样式、字幕文件烧录。当前动作标签不依赖它。不要因 `ffmpeg -version` 能运行就认为所有滤镜都存在。[滤镜官方说明](https://ffmpeg.org/ffmpeg-filters.html)

## 素材理解与声音工具

| 工具 | 建议用途 | 接入优先级与边界 |
| --- | --- | --- |
| [PySceneDetect](https://www.scenedetect.com/docs/latest/api/detectors.html) | 找镜头切换和候选片段，节省逐帧分析成本 | 下一步；镜头边界不等于动作边界，水花和运动可能误触发 |
| [OpenCV](https://docs.opencv.org/4.x/) / PyAV | 连续帧采样、清晰度/重复检测、跟踪、构图辅助 | 下一步；目标跟踪和姿态点不能单独证明泳姿类别 |
| 可看连续帧或短视频的视觉模型 | 识别动作、完整周期、独有内容、字幕避让区域 | 必须验证现有订阅执行器的实际可视能力，不默认另购 API；不能只做 ASR 剪辑 |
| [whisper.cpp](https://github.com/ggml-org/whisper.cpp) 或 [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | 转写现场语音，为内容提供辅助证据 | 可选其一：前者便于 CPU/Apple Silicon，后者可评估 Linux CPU int8 / GPU；模型下载到共享缓存 |
| [WhisperX](https://github.com/m-bain/whisperX) | 更细的语音时间对齐；必要时分离说话人 | 需要逐字字幕才评估；对齐讲话不代表对齐了画面动作，部分附加模型需账号授权 |
| [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) | 读取参考片已有字幕，判断文字区域 | 可选；OCR 文字也可能写错，不把 Mac 专有 OCR 作为服务器必需依赖 |
| [librosa](https://github.com/librosa/librosa) | 音乐节拍、能量变化、可选的节奏辅助 | 有音乐需求再接；不能为了卡点切断教学动作 |
| [Piper](https://github.com/OHF-Voice/piper1-gpl) 等本地 TTS | 画面确定后生成旁白 | 后续验证中文自然度、音色及模型授权；引擎和声音模型许可证分别核实 |
| FFmpeg loudnorm / sidechaincompress | 响度、限峰、旁白时降低背景音乐 | 后续混音阶段；当前只支持选定单一音轨，不宣称已实现旁白+音乐自动混音 |

没有可用音乐时，依场景模板生成静音方案并说明。不会自动下载来源不明的音乐，不把公开视频中的背景乐当成自有素材。不要默认使用依赖非正式接口的在线语音服务作为生产基础。

## 工程与平台工具

- [OpenTimelineIO](https://github.com/AcademySoftwareFoundation/OpenTimelineIO)：第二阶段评估时间线交换。它表达剪辑关系，不负责视频渲染，不能保证所有引擎特效无损互转。
- 对象存储与上传：优先复用 video-2022；需要断点续传时再评估 Uppy/tusd，避免重复造上传服务。
- 数据库与任务队列：建议 PostgreSQL 保存工程、版本、租约和任务状态；初期单 worker 也要有持久任务，规模增长后再决定是否引入 Redis 队列。**这是待实施建议。**
- 观测：每阶段耗时、失败类型、资源使用、模型调用状态、输入散列、引擎版本；不要采集凭证或完整私人素材。
- 手机验收：真机 Safari/Chrome 上传、锁屏/关页后后台继续、Range 播放、过期链接刷新、下载和保存操作。浏览器端大模型或重渲染不放进第一期。

## 暂不作为第一期依赖

生成式补帧、超分、人声分离、复杂姿态识别、人物分割、数字人、音乐生成、大型 NLE 编辑器都需具体问题驱动。它们不能补救错误的动作判断和时间线，且会增加资源、模型与许可证成本。

先测 CPU 的真实样片用时、内存峰值和画质。只有确认瓶颈后再评估 GPU；硬件编码、模型推理、视频解码是不同环节，不能混为一个“GPU 加速”开关。阿里云函数计算 GPU 仍是待验证选项，不默认创建付费资源。
