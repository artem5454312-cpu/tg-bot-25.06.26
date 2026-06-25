from datetime import date, datetime
from typing import Optional, List
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Task, TaskStatus, TaskSource, TaskPriority


async def create_task(
    session: AsyncSession,
    user_id: int,
    title: str,
    description: Optional[str] = None,
    task_date: Optional[str] = None,
    task_time: Optional[str] = None,
    project_id: Optional[int] = None,
    priority: TaskPriority = TaskPriority.medium,
    source: TaskSource = TaskSource.text,
    original_text: Optional[str] = None,
    transcript: Optional[str] = None,
    reminder_time: Optional[str] = None,
    reminder_rule: Optional[str] = None,
    created_by_user_id: Optional[int] = None,
    assigned_to_user_id: Optional[int] = None,
    is_personal: bool = False,
) -> Task:
    task = Task(
        user_id=user_id,
        title=title,
        description=description,
        date=task_date,
        time=task_time,
        project_id=project_id,
        priority=priority,
        source=source,
        original_text=original_text,
        transcript=transcript,
        reminder_time=reminder_time,
        reminder_rule=reminder_rule,
        created_by_user_id=created_by_user_id or user_id,
        assigned_to_user_id=assigned_to_user_id,
        is_personal=is_personal,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def get_tasks_today(session: AsyncSession, user_id: int) -> List[Task]:
    today = date.today().isoformat()
    result = await session.execute(
        select(Task).where(
            and_(
                Task.user_id == user_id,
                Task.date == today,
                Task.status.not_in([TaskStatus.deleted, TaskStatus.done])
            )
        ).order_by(Task.time)
    )
    return result.scalars().all()


async def get_tasks_overdue(session: AsyncSession, user_id: int) -> List[Task]:
    today = date.today().isoformat()
    result = await session.execute(
        select(Task).where(
            and_(
                Task.user_id == user_id,
                Task.date < today,
                Task.date.isnot(None),
                Task.status.not_in([TaskStatus.deleted, TaskStatus.done])
            )
        ).order_by(Task.date)
    )
    return result.scalars().all()


async def get_tasks_no_time(session: AsyncSession, user_id: int) -> List[Task]:
    today = date.today().isoformat()
    result = await session.execute(
        select(Task).where(
            and_(
                Task.user_id == user_id,
                Task.date == today,
                Task.time.is_(None),
                Task.status.not_in([TaskStatus.deleted, TaskStatus.done])
            )
        )
    )
    return result.scalars().all()


async def get_tasks_tomorrow(session: AsyncSession, user_id: int) -> List[Task]:
    from datetime import timedelta
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    result = await session.execute(
        select(Task).where(
            and_(
                Task.user_id == user_id,
                Task.date == tomorrow,
                Task.status.not_in([TaskStatus.deleted, TaskStatus.done])
            )
        ).order_by(Task.time)
    )
    return result.scalars().all()


async def get_all_active_tasks(session: AsyncSession, user_id: int) -> List[Task]:
    result = await session.execute(
        select(Task).where(
            and_(
                Task.user_id == user_id,
                Task.status.not_in([TaskStatus.deleted, TaskStatus.done])
            )
        ).order_by(Task.date, Task.time)
    )
    return result.scalars().all()


async def get_done_tasks(session: AsyncSession, user_id: int) -> List[Task]:
    result = await session.execute(
        select(Task).where(
            and_(Task.user_id == user_id, Task.status == TaskStatus.done)
        ).order_by(Task.updated_at.desc()).limit(50)
    )
    return result.scalars().all()


async def search_tasks_by_keywords(
    session: AsyncSession, user_id: int, keywords: str
) -> List[Task]:
    result = await session.execute(
        select(Task).where(
            and_(
                Task.user_id == user_id,
                Task.status.not_in([TaskStatus.deleted]),
                or_(
                    Task.title.ilike(f"%{keywords}%"),
                    Task.description.ilike(f"%{keywords}%"),
                )
            )
        ).limit(10)
    )
    return result.scalars().all()


async def soft_delete_task(session: AsyncSession, task_id: int) -> Optional[Task]:
    result = await session.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task:
        task.status = TaskStatus.deleted
        task.updated_at = datetime.utcnow()
        await session.commit()
    return task


async def complete_task(session: AsyncSession, task_id: int) -> Optional[Task]:
    result = await session.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task:
        task.status = TaskStatus.done
        task.updated_at = datetime.utcnow()
        await session.commit()
    return task


async def update_task(session: AsyncSession, task_id: int, **kwargs) -> Optional[Task]:
    result = await session.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if task:
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
        task.updated_at = datetime.utcnow()
        await session.commit()
    return task
