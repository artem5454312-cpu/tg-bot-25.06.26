import logging
from datetime import date, datetime, timedelta
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.engine import AsyncSessionLocal
from app.db import repos, task_repo
from app.db.models import UserStatus, ReminderStatus, TaskStatus
from app.services import claude_service
from app.services.weather_service import get_weather
from config.settings import settings
from sqlalchemy import select

logger = logging.getLogger(__name__)


def setup_scheduler(scheduler: AsyncIOScheduler, bot: Bot):
    try:
        hour, minute = map(int, settings.MORNING_REPORT_TIME.split(":"))
    except Exception:
        hour, minute = 7, 0

    # Утреннее сообщение
    scheduler.add_job(
        send_morning_reports,
        trigger="cron",
        hour=hour,
        minute=minute,
        args=[bot],
        id="morning_report",
        replace_existing=True,
    )

    # Напоминания каждую минуту
    scheduler.add_job(
        check_reminders,
        trigger="interval",
        minutes=1,
        args=[bot],
        id="reminders",
        replace_existing=True,
    )

    # Проактивные сообщения в 15:00
    scheduler.add_job(
        send_proactive_messages,
        trigger="cron",
        hour=15,
        minute=0,
        args=[bot],
        id="proactive",
        replace_existing=True,
    )

    logger.info(f"Scheduler set up: morning at {hour:02d}:{minute:02d}")


async def send_morning_reports(bot: Bot):
    logger.info("Sending morning reports")
    today = date.today().isoformat()
    today_pretty = date.today().strftime("%d.%m.%Y")

    async with AsyncSessionLocal() as session:
        from app.db.models import User
        result = await session.execute(
            select(User).where(User.status == UserStatus.active)
        )
        users = result.scalars().all()

    # Погода один раз для всех
    weather = await get_weather("Moscow")

    # Совет дня через Claude
    tip = await _get_daily_tip()

    for user in users:
        try:
            async with AsyncSessionLocal() as session:
                tasks_today = await task_repo.get_tasks_today(session, user.id)
                tasks_overdue = await task_repo.get_tasks_overdue(session, user.id)

            name = user.first_name or user.username or "друг"
            task_count = len(tasks_today)

            lines = [f"Доброе утро, {name}! 👋"]
            lines.append(f"Сегодня {today_pretty}\n")

            # Задачи
            if task_count > 0:
                lines.append(f"📋 Задач на сегодня: {task_count}")
            else:
                lines.append("📋 Задач на сегодня нет")

            if tasks_overdue:
                lines.append(f"⚠️ Просроченных: {len(tasks_overdue)}")

            lines.append("")

            # Погода
            if "error" not in weather:
                lines.append(
                    f"🌤 Погода в Москве: {weather['icon']}\n"
                    f"🌡 {weather['temp']}°C, ощущается как {weather['feels_like']}°C"
                )
            else:
                lines.append("🌤 Погода: данные недоступны")

            lines.append("")

            # Совет дня
            if tip:
                lines.append(f"💡 Совет дня:\n{tip}")

            lines.append("\nЯ на связи 😊")

            await bot.send_message(user.telegram_id, "\n".join(lines))
        except Exception as e:
            logger.error(f"Morning report error for {user.telegram_id}: {e}")


async def _get_daily_tip() -> str:
    """Get a short useful tip via Claude."""
    try:
        from datetime import date
        prompt = f"""Дай один короткий полезный совет на день. Сегодня {date.today().strftime('%d.%m.%Y')}.
Совет должен быть практичным и применимым прямо сейчас — про продуктивность, здоровье, общение или бизнес.
Максимум 2 строки. Только текст, без markdown."""
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = await client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.error(f"Daily tip error: {e}")
        return ""


async def check_reminders(bot: Bot):
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
                        f"🔔 Напоминание\n\nСейчас нужно:\n<b>{task.title}</b>"
                    )
                reminder.status = ReminderStatus.sent
            except Exception as e:
                logger.error(f"Reminder send error: {e}")

        await session.commit()


async def send_proactive_messages(bot: Bot):
    logger.info("Checking stale tasks")
    stale_threshold = datetime.utcnow() - timedelta(days=3)

    async with AsyncSessionLocal() as session:
        from app.db.models import User
        result = await session.execute(
            select(User).where(User.status == UserStatus.active)
        )
        users = result.scalars().all()

    for user in users:
        try:
            async with AsyncSessionLocal() as session:
                from sqlalchemy import and_
                from app.db.models import Task
                result = await session.execute(
                    select(Task).where(
                        and_(
                            Task.user_id == user.id,
                            Task.status == TaskStatus.new,
                            Task.created_at <= stale_threshold,
                            Task.date.is_(None),
                        )
                    ).limit(5)
                )
                stale_tasks = result.scalars().all()

            if stale_tasks:
                tasks_data = [
                    {"title": t.title, "created": t.created_at.strftime("%d.%m")}
                    for t in stale_tasks
                ]
                msg = await claude_service.generate_proactive_message(
                    tasks_data, user.first_name or "друг"
                )
                await bot.send_message(user.telegram_id, f"💡 {msg}")
        except Exception as e:
            logger.error(f"Proactive error for {user.telegram_id}: {e}")
