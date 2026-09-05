"""SQLAlchemy ORM models.

Only portable column types are used so the same models run on PostgreSQL and SQLite.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(120), default="กรุงเทพมหานคร", nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    prayer_notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    posts: Mapped[list["ForumPost"]] = relationship(back_populates="author", cascade="all, delete-orphan")
    comments: Mapped[list["ForumComment"]] = relationship(back_populates="author", cascade="all, delete-orphan")
    likes: Mapped[list["ForumLike"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    donations: Mapped[list["Donation"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    @property
    def initial(self) -> str:
        return (self.full_name or self.email or "?").strip()[:1].upper()


class News(Base):
    __tablename__ = "news"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    # one of: article | event | announcement
    category: Mapped[str] = mapped_column(String(40), index=True, nullable=False, default="article")
    summary: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # CSS placeholder colour — avoids any external image dependency
    image_color: Mapped[str] = mapped_column(String(20), default="#1B5E3A", nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ForumPost(Base):
    __tablename__ = "forum_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # one of: qa | article | announce
    category: Mapped[str] = mapped_column(String(40), default="qa", nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    author: Mapped["User"] = relationship(back_populates="posts")
    comments: Mapped[list["ForumComment"]] = relationship(
        back_populates="post", cascade="all, delete-orphan", order_by="ForumComment.created_at"
    )
    likes: Mapped[list["ForumLike"]] = relationship(back_populates="post", cascade="all, delete-orphan")

    @property
    def like_count(self) -> int:
        return len(self.likes)

    @property
    def comment_count(self) -> int:
        return len(self.comments)

    @property
    def snippet(self) -> str:
        text = " ".join((self.content or "").split())
        return text[:110] + ("…" if len(text) > 110 else "")


class ForumComment(Base):
    __tablename__ = "forum_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("forum_posts.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    post: Mapped["ForumPost"] = relationship(back_populates="comments")
    author: Mapped["User"] = relationship(back_populates="comments")


class ForumLike(Base):
    __tablename__ = "forum_likes"
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_forum_like_post_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("forum_posts.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    post: Mapped["ForumPost"] = relationship(back_populates="likes")
    user: Mapped["User"] = relationship(back_populates="likes")


class Mosque(Base):
    __tablename__ = "mosques"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    address: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DonationCampaign(Base):
    __tablename__ = "donation_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    bank_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    bank_account_number: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    bank_account_name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    # plain-text payload actually encoded into the generated QR PNG
    qr_payload: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    qr_image_path: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    donations: Mapped[list["Donation"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")


class Donation(Base):
    __tablename__ = "donations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("donation_campaigns.id", ondelete="CASCADE"), index=True, nullable=False
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(String(400), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="donations")
    campaign: Mapped["DonationCampaign"] = relationship(back_populates="donations")
