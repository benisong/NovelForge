"""Bot 配置档案 CRUD（per-workspace）"""

import json

from fastapi import APIRouter, Depends

from ..config import config_file
from ..models import SaveConfigRequest
from ..workspace import require_workspace

router = APIRouter(
    prefix="/api/w/{workspace}",
    dependencies=[Depends(require_workspace)],
)


def _read_configs(workspace: str) -> list[dict]:
    cf = config_file(workspace)
    if cf.exists():
        try:
            return json.loads(cf.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return []


def _write_configs(workspace: str, configs: list[dict]) -> None:
    cf = config_file(workspace)
    cf.parent.mkdir(parents=True, exist_ok=True)
    cf.write_text(json.dumps(configs, ensure_ascii=False, indent=2), encoding="utf-8")


@router.get("/configs")
async def get_configs(workspace: str):
    return {"configs": _read_configs(workspace)}


@router.post("/configs")
async def save_configs(workspace: str, req: SaveConfigRequest):
    _write_configs(workspace, req.configs)
    return {"ok": True}


@router.delete("/configs/{config_id}")
async def delete_config(workspace: str, config_id: str):
    configs = _read_configs(workspace)
    configs = [c for c in configs if c.get("id") != config_id]
    _write_configs(workspace, configs)
    return {"ok": True}
