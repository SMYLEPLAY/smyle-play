"""
D3 Confiance (07/07) — signalement de contenu (conformité DSA, art. 16).

Un signalement peut être ANONYME (le DSA impose un mécanisme accessible à
tous) : reporter_id nullable, reporter_email facultatif pour l'accusé de
réception. Cycle de vie : new → reviewed → actioned | rejected.

target_type en String (pas d'enum DB) : track / prompt / image / profil /
playlist / album — extensible sans migration.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ReportReason(str, enum.Enum):
    CONTENU_ILLEGAL = "contenu_illegal"
    CONTREFACON     = "contrefacon"
    HAINE_VIOLENCE  = "haine_violence"
    NUDITE          = "nudite"
    SPAM_ARNAQUE    = "spam_arnaque"
    AUTRE           = "autre"


class ReportStatus(str, enum.Enum):
    NEW      = "new"
    REVIEWED = "reviewed"
    ACTIONED = "actioned"
    REJECTED = "rejected"


class ContentReport(Base):
    __tablename__ = "content_reports"
    __table_args__ = (
        CheckConstraint(
            "reporter_id IS NOT NULL OR reporter_email IS NOT NULL "
            "OR detail IS NOT NULL",
            name="ck_content_reports_not_empty",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    reporter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Signalement anonyme : email facultatif pour l'accusé de réception.
    reporter_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    reason: Mapped[ReportReason] = mapped_column(
        SQLEnum(
            ReportReason,
            name="report_reason",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ReportStatus] = mapped_column(
        SQLEnum(
            ReportStatus,
            name="report_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=ReportStatus.NEW,
        server_default=ReportStatus.NEW.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
