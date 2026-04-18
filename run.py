"""启动入口"""

import os

import uvicorn


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


if __name__ == "__main__":
    # 默认对外开放（0.0.0.0）+ 17000 端口；HOST / PORT 可被 env 覆盖
    host = os.environ.get("HOST", os.environ.get("BIND_ADDR", "0.0.0.0"))
    port = int(os.environ.get("PORT", "17000"))
    reload = _env_bool("DEV_RELOAD", False)
    uvicorn.run("app:app", host=host, port=port, reload=reload)
