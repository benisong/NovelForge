"""全局配置常量"""

import os
from pathlib import Path

API_TIMEOUT = 180.0  # 3分钟超时

# 持久化目录
DATA_DIR = Path(os.environ.get("NOVEL_DATA_DIR", Path(__file__).parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

STYLES_FILE = DATA_DIR / "writing_styles.json"
PRESET_STYLES_FILE = Path(__file__).parent.parent / "preset_styles.json"
CONFIG_FILE = DATA_DIR / "_bot_configs.json"
BOT3_PROMPTS_FILE = DATA_DIR / "bot3_prompts.json"
