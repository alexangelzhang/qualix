"""OCR 引擎：通过 subprocess 调用系统 tesseract / surya CLI，零 Python 依赖。"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OcrResult:
    """OCR 提取结果。"""

    text: str = ""
    confidence: float = 0.0
    engine: str = "none"
    lines: list[str] = field(default_factory=list)


def ocr_extract(image_path: Path, langs: str = "chi_sim+eng") -> OcrResult:
    """自动选择可用引擎提取文字：tesseract 优先（快），surya 兜底（准）。

    两个都不可用时返回空结果（engine="none"）。
    """
    result = _run_tesseract(image_path, langs)
    if result is not None:
        return result

    surya_langs = _convert_langs_for_surya(langs)
    result = _run_surya(image_path, surya_langs)
    if result is not None:
        return result

    return OcrResult()


_EXTRA_BIN_PATHS = [
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/bin",
]


def _which_with_fallback(name: str) -> str | None:
    """shutil.which + 常见安装路径 fallback（应对 pyenv 环境 PATH 不完整的情况）。"""
    found = shutil.which(name)
    if found:
        return found
    # pyenv bin
    pyenv_bin = Path.home() / ".pyenv" / "versions"
    for p in sorted(pyenv_bin.glob("*/bin/" + name), reverse=True):
        if p.is_file():
            return str(p)
    for d in _EXTRA_BIN_PATHS:
        candidate = Path(d) / name
        if candidate.is_file():
            return str(candidate)
    return None


def is_ocr_available() -> bool:
    """检查是否有任何 OCR 引擎可用。"""
    return _which_with_fallback("tesseract") is not None or _which_with_fallback("surya_ocr") is not None


def _run_tesseract(image_path: Path, langs: str = "chi_sim+eng") -> OcrResult | None:
    """通过 subprocess 调用 tesseract CLI。

    返回 None 表示 tesseract 不可用（未安装或语言包缺失）。
    """
    tesseract = _which_with_fallback("tesseract")
    if tesseract is None:
        return None

    try:
        result = subprocess.run(
            [tesseract, str(image_path), "stdout", "-l", langs, "--psm", "6"],
            capture_output=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace")
        if "Failed loading language" in stderr:
            fallback = subprocess.run(
                [tesseract, str(image_path), "stdout", "-l", "eng", "--psm", "6"],
                capture_output=True,
                timeout=30,
            )
            if fallback.returncode != 0:
                return None
            result = fallback

    text = result.stdout.decode(errors="replace").strip()
    if not text:
        return OcrResult(engine="tesseract")

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    confidence = _get_tesseract_confidence(image_path, langs)

    return OcrResult(text=text, confidence=confidence, engine="tesseract", lines=lines)


def _get_tesseract_confidence(image_path: Path, langs: str = "chi_sim+eng") -> float:
    """用 tesseract TSV 输出获取平均置信度。"""
    tesseract = _which_with_fallback("tesseract")
    if tesseract is None:
        return 0.5

    try:
        result = subprocess.run(
            [tesseract, str(image_path), "stdout", "-l", langs, "--psm", "6", "tsv"],
            capture_output=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 0.5

    if result.returncode != 0:
        return 0.5

    confidences: list[float] = []
    for line in result.stdout.decode(errors="replace").splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) >= 12:
            try:
                conf = float(parts[10])
                word = parts[11].strip()
                if conf >= 0 and word:
                    confidences.append(conf / 100.0)
            except (ValueError, IndexError):
                continue

    return sum(confidences) / len(confidences) if confidences else 0.5


def _run_surya(image_path: Path, langs: str = "zh,en") -> OcrResult | None:
    """通过 subprocess 调用 surya_ocr CLI。

    返回 None 表示 surya 不可用。
    """
    surya = _which_with_fallback("surya_ocr")
    if surya is None:
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            result = subprocess.run(
                [surya, str(image_path), "--output_dir", tmpdir],
                capture_output=True,
                timeout=120,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None

        if result.returncode != 0:
            return None

        text, lines = _parse_surya_output(Path(tmpdir))

    if not text:
        return OcrResult(engine="surya")

    return OcrResult(text=text, confidence=0.85, engine="surya", lines=lines)


def _parse_surya_output(results_dir: Path) -> tuple[str, list[str]]:
    """解析 surya_ocr 的 JSON 输出。

    兼容两种格式：
    - 旧版: {"pages": [{text_lines: [...]}]} 或 [{text_lines: [...]}]
    - 新版: {"<filename>": [{text_lines: [...]}]}
    """
    json_files = list(results_dir.rglob("*.json"))
    if not json_files:
        return "", []

    all_lines: list[str] = []
    for jf in json_files:
        try:
            raw = jf.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError):
            continue

        if isinstance(data, dict):
            if "pages" in data:
                pages = data["pages"]
            else:
                # 新版格式：{filename: [{text_lines: [...]}]}
                pages = []
                for v in data.values():
                    if isinstance(v, list):
                        pages.extend(v)
        elif isinstance(data, list):
            pages = data
        else:
            continue

        for page in pages:
            if not isinstance(page, dict):
                continue
            text_lines = page.get("text_lines", [])
            for tl in text_lines:
                if isinstance(tl, dict):
                    t = tl.get("text", "").strip()
                    if t:
                        all_lines.append(t)

    text = "\n".join(all_lines)
    return text, all_lines


def _convert_langs_for_surya(tesseract_langs: str) -> str:
    """将 tesseract 语言代码转换为 surya 格式。"""
    mapping = {
        "chi_sim": "zh",
        "chi_tra": "zh",
        "eng": "en",
        "jpn": "ja",
        "kor": "ko",
    }
    parts = tesseract_langs.split("+")
    surya_parts: list[str] = []
    seen: set[str] = set()
    for p in parts:
        mapped = mapping.get(p.strip(), p.strip())
        if mapped not in seen:
            surya_parts.append(mapped)
            seen.add(mapped)
    return ",".join(surya_parts) if surya_parts else "zh,en"


def _warn(msg: str) -> None:
    print(f"[ocr][WARN] {msg}", file=sys.stderr)
