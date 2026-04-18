"""一次性迁移脚本：把旧版（单工作空间）数据迁移到多工作空间结构。

用法：
    python migrate_to_workspaces.py [--data-dir DATA_DIR] [--slug default] [--password PASSWORD]

行为：
    - 读取 DATA_DIR 下的所有 *.json（项目）+ chapters/ + backups/ + writing_styles.json + _bot_configs.json + bot3_prompts.json
    - 全部移动到 DATA_DIR/w/<slug>/ 目录下
    - 在 DATA_DIR/workspaces.json 注册一条 <slug> 记录（带密码）
    - 已经迁移过（DATA_DIR/w/<slug>/ 已存在）则只补登记，不重复搬动

注意：迁移前请先备份 DATA_DIR。
"""

import argparse
import json
import os
import shutil
import sys
import time
from getpass import getpass
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=os.environ.get("NOVEL_DATA_DIR", "data"))
    ap.add_argument("--slug", default="default", help="目标工作空间 slug（默认 default）")
    ap.add_argument("--name", default="默认空间")
    ap.add_argument("--password", default=None, help="设置初始密码（不传则交互式输入）")
    args = ap.parse_args()

    data_dir = Path(args.data_dir).resolve()
    if not data_dir.exists():
        print(f"数据目录不存在: {data_dir}")
        return 1

    target_dir = data_dir / "w" / args.slug
    target_dir.mkdir(parents=True, exist_ok=True)

    # 待迁移的顶层文件 / 目录
    legacy_items = [
        "writing_styles.json",
        "_bot_configs.json",
        "bot3_prompts.json",
        "chapters",
        "backups",
    ]
    # 项目 JSON：data_dir 下所有不以 _ 开头的 *.json，且不是 workspaces.json
    project_files = [
        f for f in data_dir.glob("*.json")
        if not f.name.startswith("_") and f.name != "workspaces.json"
    ]

    moved = 0
    for name in legacy_items:
        src = data_dir / name
        if not src.exists():
            continue
        dst = target_dir / name
        if dst.exists():
            print(f"跳过（目标已存在）：{name}")
            continue
        shutil.move(str(src), str(dst))
        print(f"已迁移：{name}")
        moved += 1

    for f in project_files:
        dst = target_dir / f.name
        if dst.exists():
            print(f"跳过（目标已存在）：{f.name}")
            continue
        shutil.move(str(f), str(dst))
        print(f"已迁移项目：{f.name}")
        moved += 1

    # 登记到 workspaces.json
    password = args.password
    if password is None:
        password = getpass(f"请为工作空间 '{args.slug}' 设置访问密码（≥4 字符）：").strip()
    if len(password) < 4:
        print("密码至少 4 个字符")
        return 1

    # 用 app/workspace.py 的逻辑生成密码哈希，避免重复
    sys.path.insert(0, str(Path(__file__).parent))
    os.environ["NOVEL_DATA_DIR"] = str(data_dir)
    from app.workspace import _hash_password, _load_registry, _save_registry, is_valid_slug

    if not is_valid_slug(args.slug):
        print(f"slug '{args.slug}' 不合法（只允许小写字母/数字/横线，3-32 字符）")
        return 1

    items = _load_registry()
    if any(it.get("slug") == args.slug for it in items):
        print(f"工作空间 '{args.slug}' 已在注册表中，仅补充密码")
        for it in items:
            if it.get("slug") == args.slug:
                it["password_hash"] = _hash_password(password)
                break
    else:
        items.append({
            "slug": args.slug,
            "name": args.name,
            "password_hash": _hash_password(password),
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "last_active": "",
        })
    _save_registry(items)

    print(f"\n完成。共迁移 {moved} 项。")
    print(f"工作空间已就绪：访问 http://<host>/w/{args.slug}/ 用刚才的密码登录。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
