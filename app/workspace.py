"""工作空间：注册表、密码、cookie 会话、登录限速。

数据落在 NOVEL_DATA_DIR 下：
  workspaces.json     —— 全局注册表 [{slug,name,password_hash,created,last_active}, ...]
  w/<slug>/...        —— 每个工作空间一份独立目录
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Optional

import bcrypt
from fastapi import HTTPException, Path as FPath, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger(__name__)


# bcrypt 限制密码 ≤72 字节；超过的部分会被忽略，必须显式截断防止行为不一致
def _hash_password(password: str) -> str:
    raw = (password or "").encode("utf-8")[:72]
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("ascii")


def _check_password(password: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        raw = (password or "").encode("utf-8")[:72]
        return bcrypt.checkpw(raw, hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


# ---------- 常量 / 配置 ----------

DATA_ROOT = Path(
    os.environ.get("NOVEL_DATA_DIR", Path(__file__).parent.parent / "data")
).resolve()
WORKSPACES_DIR = (DATA_ROOT / "w").resolve()
WORKSPACES_FILE = DATA_ROOT / "workspaces.json"

DATA_ROOT.mkdir(parents=True, exist_ok=True)
WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)

COOKIE_PREFIX = "ws_"
COOKIE_MAX_AGE = 30 * 24 * 3600  # 30 天
COOKIE_SAMESITE = "lax"

# 管理员账户存在 DATA_ROOT/_admin.json，首次启动自动用 admin/admin 初始化。
ADMIN_FILE = DATA_ROOT / "_admin.json"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin"
_COOKIE_SECRET = os.environ.get("WORKSPACE_COOKIE_SECRET", "").strip()
if not _COOKIE_SECRET:
    # 没配置时落到一个本地文件持久化，重启不会失效（但部署时强烈建议显式配 env）
    secret_file = DATA_ROOT / ".cookie_secret"
    if secret_file.exists():
        _COOKIE_SECRET = secret_file.read_text(encoding="utf-8").strip()
    else:
        import secrets as _secrets
        _COOKIE_SECRET = _secrets.token_urlsafe(48)
        secret_file.write_text(_COOKIE_SECRET, encoding="utf-8")
        try:
            os.chmod(secret_file, 0o600)
        except OSError:
            pass

_serializer = URLSafeTimedSerializer(_COOKIE_SECRET, salt="novelforge-ws")


# ---------- slug 校验 ----------

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,30}[a-z0-9]$")


def is_valid_slug(slug: str) -> bool:
    return bool(_SLUG_RE.match(slug or ""))


# ---------- 注册表读写（线程锁保护）----------

_registry_lock = threading.Lock()


def _load_registry() -> list[dict]:
    if not WORKSPACES_FILE.exists():
        return []
    try:
        data = json.loads(WORKSPACES_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError) as e:
        logger.error("workspaces.json 解析失败: %s", e)
        return []


def _save_registry(items: list[dict]) -> None:
    tmp = WORKSPACES_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(WORKSPACES_FILE)


def list_workspaces_public() -> list[dict]:
    """对公开页（首页）返回的字段，绝不含密码哈希。"""
    items = _load_registry()
    return [
        {
            "slug": it.get("slug"),
            "name": it.get("name", it.get("slug")),
            "last_active": it.get("last_active", ""),
        }
        for it in items
        if it.get("slug")
    ]


def list_workspaces_admin() -> list[dict]:
    """admin 页用，比 public 多一个 created 字段，仍不返回 hash。"""
    items = _load_registry()
    return [
        {
            "slug": it.get("slug"),
            "name": it.get("name", it.get("slug")),
            "created": it.get("created", ""),
            "last_active": it.get("last_active", ""),
            "has_password": bool(it.get("password_hash")),
        }
        for it in items
        if it.get("slug")
    ]


def get_workspace(slug: str) -> Optional[dict]:
    for it in _load_registry():
        if it.get("slug") == slug:
            return it
    return None


def workspace_dir(slug: str) -> Path:
    """计算并校验工作空间目录在 WORKSPACES_DIR 内。"""
    if not is_valid_slug(slug):
        raise ValueError("invalid slug")
    p = (WORKSPACES_DIR / slug).resolve()
    p.relative_to(WORKSPACES_DIR)  # 越界则抛 ValueError
    return p


# ---------- 工作空间 CRUD ----------

def create_workspace(slug: str, name: str, password: str) -> dict:
    if not is_valid_slug(slug):
        raise ValueError("slug 只允许小写字母/数字/横线，3-32 字符，首尾必须是字母数字")
    if not password or len(password) < 4:
        raise ValueError("密码至少 4 个字符")
    name = (name or slug).strip()
    with _registry_lock:
        items = _load_registry()
        if any(it.get("slug") == slug for it in items):
            raise ValueError("slug 已存在")
        ws_dir = workspace_dir(slug)
        ws_dir.mkdir(parents=True, exist_ok=True)
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = {
            "slug": slug,
            "name": name,
            "password_hash": _hash_password(password),
            "created": now,
            "last_active": "",
        }
        items.append(entry)
        _save_registry(items)
    logger.info("workspace created: %s", slug)
    return {"slug": slug, "name": name, "created": entry["created"]}


def update_password(slug: str, new_password: str) -> None:
    if not new_password or len(new_password) < 4:
        raise ValueError("密码至少 4 个字符")
    with _registry_lock:
        items = _load_registry()
        found = False
        for it in items:
            if it.get("slug") == slug:
                it["password_hash"] = _hash_password(new_password)
                found = True
                break
        if not found:
            raise ValueError("工作空间不存在")
        _save_registry(items)
    logger.info("workspace password updated: %s", slug)


def rename_workspace(slug: str, new_name: str) -> None:
    new_name = (new_name or "").strip()
    if not new_name:
        raise ValueError("名称不能为空")
    with _registry_lock:
        items = _load_registry()
        found = False
        for it in items:
            if it.get("slug") == slug:
                it["name"] = new_name
                found = True
                break
        if not found:
            raise ValueError("工作空间不存在")
        _save_registry(items)


def delete_workspace(slug: str) -> None:
    with _registry_lock:
        items = _load_registry()
        new_items = [it for it in items if it.get("slug") != slug]
        if len(new_items) == len(items):
            raise ValueError("工作空间不存在")
        _save_registry(new_items)
    try:
        ws_dir = workspace_dir(slug)
        if ws_dir.exists():
            shutil.rmtree(ws_dir)
    except (ValueError, OSError) as e:
        logger.error("删除工作空间目录失败 %s: %s", slug, e)
    logger.info("workspace deleted: %s", slug)


def touch_last_active(slug: str) -> None:
    """更新 last_active，失败不影响主流程。"""
    try:
        with _registry_lock:
            items = _load_registry()
            for it in items:
                if it.get("slug") == slug:
                    it["last_active"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    _save_registry(items)
                    return
    except Exception as e:
        logger.warning("touch_last_active 失败 %s: %s", slug, e)


# ---------- 密码校验 + 限速 ----------

_RATE_LIMIT_WINDOW = 60.0       # 1 分钟窗口
_RATE_LIMIT_MAX_FAILS = 5       # 5 次失败
_RATE_LIMIT_LOCK_SECONDS = 900  # 锁 15 分钟

_fail_lock = threading.Lock()
# slug -> {"fails": [t1, t2, ...], "locked_until": ts}
_fails: dict[str, dict] = {}


def _gc_fails(slug: str, now: float) -> dict:
    info = _fails.setdefault(slug, {"fails": [], "locked_until": 0.0})
    info["fails"] = [t for t in info["fails"] if now - t < _RATE_LIMIT_WINDOW]
    return info


def is_locked(slug: str) -> tuple[bool, int]:
    """返回 (是否被锁, 剩余秒数)。"""
    now = time.time()
    with _fail_lock:
        info = _gc_fails(slug, now)
        if info["locked_until"] > now:
            return True, int(info["locked_until"] - now)
    return False, 0


def verify_password(slug: str, password: str) -> bool:
    """校验密码。失败累计 + 锁定。成功重置计数。"""
    locked, _ = is_locked(slug)
    if locked:
        return False
    ws = get_workspace(slug)
    if not ws:
        # 防探测，统一返回 False，但仍然计入失败
        _record_fail(slug)
        return False
    ok = _check_password(password or "", ws.get("password_hash", ""))
    if ok:
        with _fail_lock:
            _fails.pop(slug, None)
        return True
    _record_fail(slug)
    return False


def _record_fail(slug: str) -> None:
    now = time.time()
    with _fail_lock:
        info = _gc_fails(slug, now)
        info["fails"].append(now)
        if len(info["fails"]) >= _RATE_LIMIT_MAX_FAILS:
            info["locked_until"] = now + _RATE_LIMIT_LOCK_SECONDS
            info["fails"] = []
            logger.warning("workspace 登录被锁: %s", slug)


# ---------- Cookie 签发 / 校验 ----------

def cookie_name(slug: str) -> str:
    return f"{COOKIE_PREFIX}{slug}"


def issue_cookie(slug: str) -> str:
    """生成 cookie 值；包含 slug，过期由 itsdangerous 验签时检查。"""
    return _serializer.dumps({"slug": slug})


def verify_cookie(slug: str, raw: str) -> bool:
    if not raw:
        return False
    try:
        data = _serializer.loads(raw, max_age=COOKIE_MAX_AGE)
    except SignatureExpired:
        return False
    except BadSignature:
        return False
    return isinstance(data, dict) and data.get("slug") == slug


# ---------- FastAPI 依赖：所有受保护路由都用它 ----------

# 路径里 workspace slug 的合法字符（与 _SLUG_RE 同步，但 FastAPI 路径正则不支持 ^$ 锚）
_PATH_SLUG_PATTERN = r"[a-z0-9][a-z0-9\-]{1,30}[a-z0-9]"


def require_workspace(
    request: Request,
    workspace: str = FPath(..., pattern=f"^{_PATH_SLUG_PATTERN}$"),
) -> str:
    """校验：slug 合法 + 已登录（cookie 验签通过）。返回 slug 字符串。"""
    if not get_workspace(workspace):
        raise HTTPException(status_code=404, detail="工作空间不存在")
    raw = request.cookies.get(cookie_name(workspace), "")
    if not verify_cookie(workspace, raw):
        raise HTTPException(status_code=401, detail="未登录或会话已失效")
    touch_last_active(workspace)
    return workspace


# ---- 管理员账户（_admin.json）+ cookie 会话 ----

ADMIN_COOKIE_NAME = "novelforge_admin"
ADMIN_COOKIE_MAX_AGE = 30 * 24 * 3600  # 30 天


def _load_admin() -> dict:
    if ADMIN_FILE.exists():
        try:
            return json.loads(ADMIN_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.error("_admin.json 解析失败: %s", e)
    return {}


def _save_admin(data: dict) -> None:
    tmp = ADMIN_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ADMIN_FILE)
    try:
        os.chmod(ADMIN_FILE, 0o600)
    except OSError:
        pass


def ensure_admin_initialized() -> None:
    """首次启动若 _admin.json 不存在，用默认 admin/admin 创建。"""
    if not ADMIN_FILE.exists():
        _save_admin({
            "username": DEFAULT_ADMIN_USERNAME,
            "password_hash": _hash_password(DEFAULT_ADMIN_PASSWORD),
        })
        logger.warning(
            "首次启动：管理员账户已初始化为 %s/%s，请登录后立即在管理页修改密码",
            DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD,
        )


def get_admin_username() -> str:
    return _load_admin().get("username", DEFAULT_ADMIN_USERNAME)


def verify_admin_login(username: str, password: str) -> bool:
    """账户名 + 密码校验。"""
    data = _load_admin()
    if not data:
        return False
    if (username or "").strip() != data.get("username", ""):
        return False
    return _check_password(password or "", data.get("password_hash", ""))


def update_admin_password(current: str, new: str) -> None:
    """自助改密码：校验当前密码 → 写入新哈希。"""
    if len(new or "") < 4:
        raise ValueError("新密码至少 4 个字符")
    data = _load_admin()
    if not data:
        raise ValueError("管理员账户未初始化")
    if not _check_password(current or "", data.get("password_hash", "")):
        raise ValueError("当前密码错误")
    data["password_hash"] = _hash_password(new)
    _save_admin(data)
    logger.info("管理员密码已更新")


def issue_admin_cookie() -> str:
    return _serializer.dumps({"role": "admin"})


def verify_admin_cookie(raw: str) -> bool:
    if not raw:
        return False
    try:
        data = _serializer.loads(raw, max_age=ADMIN_COOKIE_MAX_AGE)
    except (SignatureExpired, BadSignature):
        return False
    return isinstance(data, dict) and data.get("role") == "admin"
