"""Bot 配置档案 CRUD"""

import json
from fastapi import APIRouter

from ..models import SaveConfigRequest
from ..config import CONFIG_FILE

router = APIRouter()


def _read_configs() -> list[dict]:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _write_configs(configs: list[dict]):
    CONFIG_FILE.write_text(json.dumps(configs, ensure_ascii=False, indent=2), encoding="utf-8")


@router.get("/api/configs")
async def get_configs():
    """获取所有已保存的Bot配置"""
    return {"configs": _read_configs()}


@router.post("/api/configs")
async def save_configs(req: SaveConfigRequest):
    """保存全部Bot配置列表"""
    _write_configs(req.configs)
    return {"ok": True}


@router.delete("/api/configs/{config_id}")
async def delete_config(config_id: str):
    """删除某个配置"""
    configs = _read_configs()
    configs = [c for c in configs if c.get("id") != config_id]
    _write_configs(configs)
    return {"ok": True}
