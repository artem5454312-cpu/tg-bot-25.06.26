import logging
from datetime import date, datetime
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.engine import AsyncSessionLocal
from app.db import repos, task_repo
from app.db.models import UserStatus, ReminderStatus
from app.services import claude_service
from config.settings import settings
from sqlalchemy import select

logger = logging.getLogger(__name__)


def setup_scheduler(scheduler: AsyncIOScheduler, bot: Bot):
    # Parse morning report time
    try:
        hour, minute = map(int, settings.MORNING_REPORT_TIME.split(":"))
    except Exception:
        hour, minute = 7, 30

    scheduler.add_job(
        send_morning_reports,
        trigger="cron",
        hour=hour,
        minute=minute,
        args=[bot],
        id="morning_report",
        replace_existing=True,
    )

    # Check reminders every minute
    scheduler.add_job(
        check_reminders,
        trigger="interval",
        minutes=1,
        args=[bot],
        id="reminders",
        replace_existing=True,
    )

    logger.info(f"Scheduler set up: morning report at {hour:02d}:{minute:02d}")


async def send_morning_reports(bot: Bot):
    """Send morning plan to all active users."""
    logger.info("Sending morning reports")
    today = date.today().isoformat()

    async with AsyncSessionLocal() as session:
        from app.db.models import User
        result = await session.execute(
            select(User).where(User.status == UserStatus.active)
        )
        users = result.scalars().all()

    for user in users:
        try:
            async with AsyncSessionLocal() as session:
                tasks_today = await task_repo.get_tasks_today(session, user.id)
                tasks_overdue = await task_repo.get_tasks_overdue(session, user.id)
                tasks_no_time = await task_repo.get_tasks_no_time(session, user.id)

            def task_to_dict(t):
                return {"title": t.title, "time": t.time, "date": t.date}

            report = await claude_service.generate_morning_report(
                tasks_today=[task_to_dict(t) for t in tasks_today],
                tasks_overdue=[task_to_dict(t) for t in tasks_overdue],
                tasks_no_time=[task_to_dict(t) for t in tasks_no_time],
                user_name=user.first_name or "друг",
                today=today,
            )
            await bot.send_message(user.telegram_id, report)
        except Exception as e:
            logger.error(f"Morning report error for user {user.telegram_id}: {e}")


async def check_reminders(bot: Bot):
    """Send due reminders."""
    from app.db.models import Reminder, Task, User
    now = datetime.utcnow()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Reminder).where(
                Reminder.status == ReminderStatus.pending,
                Reminder.remind_at <= now,
            )
        )
        reminders = result.scalars().all()

        for reminder in reminders:
            try:
                task_result = await session.execute(
                    select(Task).where(Task.id == reminder.task_id)
                )
                task = task_result.scalar_one_or_none()

                user_result = await session.execute(
                    select(User).where(User.id == reminder.user_id)
                )
                user = user_result.scalar_one_or_none()

                if user and task:
                    await bot.send_message(
                        user.telegram_id,
                        f"🔔 <b>Напоминание</b>\n\nСейчас нужно:\n<b>{task.title}</b>"
                    )

                reminder.status = ReminderStatus.sent
            except Exception as e:
                logger.error(f"Reminder send error: {e}")

        await session.commit()
