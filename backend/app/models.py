import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Uuid, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from . import config


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


def _id():
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def _created():
    return mapped_column(DateTime(timezone=True), default=now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _id()
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True)   # 비어 있으면 익명
    email: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = _created()
    watches: Mapped[list["Watch"]] = relationship(cascade="all, delete-orphan")
    sessions: Mapped[list["SessionToken"]] = relationship(cascade="all, delete-orphan")


class SessionToken(Base):
    """브라우저 한 개의 로그인 상태. 한 사용자가 여러 기기에서 쓸 수 있도록 사용자와 분리했다."""
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = _created()


class Watch(Base):
    __tablename__ = "watches"
    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    brand: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(100))
    bph: Mapped[int | None] = mapped_column(Integer)
    photo_key: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = _created()
    measurements: Mapped[list["Measurement"]] = relationship(
        cascade="all, delete-orphan", order_by="Measurement.created_at"
    )
    readings: Mapped[list["Reading"]] = relationship(cascade="all, delete-orphan", order_by="Reading.taken_at")


class Measurement(Base):
    __tablename__ = "measurements"
    id: Mapped[uuid.UUID] = _id()
    watch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("watches.id"), index=True)
    # pending → queued → processing → done | low_confidence | failed
    status: Mapped[str] = mapped_column(String(20), default="pending")
    audio_key: Mapped[str] = mapped_column(String(200))
    rate_s_per_day: Mapped[float | None] = mapped_column(Float)
    rate_first_half: Mapped[float | None] = mapped_column(Float)
    rate_second_half: Mapped[float | None] = mapped_column(Float)
    beat_error_ms: Mapped[float | None] = mapped_column(Float)
    quality: Mapped[float | None] = mapped_column(Float)
    detected_bph: Mapped[int | None] = mapped_column(Integer)
    error_reason: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = _created()
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    watch: Mapped[Watch] = relationship(back_populates="measurements")


class Reading(Base):
    """사진 기록 한 건: 찍은 순간의 실제 시각과, 그때 시계가 실제보다 몇 초 앞서 있었는지."""
    __tablename__ = "readings"
    id: Mapped[uuid.UUID] = _id()
    watch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("watches.id"), index=True)
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    offset_seconds: Mapped[float] = mapped_column(Float)          # +면 시계가 빠르다
    reset: Mapped[bool] = mapped_column(Boolean, default=False)   # 시간을 다시 맞춘 직후의 기록 = 새 기준점
    photo_key: Mapped[str | None] = mapped_column(String(200))
    watch: Mapped[Watch] = relationship(back_populates="readings")


engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)
