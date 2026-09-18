# 剪辑素材批次与版本归档

更新：2026-09-18。用户明确要求以后每批素材分开建目录、目录名包含时分秒，每版成片都进入剪辑专用OSS；提示词调教是持续重点，不必每次重述。

## 存放在哪里

- 剪辑专用私有bucket：`video-editing-media`，阿里云北京地域。不是点播平台的存储桶。
- 本批统一目录：`oss://video-editing-media/batches/20260918-204846-swimming/`。
- 旧目录：`swimming/20260918/`，保留以兼容历史交接，不删除或覆盖。
- 时间命名：`YYYYMMDD-HHMMSS-主题`，时区`Asia/Shanghai`。日期避免跨天重名；时分秒区分同日批次。时间代表建档时间，不冒充拍摄时间。同秒冲突增加短后缀。
- 同一批素材后续调教继续用原批次ID；新增不同批素材才另建根目录。
- 私有凭据由Infisical的`tools / dev /video-editing`管理，实际账号配置以infra仓库`aliyun/video-editing-oss.json`为准。Git不存凭据、签名链接、私有回执或素材。

## 目录约定

```text
batches/20260918-204846-swimming/
  README.md                         # 批次、源素材、版本、恢复步骤
  assets/                           # 原素材，保留一次
  references/                       # 参考片，与原素材区分
  versions/
    v4/                             # 本批配乐历史版
    v5/                             # 本批教练原声版
    v6/                             # 本批动画编号版，内容纠正待执行
    legacy-20260916/                 # 早期成片，原版本编号未恢复
  iterations/20260918-204846/
    prompts/                        # 本轮提示词快照
    docs/                           # 用户反馈、经验、下一次任务
```

每个新版本保存成片、结构化方案、质量报告、版本说明；交付回执也放私有存储。方案至少含父版本和规则快照。提示词调教记录写清“用户反馈→原规则问题→提示词修改→验证结果／未验证项”。渲染之后新增的提示词注明供下次使用，不倒填成旧成片的生成依据。

更新内容写新版本／时间目录，不覆盖以前的视频、方案或提示词。批次README用于导航；需要修改已归档说明时增加新的带时间说明和索引，由接续者按时间读取，不静默覆盖。

## 每轮必做

1. 找现有批次ID，读取最新反馈、视频类型模板、风格配置和术语表；不依赖旧聊天。
2. 渲染新版本，更新方案、修改说明和提示词调教记录。
3. 上传该版本及记录到本批次目录。只生成方案而未渲染时也保存本轮反馈／提示词快照。
4. 校验：本地上传文件全量回读SHA-256；OSS内复制比较大小和CRC64。上传成功但未验证不算归档完成。
5. GitHub记录规则、位置和经验；私人批次清单与回执留在交付目录及私有OSS。
6. 点播链接与OSS归档分别报告。点播可播放不代表已归档OSS，OSS存在也不代表点播已经READY。

## 可复用归档工具

`scripts/archive_batch.py`读取私有JSON清单，支持`local_path`上传、`source_key`同bucket复制；目标路径相对于清单中的`prefix`。相同目标已存在时验证一致性，不覆盖不同内容，可按同一清单重试。

```json
{
  "prefix": "batches/YYYYMMDD-HHMMSS-topic",
  "files": [
    {"local_path": "/交付目录/新版.mp4", "target": "versions/v7/video.mp4"},
    {"source_key": "既有目录/assets/source.mp4", "target": "assets/source.mp4"}
  ]
}
```

通过Infisical向子进程注入`OSS_ACCESS_KEY_ID`、`OSS_ACCESS_KEY_SECRET`、`OSS_ENDPOINT`、`OSS_BUCKET`，不要把值打印或写入脚本。使用已有点播CLI依赖环境：

```sh
uv run --extra delivery --with /path/to/video-2022/cli python scripts/archive_batch.py /私有目录/归档清单.json --receipt /私有目录/归档回执.json
```

本批原方案的素材路径是`素材01.mp4`等；恢复时下载`assets/`并将其作为`asset-root`。参考片单独放在`references/`。

## 历史缺口

当前能定位v4、v5、v6及2026-09-16早期成片；v2、v3在本机交付目录与专用OSS未找到，待从历史工作机或点播平台恢复。早期成片没有可恢复的原方案，不能伪造版本号与完整工程。具体本轮验证结果见迭代记录。
