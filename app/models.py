"""SQLAlchemy ORM models.

Only portable column types are used so the same models run on PostgreSQL and SQLite.
"""
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
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
    # 2D character shown on the home screen: male | female | symbol.
    # "symbol" is a non-figurative option for those who avoid depicting living beings.
    avatar_style: Mapped[str] = mapped_column(String(20), default="symbol", nullable=False)
    # Per-prayer notification toggles (P0 spec: "แยกรายเวลาได้").
    notify_fajr: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_dhuhr: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_asr: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_maghrib: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_isha: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    posts: Mapped[list["ForumPost"]] = relationship(back_populates="author", cascade="all, delete-orphan")
    comments: Mapped[list["ForumComment"]] = relationship(back_populates="author", cascade="all, delete-orphan")
    likes: Mapped[list["ForumLike"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    donations: Mapped[list["Donation"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    outfit_choice: Mapped["UserOutfit | None"] = relationship(cascade="all, delete-orphan")
    background_choice: Mapped["UserBackground | None"] = relationship(cascade="all, delete-orphan")
    outfit_unlocks: Mapped[list["UserOutfitUnlock"]] = relationship(cascade="all, delete-orphan")
    background_unlocks: Mapped[list["UserBackgroundUnlock"]] = relationship(cascade="all, delete-orphan")

    @property
    def initial(self) -> str:
        return (self.full_name or self.email or "?").strip()[:1].upper()

    @property
    def outfit(self) -> dict | None:
        """The outfit the character wears, or None for the plain 2D mascot."""
        from app.outfits import OUTFITS, is_wearable

        if self.outfit_choice is None:
            return None
        key = self.outfit_choice.outfit_key
        outfit = OUTFITS.get(key)
        # An outfit only fits the character it was drawn for, and must be available to them.
        if outfit is None or outfit["gender"] != self.avatar_style:
            return None
        if not is_wearable(key, outfit, self.unlocked_outfits):
            return None
        return {"key": self.outfit_choice.outfit_key, **outfit}

    @property
    def unread_mail_count(self) -> int:
        """Badge on the mailbox icon (every page header)."""
        from sqlalchemy import func, select
        from sqlalchemy.orm import object_session

        db = object_session(self)
        if db is None:
            return 0
        return db.scalar(select(func.count(Mail.id)).where(Mail.user_id == self.id, Mail.read_at.is_(None))) or 0

    @property
    def owned_backgrounds(self) -> set[str]:
        return {u.background_key for u in self.background_unlocks}

    @property
    def unlocked_outfits(self) -> set[str]:
        return {u.outfit_key for u in self.outfit_unlocks}

    @property
    def background(self) -> dict:
        """Background behind the character; falls back to the default CSS scene."""
        from app.outfits import BACKGROUNDS, DEFAULT_BACKGROUND, background_available

        key = self.background_choice.background_key if self.background_choice else DEFAULT_BACKGROUND
        if not background_available(key, self.owned_backgrounds):  # removed, or hidden and not owned
            key = DEFAULT_BACKGROUND
        return {"key": key, **BACKGROUNDS[key]}

    @property
    def has_character(self) -> bool:
        """male / female draw a character that stands on a background; "symbol" doesn't."""
        return self.avatar_style in ("male", "female")

    @property
    def character_image(self) -> str:
        outfit = self.outfit
        if outfit:
            return outfit["image"]
        if self.has_character:
            from app.outfits import DEFAULT_CHARACTER

            # character only, transparent — the background comes from the chosen scene
            return DEFAULT_CHARACTER[self.avatar_style]
        return f"/static/img/mascot-{self.avatar_style}.svg"


class UserOutfit(Base):
    """Outfit currently worn by a user's character (one row per user; key from app/outfits.py).

    Its own table so it is created on startup by create_all — no migration of `users` needed.
    """

    __tablename__ = "user_outfits"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    outfit_key: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class Mail(Base):
    """A message in a user's mailbox (กล่องจดหมาย), optionally carrying an outfit gift.

    Sent by the team (python -m app.send_gift); the gift is unlocked when the user claims it.
    New table, created on startup by create_all.
    """

    __tablename__ = "mail"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    gift_outfit_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    gift_background_key: Mapped[str | None] = mapped_column(String(40), nullable=True)  # added later, see database.py
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserOutfitUnlock(Base):
    """An outfit a user has earned (app/services/rewards.py); kept for good once earned.

    `notified` flips once the "you got a new outfit" banner has been shown. New table.
    """

    __tablename__ = "user_outfit_unlocks"
    __table_args__ = (UniqueConstraint("user_id", "outfit_key", name="uq_outfit_unlock_once"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    outfit_key: Mapped[str] = mapped_column(String(40), nullable=False)
    unlocked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    notified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class UserBackgroundUnlock(Base):
    """A background a user owns (e.g. a limited one received as a mailbox gift). New table."""

    __tablename__ = "user_background_unlocks"
    __table_args__ = (UniqueConstraint("user_id", "background_key", name="uq_background_unlock_once"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    background_key: Mapped[str] = mapped_column(String(40), nullable=False)
    unlocked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class UserBackground(Base):
    """Background chosen behind a user's character (one row per user; key from app/outfits.py)."""

    __tablename__ = "user_backgrounds"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    background_key: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


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

    events: Mapped[list["MosqueEvent"]] = relationship(back_populates="mosque", cascade="all, delete-orphan")


class MosqueEvent(Base):
    """A recurring/one-off mosque activity (ญุมอะฮ์, สอนกุรอาน, บรรยาย, อิฟฏอร ฯลฯ)."""

    __tablename__ = "mosque_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mosque_id: Mapped[int] = mapped_column(ForeignKey("mosques.id", ondelete="CASCADE"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # freeform, e.g. "ทุกวันศุกร์ 12:30 น." — no recurrence engine needed for this scale
    schedule_text: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    mosque: Mapped["Mosque"] = relationship(back_populates="events")


class MosqueAttendance(Base):
    """'ฉันไปด้วย' RSVP — one row per user, per mosque, per prayer, per day."""

    __tablename__ = "mosque_attendance"
    __table_args__ = (
        UniqueConstraint("mosque_id", "user_id", "prayer_key", "attend_date", name="uq_attendance_once"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mosque_id: Mapped[int] = mapped_column(ForeignKey("mosques.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    prayer_key: Mapped[str] = mapped_column(String(20), nullable=False)  # Fajr | Dhuhr | Asr | Maghrib | Isha
    attend_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    mosque: Mapped["Mosque"] = relationship()
    user: Mapped["User"] = relationship()


class MosqueCheckin(Base):
    """Location-verified check-in at an OpenStreetMap mosque (see app/services/checkin.py).

    At most one per user per prayer per day, across all mosques. The visitor's coordinates
    are only used to verify the distance and are never stored.
    """

    __tablename__ = "mosque_checkins"
    __table_args__ = (
        UniqueConstraint("user_id", "prayer_key", "prayer_date", name="uq_checkin_once_per_prayer"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    osm_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)  # "node/123", "way/456"
    # name at check-in time, so history still reads right if the OSM name changes later
    mosque_name: Mapped[str] = mapped_column(String(200), nullable=False)
    prayer_key: Mapped[str] = mapped_column(String(20), nullable=False)  # Fajr | Dhuhr | Asr | Maghrib | Isha
    # the day the prayer belongs to (an Isha check-in after midnight counts for the previous day)
    prayer_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped["User"] = relationship()


class PrayerNotice(Base):
    """A "you missed <prayer>" notice already raised for a user, so it is shown only once.

    New table, created on startup by create_all.
    """

    __tablename__ = "prayer_notices"
    __table_args__ = (UniqueConstraint("user_id", "date", "prayer", name="uq_prayer_notice_once"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    prayer: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class PrayerLog(Base):
    """One of the five obligatory prayers marked as prayed (app/services/prayer_log.py).

    Private to its user: only ever read back for the logged-in owner. New table, so it is
    created on startup by create_all — existing tables and rows are untouched.
    """

    __tablename__ = "prayer_log"
    __table_args__ = (UniqueConstraint("user_id", "date", "prayer", name="uq_prayer_log_once"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    # the day the prayer belongs to (an Isha check-in after midnight counts for the previous day)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    prayer: Mapped[str] = mapped_column(String(10), nullable=False)  # fajr | dhuhr | asr | maghrib | isha
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)  # on_time | qada (set by the server)
    source: Mapped[str] = mapped_column(String(10), default="manual", nullable=False)  # manual | checkin
    in_congregation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # OSM id of the mosque ("node/123") when source == checkin; the finder's mosques are
    # OpenStreetMap places, not rows of the old `mosques` table.
    mosque_id: Mapped[str | None] = mapped_column(String(32), nullable=True)


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
