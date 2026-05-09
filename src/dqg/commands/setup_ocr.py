"""一键安装 OCR 依赖（tesseract + 中文语言包）。"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_BREW_TESSERACT_CMD = ["brew", "install", "tesseract", "tesseract-lang"]
_APT_TESSERACT_CMD = ["sudo", "apt-get", "install", "-y", "tesseract-ocr", "tesseract-ocr-chi-sim"]


def cmd_setup_ocr(args, output_dir: Path) -> int:
    """一键安装 OCR 依赖（tesseract + 中文语言包）。"""
    from dqg.commands.cli_json import cli_envelope, cli_json_mode, print_cli_json

    if cli_json_mode(args):
        print_cli_json(
            cli_envelope(
                command="setup-ocr",
                project_id=args.project_id,
                success=False,
                exit_code=2,
                extra={
                    "error": "interactive_only",
                    "message": "setup-ocr runs brew/apt and is interactive; omit --json for installation",
                },
            )
        )
        return 2

    import platform
    import shutil

    print()
    print("=" * 50)
    print("  DQG Setup OCR — 图片解析依赖安装")
    print("=" * 50)

    system = platform.system()

    # 1. Tesseract
    tesseract_path = shutil.which("tesseract")
    if tesseract_path:
        print(f"  ✓ tesseract 已安装: {tesseract_path}")
        result = subprocess.run([tesseract_path, "--list-langs"], capture_output=True, text=True, timeout=5)
        if "chi_sim" in result.stdout:
            print("  ✓ 中文语言包 chi_sim 已安装")
        else:
            print("  ⚠ 缺少中文语言包，正在安装...")
            if system == "Darwin":
                _run_install(["brew", "install", "tesseract-lang"])
            elif system == "Linux":
                _run_install(["sudo", "apt-get", "install", "-y", "tesseract-ocr-chi-sim"])
            else:
                print(f"  ✗ 不支持自动安装中文语言包 ({system})，请手动安装")
    else:
        print("  正在安装 tesseract...")
        if system == "Darwin":
            if shutil.which("brew"):
                _run_install(_BREW_TESSERACT_CMD)
            else:
                print("  ✗ 需要 Homebrew。请先安装: https://brew.sh")
                return 1
        elif system == "Linux":
            _run_install(_APT_TESSERACT_CMD)
        else:
            print(f"  ✗ 不支持自动安装 ({system})")
            print("    Windows: https://github.com/UB-Mannheim/tesseract/wiki")
            return 1

    # 验证安装
    tesseract_path = shutil.which("tesseract")
    if tesseract_path:
        result = subprocess.run([tesseract_path, "--list-langs"], capture_output=True, text=True, timeout=5)
        has_chi = "chi_sim" in result.stdout
        print()
        print("  安装结果:")
        print(f"    tesseract: ✓ ({tesseract_path})")
        print(f"    chi_sim:   {'✓' if has_chi else '✗'}")
    else:
        print()
        print("  ✗ tesseract 安装失败，请检查输出日志")
        return 1

    # 2. surya-ocr（提示，不自动安装）
    surya_path = shutil.which("surya_ocr")
    print()
    if surya_path:
        print(f"  ✓ surya_ocr 已安装: {surya_path}")
    else:
        print("  - surya_ocr 未安装（可选，高精度 OCR 兜底）")
        print("    安装: pip install surya-ocr (~500MB)")

    print()
    return 0


def _run_install(cmd: list[str]) -> None:
    """执行安装命令并打印输出。"""
    print(f"    $ {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, timeout=300)
        if result.returncode == 0:
            print("    ✓ 安装成功")
        else:
            print(f"    ✗ 安装失败 (exit code: {result.returncode})")
    except subprocess.TimeoutExpired:
        print("    ✗ 安装超时")
    except FileNotFoundError:
        print(f"    ✗ 命令不存在: {cmd[0]}")
