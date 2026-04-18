"""全局配置常量 + per-workspace 路径函数。

历史背景：本模块原来导出几个模块级 Path 常量（DATA_DIR / STYLES_FILE / ...）。
多工作空间改造后，所有 per-workspace 路径都改为函数 `xxx_file(workspace)`，
统一在 app/workspace.py 的 DATA_ROOT/w/<slug>/ 下。
"""

from pathlib import Path

from .workspace import DATA_ROOT, workspace_dir

API_TIMEOUT = 180.0  # 3 分钟超时

# 数据根目录（来自 NOVEL_DATA_DIR 环境变量；ws/<slug>/ 都在它下面）
DATA_DIR = DATA_ROOT

# preset 文风列表是只读的内置资源，与工作空间无关
PRESET_STYLES_FILE = Path(__file__).parent.parent / "preset_styles.json"


# ---------- per-workspace 路径 ----------

def styles_file(workspace: str) -> Path:
    return workspace_dir(workspace) / "writing_styles.json"


def config_file(workspace: str) -> Path:
    return workspace_dir(workspace) / "_bot_configs.json"


def bot3_prompts_file(workspace: str) -> Path:
    return workspace_dir(workspace) / "bot3_prompts.json"


def workspace_data_dir(workspace: str) -> Path:
    """工作空间内的 data 根（项目 json、chapters、backups 都在这）。"""
    d = workspace_dir(workspace)
    d.mkdir(parents=True, exist_ok=True)
    return d
