from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any
import json


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


class Character(BaseModel):
    id: str
    book_id: str
    canonical_name: str
    aliases_json: str
    frequency: int
    state: str
    created_at: str
    updated_at: str

    @property
    def aliases(self) -> List[str]:
        try:
            return json.loads(self.aliases_json or "[]")
        except json.JSONDecodeError:
            return []


class Relation(BaseModel):
    id: str
    book_id: str
    subject_type: str
    subject_id: str
    relation_type: str
    object_type: str
    object_id: str
    value_json: str
    state: str
    created_at: str
    updated_at: str

    @property
    def value(self) -> Dict[str, Any]:
        try:
            return json.loads(self.value_json or "{}")
        except json.JSONDecodeError:
            return {}


class CharacterListResponse(BaseModel):
    characters: List[Character]


class RelationListResponse(BaseModel):
    relations: List[Relation]


__all__ = ["CardCreate", "CardUpdate", "Character", "Relation", "CharacterListResponse", "RelationListResponse"]
