from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.m1 import JsonType, new_uuid, now_utc


class WikiPage(Base):
    __tablename__ = "wiki_pages"
    __table_args__ = (UniqueConstraint("kb_id", "slug", name="uq_wiki_pages_kb_slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    kb_id: Mapped[str] = mapped_column(ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    page_type: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[str] = mapped_column(Text(), default="", nullable=False)
    content: Mapped[str] = mapped_column(Text(), default="", nullable=False)
    category_path: Mapped[list[str]] = mapped_column(JsonType, default=list, nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JsonType, default=list, nullable=False)
    source_refs: Mapped[list[str]] = mapped_column(JsonType, default=list, nullable=False)
    current_revision_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    revisions: Mapped[list["WikiPageRevision"]] = relationship(
        back_populates="page",
        cascade="all, delete-orphan",
        primaryjoin="WikiPage.id == WikiPageRevision.page_id",
    )


class WikiPageRevision(Base):
    __tablename__ = "wiki_page_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    page_id: Mapped[str] = mapped_column(
        ForeignKey("wiki_pages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text(), nullable=False)
    editor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    editor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    change_summary: Mapped[str] = mapped_column(Text(), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    page: Mapped[WikiPage] = relationship(back_populates="revisions")


class Entity(Base):
    __tablename__ = "entities"
    __table_args__ = (UniqueConstraint("kb_id", "slug", name="uq_entities_kb_slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    kb_id: Mapped[str] = mapped_column(ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    slug: Mapped[str] = mapped_column(String(256), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), default="other", nullable=False)
    description: Mapped[str] = mapped_column(Text(), default="", nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JsonType, default=list, nullable=False)
    wiki_page_id: Mapped[str | None] = mapped_column(ForeignKey("wiki_pages.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Relation(Base):
    __tablename__ = "relations"
    __table_args__ = (
        UniqueConstraint(
            "source_entity_id",
            "target_entity_id",
            "relation_type",
            name="uq_relations_source_target_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    kb_id: Mapped[str] = mapped_column(ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    source_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), nullable=False)
    target_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_chunk_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
