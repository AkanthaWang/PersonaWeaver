from typing import Optional

from pydantic import BaseModel, Field


class RetrievalQuery(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    book_id: Optional[str] = None
    limit: int = Field(default=10, ge=1, le=100)
