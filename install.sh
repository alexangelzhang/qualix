#!/usr/bin/env bash
set -euo pipefail

P="$0"
while [ -L "$P" ]; do
  D="$(cd "$(dirname "$P")" && pwd -P)"
  P="$(readlink "$P")"
  [[ "$P" != /* ]] && P="$D/$P"
done

exec python3 - "$P" "$@" <<'PYCODE'
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


REQUIRED_RESOURCES = ["skills", "references", "profiles", "regression"]
REQUIRED_META = ["VERSION", "pyproject.toml"]


class InstallError(RuntimeError):
    pass


class RaiseArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InstallError(message)


def expand(raw: str) -> Path:
    return Path(os.path.expanduser(raw)).resolve()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = RaiseArgumentParser(
        prog="install.sh",
        description="把 DQG 资源和 Python 包安装到 ~/.dqg + site-packages",
    )
    parser.add_argument("--output-root", default="~/.dqg")
    parser.add_argument("--source-root", default=None)
    parser.add_argument("--dev", action="store_true", help="维护者模式：symlink + pip install -e")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-pip", action="store_true")
    return parser.parse_args(argv)


def ensure_source(source: Path) -> None:
    missing = [
        str(source / name)
        for name in REQUIRED_RESOURCES + REQUIRED_META
        if not (source / name).exists()
    ]
    if missing:
        raise InstallError("缺少必要目录/文件:\n- " + "\n- ".join(missing))


def read_version(source: Path) -> str:
    return (source / "VERSION").read_text().strip()


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.exists():
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()


def copy_resource(src: Path, dest_parent: Path) -> Path:
    dest_parent.mkdir(parents=True, exist_ok=True)
    dest = dest_parent / src.name
    remove_path(dest)
    if src.is_dir():
        shutil.copytree(src, dest, symlinks=True)
    else:
        shutil.copy2(src, dest)
    return dest


def symlink_resource(src: Path, dest_parent: Path) -> Path:
    dest_parent.mkdir(parents=True, exist_ok=True)
    dest = dest_parent / src.name
    if dest.is_symlink() and Path(os.readlink(dest)) == src.resolve():
        return dest
    if dest.exists() and not dest.is_symlink():
        raise InstallError(
            f"{dest} 已是真实目录（可能之前跑过非 --dev）\n"
            f"请先手动删除再重试: rm -rf {dest}"
        )
    if dest.is_symlink():
        dest.unlink()
    os.symlink(src.resolve(), dest)
    return dest


def run_pip(source: Path, editable: bool) -> None:
    cmd = [sys.executable, "-m", "pip", "install", "--user"]
    if editable:
        cmd.append("-e")
    cmd.append(str(source))
    print(f"\n执行: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise InstallError(f"pip install 失败，退出码 {result.returncode}")


def main() -> int:
    script_path = expand(sys.argv[1])
    args = parse_args(sys.argv[2:])

    source = expand(args.source_root) if args.source_root else script_path.parent
    ensure_source(source)
    version = read_version(source)

    output_root = expand(args.output_root)
    mode = "dev-symlink" if args.dev else "production"

    print("安装计划：")
    print(f"- 模式: {mode}")
    print(f"- 源目录: {source}")
    print(f"- DQG version: {version}")
    print(f"- 目标根: {output_root}")
    print(f"- 资源条目: {', '.join(REQUIRED_RESOURCES)}")
    print(f"- pip 安装: {'跳过' if args.skip_pip else ('editable' if args.dev else 'normal')}")

    if args.dry_run:
        print("dry-run: 不实际执行")
        return 0

    placer = symlink_resource if args.dev else copy_resource
    for name in REQUIRED_RESOURCES:
        placer(source / name, output_root)

    if args.dev:
        symlink_resource(source / "VERSION", output_root)
    else:
        output_root.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / "VERSION", output_root / "VERSION")

    if not args.skip_pip:
        run_pip(source, editable=args.dev)

    print("\n✓ 安装完成")

    # 检测飞书认证状态（用于 bitable 上报）
    import configparser as _cp
    vaf_config = Path.home() / ".vaf" / "config"
    larkkit_ok = False
    if vaf_config.exists():
        cfg = _cp.ConfigParser()
        cfg.read(vaf_config)
        larkkit_ok = bool(cfg.get("feishu", "user_token", fallback=""))

    if larkkit_ok:
        print("✓ 飞书认证已就绪，团队数据上报已启用")
    else:
        print("\n⚠️  飞书认证未初始化，团队执行数据将无法上报到共享看板")
        print("   请运行以下命令登录（一次性）：")
        print("   uvx larkkit auth login")

    print("\n下一步：")
    print("  cd 你的项目目录")
    print("  qualix-run init")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InstallError as exc:
        print(f"install.sh: {exc}", file=sys.stderr)
        raise SystemExit(1)
PYCODE
