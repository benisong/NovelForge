"""启动入口"""

import os

import uvicorn


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    reload = _env_bool("DEV_RELOAD", False)
    uvicorn.run("app:app", host=host, port=port, reload=reload)
