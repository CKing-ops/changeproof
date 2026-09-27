from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Provenance(BaseModel):
    """Where a fact came from: a repo-relative path and 1-based line range."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    file: str = Field(min_length=1)
    line: int = Field(ge=1)
    end_line: int | None = Field(default=None, ge=1)

    # PURPOSE: KEEPS PATHS REPO-RELATIVE SO EVIDENCE REPRODUCES ON ANY MACHINE
    @field_validator("file")
    @classmethod
    def relative_posix_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("file must be a repo-relative path without '..'")
        return value

    # PURPOSE: REJECTS A RANGE THAT ENDS BEFORE IT STARTS
    @model_validator(mode="after")
    def ordered_range(self) -> "Provenance":
        if self.end_line is not None and self.end_line < self.line:
            raise ValueError("end_line is before line")
        return self

    # PURPOSE: RENDERS AS FILE:LINE OR FILE:LINE-END
    def __str__(self) -> str:
        span = f"-{self.end_line}" if self.end_line and self.end_line != self.line else ""
        return f"{self.file}:{self.line}{span}"
