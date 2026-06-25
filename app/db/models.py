from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    BigInteger, String, Text, Integer, Boolean,
    DateTime, ForeignKey, JSON, Enum as SAEnum
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum


class Base(DeclarativeBase):
    pass


# ─── Enums ──────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    owner = "owner"
    admin = "admin"
    assistant = "assistant"
    employee = "employee"
    viewer = "viewer"


class UserStatus(str, enum.Enum):
    active = "active"
    blocked = "blocked"


class TaskStatus(str, enum.Enum):
    new = "new"
    in_progress = "in_progress"
    done = "done"
    deleted = "deleted"
    moved = "moved"


class TaskPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class TaskSource(str, enum.Enum):
    text = "text"
    voice = "voice"


class NoteType(str, enum.Enum):
    note = "note"
    training = "training"
    project_note = "project_note"
    memory = "memory"


class MemoryType(str, enum.Enum):
    personal = "personal"
    project = "project"
    global_memory = "global"     # общий чат — без проекта


class ProjectStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


class InviteStatus(str, enum.Enum):
    pending = "pending"
    used = "used"
    expired = "expired"


class ReminderStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    cancelled = "cancelled"


# ─── Models ─────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(64))
    first_name: Mapped[Optional[str]] = mapped_column(String(128))
    last_name: Mapped[Optional[str]] = mapped_column(String(128))
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), default=UserRole.viewer)
    status: Mapped[UserStatus] = mapped_column(SAEnum(UserStatus), default=UserStatus.active)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    tasks: Mapped[List["Task"]] = relationship(back_populates="user")
    memories: Mapped[List["Memory"]] = relationship(back_populates="user")
    notes: Mapped[List["Note"]] = relationship(back_populates="user")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(SAEnum(ProjectStatus), default=ProjectStatus.active)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tasks: Mapped[List["Task"]] = relationship(back_populates="project")
    memories: Mapped[List["Memory"]] = relationship(back_populates="project")
    notes: Mapped[List["Note"]] = relationship(back_populates="project")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    date: Mapped[Optional[str]] = mapped_column(String(10))      # YYYY-MM-DD
    time: Mapped[Optional[str]] = mapped_column(String(5))       # HH:MM
    priority: Mapped[TaskPriority] = mapped_column(SAEnum(TaskPriority), default=TaskPriority.medium)
    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), default=TaskStatus.new)
    source: Mapped[TaskSource] = mapped_column(SAEnum(TaskSource), default=TaskSource.text)
    original_text: Mapped[Optional[str]] = mapped_column(Text)
    transcript: Mapped[Optional[str]] = mapped_column(Text)
    reminder_time: Mapped[Optional[str]] = mapped_column(String(20))
    reminder_rule: Mapped[Optional[str]] = mapped_column(String(256))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assigned_to_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    is_personal: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="tasks", foreign_keys=[user_id])
    project: Mapped[Optional["Project"]] = relationship(back_populates="tasks")
    reminders: Mapped[List["Reminder"]] = relationship(back_populates="task")


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id"))
    type: Mapped[MemoryType] = mapped_column(SAEnum(MemoryType), default=MemoryType.personal)
    title: Mapped[Optional[str]] = mapped_column(String(256))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[int] = mapped_column(Integer, default=5)   # 1–10
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="memories")
    project: Mapped[Optional["Project"]] = relationship(back_populates="memories")


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id"))
    type: Mapped[NoteType] = mapped_column(SAEnum(NoteType), default=NoteType.note)
    title: Mapped[Optional[str]] = mapped_column(String(256))
    content: Mapped[Optional[str]] = mapped_column(Text)
    data_json: Mapped[Optional[dict]] = mapped_column(JSON)
    source: Mapped[TaskSource] = mapped_column(SAEnum(TaskSource), default=TaskSource.text)
    original_text: Mapped[Optional[str]] = mapped_column(Text)
    transcript: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    recorded_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    user: Mapped["User"] = relationship(back_populates="notes")
    project: Mapped[Optional["Project"]] = relationship(back_populates="notes")


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id"))
    remind_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[ReminderStatus] = mapped_column(SAEnum(ReminderStatus), default=ReminderStatus.pending)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    task: Mapped[Optional["Task"]] = relationship(back_populates="reminders")


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), default=UserRole.viewer)
    project_ids: Mapped[Optional[list]] = mapped_column(JSON)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[InviteStatus] = mapped_column(SAEnum(InviteStatus), default=InviteStatus.pending)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProjectAccess(Base):
    __tablename__ = "project_access"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    access_level: Mapped[str] = mapped_column(String(32), default="view")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    pin_verified_until: Mapped[Optional[datetime]] = mapped_column(DateTime)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    details: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PdfReport(Base):
    __tablename__ = "pdf_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(256))
    file_url: Mapped[Optional[str]] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ImageGeneration(Base):
    __tablename__ = "image_generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("projects.id"))
    prompt: Mapped[str] = mapped_column(Text)
    final_prompt: Mapped[Optional[str]] = mapped_column(Text)
    image_url: Mapped[Optional[str]] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
