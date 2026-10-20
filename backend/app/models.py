from datetime import datetime, timezone
from sqlalchemy import ForeignKey, String, Text, Boolean, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    tracks: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    prizes: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    url: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    deadlines: Mapped[list["Deadline"]] = relationship(
        cascade="all, delete-orphan", order_by="Deadline.due_at", lazy="selectin"
    )
    checklist: Mapped[list["ChecklistItem"]] = relationship(
        cascade="all, delete-orphan", order_by="ChecklistItem.position", lazy="selectin"
    )


class Deadline(Base):
    __tablename__ = "deadlines"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    label: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(30), default="other")  # submission|registration|results|event|other
    due_at: Mapped[datetime] = mapped_column(DateTime)  # naive UTC
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # set by bot webhooks


class ChecklistItem(Base):
    __tablename__ = "checklist_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    label: Mapped[str] = mapped_column(String(300))
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True)  # set by bot webhooks
