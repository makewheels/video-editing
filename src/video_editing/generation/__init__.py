"""素材生成：调用外部模型生成剪辑用素材；当前接入 Seedance 2.5。

生成物属于合成素材：归档时标记来源与提示词版本，不混入原素材目录。
凭据只从进程环境读取，不写入仓库、方案或回执。
"""

from .seedance import (
    MODEL,
    build_payload,
    create_task,
    download,
    estimate_cost,
    generate,
    wait_task,
)

__all__ = [
    "MODEL",
    "build_payload",
    "create_task",
    "download",
    "estimate_cost",
    "generate",
    "wait_task",
]
