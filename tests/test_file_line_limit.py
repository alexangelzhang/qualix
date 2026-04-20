"""门禁测试：确保新文件不超过 400 行铁律。

白名单内的历史遗留文件只产生 warning，不 fail。
新文件超标直接 fail，阻止技术债继续积累。
"""

import subprocess
import sys


def test_file_line_limit():
    """所有非白名单 .py 文件必须 ≤ 400 行。"""
    result = subprocess.run(
        [sys.executable, "scripts/check_file_lines.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"文件行数门禁未通过:\n{result.stdout}\n{result.stderr}"
    )
