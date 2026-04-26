"""Prompt Harness primitives.

This package treats prompts as versioned, observable engineering artifacts.
Domain modules still own skill/rubric/protocol semantics; Prompt Harness owns
compilation metadata, assembly order, and manifest persistence.
"""

from dqg.prompting.assembler import PromptAssembler, PromptSection, PromptTemplate
from dqg.prompting.compiler import PromptBuild, PromptCompiler
from dqg.prompting.manifest import PromptManifest, write_prompt_manifest
from dqg.prompting.policy import PromptPolicyIssue, PromptPolicyResult, validate_prompt_artifact
from dqg.prompting.record import record_prompt_manifest
from dqg.prompting.spec import PromptAsset, PromptSpec

__all__ = [
    "PromptAssembler",
    "PromptAsset",
    "PromptBuild",
    "PromptCompiler",
    "PromptManifest",
    "PromptPolicyIssue",
    "PromptPolicyResult",
    "PromptSection",
    "PromptSpec",
    "PromptTemplate",
    "record_prompt_manifest",
    "validate_prompt_artifact",
    "write_prompt_manifest",
]
