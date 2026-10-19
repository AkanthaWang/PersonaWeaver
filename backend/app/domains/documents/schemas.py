from typing import Optional

from pydantic import BaseModel, Field, model_validator


class ExtractRequest(BaseModel):
    book_id: str
    max_chapters: Optional[int] = Field(default=None, ge=1, le=1000)
    chapter_start: Optional[int] = Field(default=None, ge=1)
    chapter_end: Optional[int] = Field(default=None, ge=1)
    force: bool = False

    @model_validator(mode="after")
    def validate_range(self):
        if (self.chapter_start is None) != (self.chapter_end is None):
            raise ValueError("章节区间必须同时指定起点和终点")
        if self.chapter_start is not None:
            if self.max_chapters is not None:
                raise ValueError("章节区间与前 N 章不能同时使用")
            if self.chapter_start > self.chapter_end:
                raise ValueError("章节起点不能大于终点")
        return self


class ResolutionRequest(BaseModel):
    revision: int = Field(ge=0)
    action: str = Field(pattern="^(merge|split)$")
    source_ids: list[str] = Field(min_length=1, max_length=10000)
    other_source_ids: list[str] = Field(default_factory=list, max_length=10000)


__all__ = ["ExtractRequest"]
