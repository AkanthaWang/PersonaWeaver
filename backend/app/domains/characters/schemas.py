from pydantic import BaseModel, Field, field_validator


class CardCreate(BaseModel):
    book_id: str
    name: str = Field(min_length=1, max_length=100)
    intro: str = Field(default="", max_length=4000)
    content: str = Field(default="", max_length=50000)
    source_entity_id: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError("角色名称不能为空")
        return value.strip()


class CardUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    intro: str = Field(default="", max_length=4000)
    content: str = Field(max_length=50000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        return CardCreate.clean_name(value)


__all__ = ["CardCreate", "CardUpdate"]
