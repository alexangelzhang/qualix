from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class SourceLocation(BaseModel):
    """源码坐标，用于行级血缘追踪."""

    file: str = Field(min_length=1)
    line_start: int = Field(ge=1)
    line_end: int | None = Field(default=None, ge=1)
    class_name: str = ""
    method_name: str = ""
    repo: str = ""

    @model_validator(mode="after")
    def line_end_gte_line_start(self) -> SourceLocation:
        if self.line_end is not None and self.line_end < self.line_start:
            raise ValueError(f"line_end ({self.line_end}) must be >= line_start ({self.line_start})")
        return self
