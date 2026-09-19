"""校验覆盖、证据、时长和真实媒体范围，拒绝静默删动作或替换参考片。"""

from pathlib import Path

from .contracts import Plan
from .media import local_asset, probe


def validate_plan(plan: Plan, asset_root: Path) -> dict:
    assets = {x.id: x for x in plan.assets}
    contents = {x.id: x for x in plan.contents}
    paths = {x.id: local_asset(asset_root, x.path) for x in plan.assets}
    metadata = {key: probe(path) for key, path in paths.items()}
    errors = []
    coverage = []
    covered = set()
    position = 0.0
    previous_overlap = 0.0
    for item in plan.contents:
        for evidence in item.evidence:
            if evidence.asset_id not in assets:
                errors.append(f"{item.id} 的证据引用了未知素材")
            elif evidence.end > metadata[evidence.asset_id]["duration"] + 0.02:
                errors.append(f"{item.id} 的证据超出素材时长")
    for index, clip in enumerate(plan.clips):
        if clip.asset_id not in assets or clip.content_id not in contents:
            errors.append(f"{clip.id} 引用了未知素材或内容")
            continue
        asset, content = assets[clip.asset_id], contents[clip.content_id]
        duration = clip.source_out - clip.source_in
        if asset.role == "reference" and not plan.allow_reference_footage:
            errors.append(f"{clip.id} 使用了只供参考的样片")
        if asset.role not in ("source", "reference") or not metadata[asset.id]["video_codec"]:
            errors.append(f"{clip.id} 不是视频素材")
        if clip.source_out > metadata[asset.id]["duration"] + 0.02:
            errors.append(f"{clip.id} 裁切超出原片")
        if metadata[asset.id]["color_transfer"] in ("smpte2084", "arib-std-b67"):
            errors.append(f"{clip.id} 是 HDR；当前适配器尚未实现色调映射，不能直接输出 SDR")
        if previous_overlap + clip.transition_out >= duration:
            errors.append(f"{clip.id} 转场占满动作，或产生三段重叠")
        if (index + 1 < len(plan.clips) and plan.output.next_label_seconds
                >= duration - previous_overlap - clip.transition_out):
            errors.append(f"{clip.id} 预告字幕占满当前动作标签时间")
        if index == len(plan.clips) - 1 and clip.transition_out:
            errors.append("最后一段不能带向下一段的转场")
        if content.status != "confirmed":
            errors.append(f"{content.id} 动作名称尚未确认")
        # Evidence describes a complete action interval. It must remain outside both dissolves.
        visual = [e for e in content.evidence if e.modality == "continuous_visual"
                  and e.asset_id == clip.asset_id
                  and e.start >= clip.source_in + previous_overlap - 1e-6
                  and e.end <= clip.source_out - clip.transition_out + 1e-6]
        if not visual:
            errors.append(f"{clip.id} 没有被完整保留且避开转场的连续画面证据")
        covered.add(content.id)
        coverage.append({
            "content_id": content.id, "label": content.label, "category": content.category,
            "clip_id": clip.id, "asset_id": clip.asset_id,
            "source_range": [clip.source_in, clip.source_out],
            "output_range": [round(position, 6), round(position + duration, 6)],
            "clear_output_range": [round(position + previous_overlap, 6),
                                   round(position + duration - clip.transition_out, 6)],
        })
        position += duration - clip.transition_out
        previous_overlap = clip.transition_out
    missing = sorted(c.id for c in plan.contents if c.required and c.id not in covered)
    if missing:
        errors.append(f"遗漏必需内容：{', '.join(missing)}")
    target = plan.output.target_seconds
    if target is not None and abs(position - target) > plan.output.tolerance_seconds + 1e-6:
        errors.append(f"计划 {position:.3f} 秒，与目标 {target} 秒冲突；不能自动删内容或加速")
    if plan.audio.mode in ("music", "voiceover", "mixed"):
        key = plan.audio.asset_id
        role = "music" if plan.audio.mode == "mixed" else plan.audio.mode
        if key not in assets or assets[key].role != role:
            errors.append("音轨素材不存在或角色不符")
        elif not metadata[key]["has_audio"] or metadata[key]["duration"] < position - 0.02:
            errors.append("音轨缺失或比成片短；不能默默循环、拉伸旁白或留下静音尾部")
    if plan.audio.mode in ("source", "mixed") and any(
        not metadata[c.asset_id]["has_audio"] for c in plan.clips if c.asset_id in metadata
    ):
        errors.append("要求保留原声，但部分片段没有音轨")
    if errors:
        raise ValueError("；".join(errors))
    return {"duration_seconds": round(position, 6), "coverage": coverage,
            "assets": metadata, "covered_contents": len(covered),
            "semantic_boundary": "验证已声明清单及证据的一致性；不自动证明清单没有漏识别动作"}
