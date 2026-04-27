"""一次性数据迁移。

启动时调用 `run_pending_migrations()`，每个迁移自身做幂等检查，
重复跑也安全。新增迁移：在文件末尾加一个函数，再在
`run_pending_migrations` 里追加一次调用即可。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .llm import MAX_OUTPUT_TOKENS
from .workspace import WORKSPACES_DIR

logger = logging.getLogger(__name__)

_BOT_KEYS = ("bot1", "bot2", "bot3", "bot4")


def _bump_one_config_dict(config: dict) -> int:
    """把单个 config（含 bot1-4 子配置）里 max_tokens 拉到 MAX_OUTPUT_TOKENS。

    返回实际改动的 bot 数量。
    """
    changed = 0
    for bot_key in _BOT_KEYS:
        bot = config.get(bot_key)
        if not isinstance(bot, dict):
            continue
        existing = bot.get("max_tokens")
        if not isinstance(existing, (int, float)) or existing < MAX_OUTPUT_TOKENS:
            bot["max_tokens"] = MAX_OUTPUT_TOKENS
            changed += 1
    return changed


def _migrate_one_workspace(configs_file: Path) -> tuple[int, int]:
    """处理单个工作空间的 _bot_configs.json。

    返回 (改动的 config 条数, 改动的 bot 字段数)。
    """
    try:
        raw = configs_file.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("跳过损坏的 %s: %s", configs_file, e)
        return 0, 0

    if not isinstance(data, list):
        return 0, 0

    total_bot_changes = 0
    affected_configs = 0
    for config in data:
        if not isinstance(config, dict):
            continue
        bot_changes = _bump_one_config_dict(config)
        if bot_changes > 0:
            total_bot_changes += bot_changes
            affected_configs += 1

    if total_bot_changes == 0:
        return 0, 0

    try:
        configs_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        logger.warning("写回 %s 失败: %s", configs_file, e)
        return 0, 0

    return affected_configs, total_bot_changes


def bump_max_tokens_in_saved_configs() -> None:
    """把所有工作空间已保存的 max_tokens 拉到当前 MAX_OUTPUT_TOKENS。

    旧版本默认是 2048/4096/8192，会在 Bot3/Bot4 这种结构化输出场景里被
    模型截断；后端虽然在 _build_payload 里硬编码覆盖了，但 UI 里读到的
    历史值仍是旧值，会让用户困惑。这次一次性把存盘的也拉齐。
    """
    if not WORKSPACES_DIR.exists():
        return

    workspace_count = 0
    config_changes = 0
    bot_changes = 0
    for ws_dir in WORKSPACES_DIR.iterdir():
        if not ws_dir.is_dir():
            continue
        configs_file = ws_dir / "_bot_configs.json"
        if not configs_file.exists():
            continue
        cc, bc = _migrate_one_workspace(configs_file)
        if bc > 0:
            workspace_count += 1
            config_changes += cc
            bot_changes += bc

    if bot_changes > 0:
        logger.info(
            "max_tokens 迁移完成：%d 个工作空间 / %d 个 config / %d 个 bot 字段被拉到 %d",
            workspace_count,
            config_changes,
            bot_changes,
            MAX_OUTPUT_TOKENS,
        )


def run_pending_migrations() -> None:
    """启动时统一入口。每个迁移内部已幂等，反复跑安全。"""
    try:
        bump_max_tokens_in_saved_configs()
    except Exception as e:  # noqa: BLE001 — 迁移失败不能阻止应用启动
        logger.exception("max_tokens 迁移异常（继续启动）: %s", e)
