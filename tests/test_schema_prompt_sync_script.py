import subprocess
import sys
from pathlib import Path


def test_check_schema_prompt_sync_exit_zero() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "check_schema_prompt_sync.py"
    r = subprocess.run([sys.executable, str(script)], cwd=str(root), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
