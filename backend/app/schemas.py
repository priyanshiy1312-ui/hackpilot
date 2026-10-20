from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator

Kind = Literal["submission", "registration", "results", "event", "other"]


class DeadlineIn(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    kind: Kind = "other"
    due_at: datetime

    @field_validator("due_at")
    @classmethod
    def to_naive_utc(cls, v: datetime):
        if v.tzinfo:
            from datetime import timezone
            v = v.astimezone(timezone.utc).replace(tzinfo=None)
        return v


class EventIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: str = ""
    tracks: list[str] = []
    prizes: list[str] = []
    deadlines: list[DeadlineIn] = Field(min_length=1, description="At least one deadline is required")
    checklist: list[str] = []


class ExtractIn(BaseModel):
    text: str = Field(min_length=20, max_length=300000)
    use_llm: bool = False


def utc_naive(v: datetime) -> datetime:
    from datetime import timezone
    return v.astimezone(timezone.utc).replace(tzinfo=None) if v.tzinfo else v


class TaskHook(BaseModel):
    event_id: int
    external_id: str = Field(min_length=1, max_length=100)
    label: str | None = Field(default=None, min_length=1, max_length=300)
    done: bool | None = None


class DeadlineHook(BaseModel):
    event_id: int
    external_id: str = Field(min_length=1, max_length=100)
    label: str | None = Field(default=None, min_length=1, max_length=200)
    kind: Kind | None = None
    due_at: datetime | None = None


class ChecklistIn(BaseModel):
    label: str = Field(min_length=1, max_length=300)


class ChecklistPatch(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=300)
    done: bool | None = None


class OrderIn(BaseModel):
    ids: list[int]
