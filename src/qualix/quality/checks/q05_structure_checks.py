"""Q05 结构合规检查 façade — 实现已拆入 q05_checks/ 子包.

外部 import 路径向后兼容：所有在 finalize_checks.py 和 tests 中引用的符号均在此 re-export。
"""

from qualix.quality.checks.q05_checks import (
    check_eut_method_alignment,
    check_eut_then_phantom_methods,
    run_q05_structure_checks,
)
from qualix.quality.checks.q05_checks._checks_coverage import (
    _check_q05_git_diff_coverage,
)
from qualix.quality.checks.q05_checks._checks_eut_basic import (
    _check_wrong_directory,
)
from qualix.quality.checks.q05_checks._checks_eut_impl import (
    _check_eut_implementation_completeness,
)
from qualix.quality.checks.q05_checks._collect import (
    _collect_new_test_files_from_repos,
    _collect_supplemental_files,
)

__all__ = [
    "_check_eut_implementation_completeness",
    "_check_q05_git_diff_coverage",
    "_check_wrong_directory",
    "_collect_new_test_files_from_repos",
    "_collect_supplemental_files",
    "check_eut_method_alignment",
    "check_eut_then_phantom_methods",
    "run_q05_structure_checks",
]
