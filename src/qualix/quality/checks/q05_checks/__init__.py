"""q05_checks: Q05 结构合规检查子包（façade __init__）."""

from ._checks_eut_impl import check_eut_method_alignment
from ._checks_production import check_eut_then_phantom_methods
from ._orchestrator import run_q05_structure_checks

__all__ = [
    "check_eut_method_alignment",
    "check_eut_then_phantom_methods",
    "run_q05_structure_checks",
]
