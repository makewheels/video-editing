"""与模型、聊天会话和渲染引擎无关的持久化输入。"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Seconds = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Asset(Contract):
    id: Identifier
    path: str = Field(min_length=1)
    role: Literal["source", "reference", "music", "voiceover"] = "source"


class Evidence(Contract):
    asset_id: Identifier
    start: Seconds
    end: Seconds
    modality: Literal["continuous_visual", "asr", "ocr"]
    note: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_range(self):
        if self.end <= self.start:
            raise ValueError("证据 end 必须大于 start")
        return self


class Content(Contract):
    id: Identifier
    label: str = Field(min_length=1, max_length=40)
    category: Literal["stroke", "start", "turn", "drill", "water_skill", "other"]
    required: bool = True
    status: Literal["confirmed", "uncertain"]
    evidence: list[Evidence] = Field(min_length=1)


class Clip(Contract):
    id: Identifier
    asset_id: Identifier
    content_id: Identifier
    source_in: Seconds
    source_out: Seconds
    transition_out: Seconds = 0
    caption_position: Literal["top", "bottom"] = "top"
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_range(self):
        if self.source_out <= self.source_in:
            raise ValueError("片段 source_out 必须大于 source_in")
        return self


class Audio(Contract):
    mode: Literal["mute", "source", "music", "voiceover"] = "mute"
    asset_id: Identifier | None = None
    rights_note: str | None = None
    gain_db: float = Field(default=-8, ge=-60, le=6)

    @model_validator(mode="after")
    def external_track(self):
        if self.mode in ("music", "voiceover"):
            if not self.asset_id or not self.rights_note or not self.rights_note.strip():
                raise ValueError("配乐或旁白必须给出 asset_id 和可用来源说明 rights_note")
        elif self.asset_id is not None:
            raise ValueError("mute/source 不接受外加音轨，避免无意混音")
        return self


class Output(Contract):
    width: int = Field(default=720, ge=64, le=3840)
    height: int = Field(default=1280, ge=64, le=3840)
    fps: int = Field(default=30, ge=1, le=60)
    target_seconds: float | None = Field(default=None, gt=0)
    tolerance_seconds: Seconds = 1
    next_label_seconds: Seconds = 0

    @model_validator(mode="after")
    def even_dimensions(self):
        if self.width % 2 or self.height % 2:
            raise ValueError("H.264 输出宽高必须为偶数")
        return self


class Plan(Contract):
    schema_version: Literal["1.0"] = "1.0"
    project_id: Identifier
    version: int = Field(default=1, ge=1)
    parent_version: int | None = Field(default=None, ge=1)
    assets: list[Asset] = Field(min_length=1)
    contents: list[Content] = Field(min_length=1)
    clips: list[Clip] = Field(min_length=1)
    audio: Audio = Field(default_factory=Audio)
    output: Output = Field(default_factory=Output)
    allow_reference_footage: bool = False
    reference_use_reason: str | None = None
    rules_snapshot: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def identities(self):
        for name in ("assets", "contents", "clips"):
            items = getattr(self, name)
            if len({x.id for x in items}) != len(items):
                raise ValueError(f"{name} 中 id 重复")
        if self.allow_reference_footage and not self.reference_use_reason:
            raise ValueError("允许参考片入成片时，必须记录本次要求的依据")
        if self.parent_version is not None and self.parent_version >= self.version:
            raise ValueError("parent_version 必须小于当前 version")
        return self
