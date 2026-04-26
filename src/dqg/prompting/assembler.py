"""Central prompt assembly with role-specific section contracts."""

from __future__ import annotations

from dataclasses import dataclass
from string import Formatter
from typing import TYPE_CHECKING, Any

from dqg.prompting.compiler import PromptBuild, PromptCompiler

if TYPE_CHECKING:
    from collections.abc import Mapping

    from dqg.prompting.spec import PromptAsset, PromptSpec


JUDGE_SECTION_ORDER = (
    "goal",
    "behavior_constraints",
    "gate_checklist",
    "evaluation_protocol",
    "rubric",
    "inputs",
    "bug_cases",
    "genes",
    "anti_rationalization",
    "output_schema",
)

JUDGE_REQUIRED_SECTIONS = (
    "goal",
    "behavior_constraints",
    "gate_checklist",
    "evaluation_protocol",
    "rubric",
    "inputs",
    "output_schema",
)

CRITIQUE_SECTION_ORDER = (
    "goal",
    "behavior_constraints",
    "gate_checklist",
    "evaluation_protocol",
    "inputs",
    "bug_cases",
    "critique_steps",
    "output_schema",
    "revision_instructions",
)

CRITIQUE_REQUIRED_SECTIONS = (
    "goal",
    "behavior_constraints",
    "gate_checklist",
    "evaluation_protocol",
    "inputs",
    "critique_steps",
    "output_schema",
)

PREFERENCE_SECTION_ORDER = (
    "goal",
    "behavior_constraints",
    "gate_checklist",
    "inputs",
    "comparison_steps",
    "output_schema",
)

PREFERENCE_REQUIRED_SECTIONS = PREFERENCE_SECTION_ORDER

REVIEW_CHAIN_SECTION_ORDER = (
    "goal",
    "judge_block",
    "critique_block",
    "preference_block",
    "completion_contract",
)

REVIEW_CHAIN_REQUIRED_SECTIONS = REVIEW_CHAIN_SECTION_ORDER


@dataclass(frozen=True)
class PromptSection:
    """Rendered section ready for assembly."""

    name: str
    content: str


@dataclass(frozen=True)
class PromptTemplate:
    """Minimal template wrapper for explicit variable rendering."""

    name: str
    template: str

    def render(self, **variables: Any) -> PromptSection:
        required = {field_name for _, field_name, _, _ in Formatter().parse(self.template) if field_name}
        missing = sorted(required - set(variables))
        if missing:
            raise ValueError(f"missing template variables for {self.name}: {', '.join(missing)}")
        return PromptSection(name=self.name, content=self.template.format(**variables))


@dataclass(frozen=True)
class PromptAssembler:
    """Assemble role prompts with a stable section order and required contract."""

    role: str
    section_order: tuple[str, ...]
    required_sections: tuple[str, ...]

    @classmethod
    def for_role(cls, role: str) -> PromptAssembler:
        if role == "judge":
            return cls(role=role, section_order=JUDGE_SECTION_ORDER, required_sections=JUDGE_REQUIRED_SECTIONS)
        if role == "critique":
            return cls(role=role, section_order=CRITIQUE_SECTION_ORDER, required_sections=CRITIQUE_REQUIRED_SECTIONS)
        if role == "preference":
            return cls(
                role=role, section_order=PREFERENCE_SECTION_ORDER, required_sections=PREFERENCE_REQUIRED_SECTIONS
            )
        if role == "review_chain":
            return cls(
                role=role, section_order=REVIEW_CHAIN_SECTION_ORDER, required_sections=REVIEW_CHAIN_REQUIRED_SECTIONS
            )
        raise ValueError(f"unsupported prompt role: {role}")

    def assemble(
        self,
        spec: PromptSpec,
        sections: Mapping[str, str | PromptSection],
        *,
        assets: tuple[PromptAsset, ...] = (),
        section_sources: dict[str, tuple[str, ...]] | None = None,
        project_id: str | None = None,
    ) -> PromptBuild:
        normalized = {name: _section_content(value) for name, value in sections.items()}
        missing = [name for name in self.required_sections if not normalized.get(name)]
        if missing:
            raise ValueError(f"missing required prompt sections for {self.role}: {', '.join(missing)}")

        ordered_sections = [(name, normalized[name]) for name in self.section_order if normalized.get(name)]
        return PromptCompiler().compile_named_sections(
            spec,
            sections=ordered_sections,
            assets=assets,
            section_sources=section_sources,
            project_id=project_id,
        )


def _section_content(value: str | PromptSection) -> str:
    if isinstance(value, PromptSection):
        return value.content
    return value
