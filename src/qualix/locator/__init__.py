"""Evidence locator providers.

Locators only produce evidence candidates.  They do not decide whether a gate
passes or fails.
"""

from qualix.locator.ripgrep_locator import RipgrepLocator
from qualix.schemas.evidence import EvidenceCitation, EvidenceConfidence, EvidenceKind

__all__ = [
    "EvidenceCitation",
    "EvidenceConfidence",
    "EvidenceKind",
    "RipgrepLocator",
]
