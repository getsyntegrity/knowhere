"""CodeLocation value object — source location span within a File."""

from pydantic import BaseModel, Field, field_validator


class CodeLocation(BaseModel):
    """Represents a source location span within a File.
    
    Shared across Symbol, Chunk, and Reference entities.
    
    Invariants:
    - start_line <= end_line; if equal, start_column <= end_column
    - All values are positive integers (1-indexed)
    - The location must fall within the bounds of the parent File
    """
    
    model_config = {"frozen": True}
    
    start_line: int = Field(..., ge=1, description="Starting line number (1-indexed)")
    start_column: int = Field(..., ge=1, description="Starting column number (1-indexed)")
    end_line: int = Field(..., ge=1, description="Ending line number (1-indexed)")
    end_column: int = Field(..., ge=1, description="Ending column number (1-indexed)")
    
    @field_validator("end_line")
    @classmethod
    def end_line_not_before_start(cls, v: int, info) -> int:
        start_line = info.data.get("start_line")
        if start_line is not None and v < start_line:
            raise ValueError("end_line must be >= start_line")
        return v
    
    @field_validator("end_column")
    @classmethod
    def end_column_not_before_start(cls, v: int, info) -> int:
        start_line = info.data.get("start_line")
        end_line = info.data.get("end_line")
        start_column = info.data.get("start_column")
        if start_line is not None and end_line is not None and start_column is not None:
            if end_line == start_line and v < start_column:
                raise ValueError("end_column must be >= start_column when on same line")
        return v
    
    def __str__(self) -> str:
        """Serialize to string format: start_line:start_column-end_line:end_column"""
        return f"{self.start_line}:{self.start_column}-{self.end_line}:{self.end_column}"
    
    @classmethod
    def from_string(cls, s: str) -> "CodeLocation":
        """Parse from string format: start_line:start_column-end_line:end_column"""
        start_part, end_part = s.split("-")
        start_line, start_column = map(int, start_part.split(":"))
        end_line, end_column = map(int, end_part.split(":"))
        return cls(
            start_line=start_line,
            start_column=start_column,
            end_line=end_line,
            end_column=end_column,
        )
