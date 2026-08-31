from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nim: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    email: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    study_program: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    cohort: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    theses: Mapped[list["Thesis"]] = relationship(
        back_populates="student",
        cascade="all, delete-orphan",
    )


class Thesis(Base):
    __tablename__ = "theses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="Proposal")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    finalized_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    student: Mapped["Student"] = relationship(back_populates="theses")
    documents: Mapped[list["ThesisDocument"]] = relationship(
        back_populates="thesis",
        cascade="all, delete-orphan",
        order_by="ThesisDocument.version",
    )


class ThesisDocument(Base):
    __tablename__ = "thesis_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thesis_id: Mapped[int] = mapped_column(
        ForeignKey("theses.id", ondelete="CASCADE"),
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[str] = mapped_column(String(30), default="proposal")
    file_path: Mapped[str] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    thesis: Mapped["Thesis"] = relationship(back_populates="documents")
    comments: Mapped[list["ReviewComment"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class ReviewComment(Base):
    __tablename__ = "review_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("thesis_documents.id", ondelete="CASCADE"),
        index=True,
    )
    section: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    paragraph_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    selected_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    severity: Mapped[str] = mapped_column(String(30), default="Moderate")
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="Open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    document: Mapped["ThesisDocument"] = relationship(back_populates="comments")
