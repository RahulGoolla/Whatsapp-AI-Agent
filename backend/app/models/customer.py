import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CustomerProfile(Base):
    """
    Persistent customer profile & state memory across WhatsApp sessions.
    Tracks customer identity (phone, name, company), chosen product track, and purchase intent.
    """

    __tablename__ = "customer_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    phone_number: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    business_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Product Track: "catalogue", "virtual_tryon", "ai_kiosk", "both", "unassigned"
    active_track: Mapped[str] = mapped_column(
        String(50), nullable=False, default="unassigned"
    )

    # Intent State: "greeting", "exploring", "evaluating_pricing", "ready_to_buy", "sample_requested", "human_handoff"
    intent_state: Mapped[str] = mapped_column(
        String(50), nullable=False, default="greeting"
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    leads: Mapped[list["UrgentLead"]] = relationship(
        "UrgentLead", back_populates="customer", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<CustomerProfile phone={self.phone_number} name={self.name} track={self.active_track}>"


class UrgentLead(Base):
    """
    Urgent CRM lead box for sales team & developer CRM sync.
    Created when customer requests demo, custom deal, buy guidance, or human handoff.
    """

    __tablename__ = "urgent_leads"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customer_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    customer_phone: Mapped[str] = mapped_column(String(50), nullable=False)
    customer_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    business_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active_track: Mapped[str] = mapped_column(String(50), nullable=False, default="catalogue")
    requirement_summary: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Status: "urgent", "in_progress", "contacted", "closed"
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="urgent")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    customer: Mapped[CustomerProfile | None] = relationship(
        "CustomerProfile", back_populates="leads"
    )

    def __repr__(self) -> str:
        return f"<UrgentLead id={self.id} phone={self.customer_phone} name={self.customer_name} status={self.status}>"
