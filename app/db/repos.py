from datetime import datetime
from typing import Optional, List
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    User, UserRole, UserStatus,
    Project, ProjectStatus,
    Memory, MemoryType,
    Note, NoteType, TaskSource,
    AuditLog, Invite, InviteStatus,
)


# ─── Users ───────────────────────────────────────────────────────────────────

async def get_or_create_user(session: AsyncSession, telegram_id: int,
                              username: str = None, first_name: str = None,
                              last_name: str = None) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    else:
        user.last_seen_at = datetime.utcnow()
        if username:
            user.username = username
        await session.commit()
    return user


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[User]:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def set_user_role(session: AsyncSession, user_id: int, role: UserRole) -> Optional[User]:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user:
        user.role = role
        await session.commit()
    return user


async def get_all_users(session: AsyncSession) -> List[User]:
    result = await session.execute(select(User))
    return result.scalars().all()


# ─── Projects ────────────────────────────────────────────────────────────────

async def create_project(session: AsyncSession, user_id: int, title: str,
                          description: str = None) -> Project:
    project = Project(user_id=user_id, title=title, description=description)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def get_user_projects(session: AsyncSession, user_id: int) -> List[Project]:
    result = await session.execute(
        select(Project).where(
            and_(Project.user_id == user_id, Project.status == ProjectStatus.active)
        ).order_by(Project.created_at.desc())
    )
    return result.scalars().all()


async def get_project_by_title(session: AsyncSession, user_id: int,
                                title: str) -> Optional[Project]:
    result = await session.execute(
        select(Project).where(
            and_(
                Project.user_id == user_id,
                Project.title.ilike(f"%{title}%"),
                Project.status == ProjectStatus.active,
            )
        )
    )
    return result.scalars().first()


async def get_project_by_id(session: AsyncSession, project_id: int) -> Optional[Project]:
    result = await session.execute(select(Project).where(Project.id == project_id))
    return result.scalar_one_or_none()


# ─── Memories ────────────────────────────────────────────────────────────────

async def save_memory(session: AsyncSession, user_id: int, content: str,
                      memory_type: MemoryType = MemoryType.personal,
                      project_id: int = None, title: str = None,
                      importance: int = 5) -> Memory:
    memory = Memory(
        user_id=user_id,
        project_id=project_id,
        type=memory_type,
        title=title,
        content=content,
        importance=importance,
    )
    session.add(memory)
    await session.commit()
    await session.refresh(memory)
    return memory


async def get_user_memories(session: AsyncSession, user_id: int,
                             memory_type: MemoryType = None,
                             project_id: int = None) -> List[Memory]:
    conditions = [Memory.user_id == user_id]
    if memory_type:
        conditions.append(Memory.type == memory_type)
    if project_id is not None:
        conditions.append(Memory.project_id == project_id)

    result = await session.execute(
        select(Memory).where(and_(*conditions))
        .order_by(Memory.importance.desc(), Memory.created_at.desc())
        .limit(30)
    )
    return result.scalars().all()


async def get_memories_summary(session: AsyncSession, user_id: int,
                                project_id: int = None) -> str:
    """Return memories as a compact text for Claude context."""
    if project_id:
        memories = await get_user_memories(session, user_id,
                                            memory_type=MemoryType.project,
                                            project_id=project_id)
    else:
        personal = await get_user_memories(session, user_id, MemoryType.personal)
        global_mem = await get_user_memories(session, user_id, MemoryType.global_memory)
        memories = personal + global_mem

    if not memories:
        return ""
    return "\n".join(f"- {m.content}" for m in memories)


# ─── Notes ───────────────────────────────────────────────────────────────────

async def create_note(session: AsyncSession, user_id: int,
                       note_type: NoteType, content: str,
                       title: str = None, project_id: int = None,
                       data_json: dict = None, source: TaskSource = TaskSource.text,
                       original_text: str = None, transcript: str = None,
                       recorded_at: datetime = None) -> Note:
    note = Note(
        user_id=user_id,
        project_id=project_id,
        type=note_type,
        title=title,
        content=content,
        data_json=data_json,
        source=source,
        original_text=original_text,
        transcript=transcript,
        recorded_at=recorded_at or datetime.utcnow(),
    )
    session.add(note)
    await session.commit()
    await session.refresh(note)
    return note


async def get_trainings(session: AsyncSession, user_id: int) -> List[Note]:
    result = await session.execute(
        select(Note).where(
            and_(Note.user_id == user_id, Note.type == NoteType.training)
        ).order_by(Note.recorded_at.desc())
    )
    return result.scalars().all()


# ─── Audit ───────────────────────────────────────────────────────────────────

async def log_action(session: AsyncSession, actor_user_id: int, action: str,
                      target_user_id: int = None, details: dict = None):
    log = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        target_user_id=target_user_id,
        details=details,
    )
    session.add(log)
    await session.commit()


async def get_audit_logs(session: AsyncSession, limit: int = 50) -> List[AuditLog]:
    result = await session.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    )
    return result.scalars().all()


# ─── Invites ─────────────────────────────────────────────────────────────────

async def create_invite(session: AsyncSession, created_by_user_id: int,
                         role: str, project_ids: list = None,
                         expires_at: datetime = None) -> Invite:
    import secrets
    code = secrets.token_urlsafe(8)
    invite = Invite(
        code=code,
        created_by_user_id=created_by_user_id,
        role=role,
        project_ids=project_ids or [],
        expires_at=expires_at,
        max_uses=1,
    )
    session.add(invite)
    await session.commit()
    await session.refresh(invite)
    return invite


async def get_invite_by_code(session: AsyncSession, code: str) -> Optional[Invite]:
    result = await session.execute(select(Invite).where(Invite.code == code))
    return result.scalar_one_or_none()


async def use_invite(session: AsyncSession, invite: Invite) -> bool:
    """Mark invite as used. Returns False if expired or exhausted."""
    now = datetime.utcnow()
    if invite.expires_at and invite.expires_at < now:
        invite.status = InviteStatus.expired
        await session.commit()
        return False
    if invite.used_count >= invite.max_uses:
        return False
    invite.used_count += 1
    if invite.used_count >= invite.max_uses:
        invite.status = InviteStatus.used
    await session.commit()
    return True
