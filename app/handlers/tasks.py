from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from app.db.engine import AsyncSessionLocal
from app.db import repos, task_repo
from app.keyboards import tasks_menu, task_actions

router = Router()


async def show_tasks_menu(message: Message):
    await message.answer("📋 Задачи:", reply_markup=tasks_menu())


@router.message(F.text == "✅ Задачи")
async def tasks_button(message: Message):
    await show_tasks_menu(message)


@router.callback_query(F.data.startswith("tasks:"))
async def tasks_callback(call: CallbackQuery):
    action = call.data.split(":")[1]
    tg = call.from_user

    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id)

        if action == "today":
            tasks = await task_repo.get_tasks_today(session, user.id)
            label = "📅 Задачи на сегодня"
        elif action == "overdue":
            tasks = await task_repo.get_tasks_overdue(session, user.id)
            label = "⚠️ Просроченные задачи"
        elif action == "no_time":
            tasks = await task_repo.get_tasks_no_time(session, user.id)
            label = "🕐 Задачи без времени"
        elif action == "tomorrow":
            tasks = await task_repo.get_tasks_tomorrow(session, user.id)
            label = "📆 Задачи на завтра"
        elif action == "all":
            tasks = await task_repo.get_all_active_tasks(session, user.id)
            label = "📋 Все активные задачи"
        elif action == "done":
            tasks = await task_repo.get_done_tasks(session, user.id)
            label = "✅ Выполненные задачи"
        elif action == "cancel":
            await call.message.edit_text("Отменено.")
            await call.answer()
            return
        else:
            await call.answer()
            return

    if not tasks:
        await call.message.edit_text(f"{label}\n\nЗадач нет.")
        await call.answer()
        return

    from datetime import datetime, date, timedelta

    def fmt_date(date_str):
        if not date_str:
            return ""
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            today = date.today()
            if d == today:
                return "сегодня"
            if d == today + timedelta(days=1):
                return "завтра"
            if d == today - timedelta(days=1):
                return "вчера"
            return d.strftime("%d.%m.%Y")
        except Exception:
            return date_str

    lines = [f"<b>{label}</b>\n"]
    for t in tasks:
        time_str = f" {t.time}" if t.time else ""
        date_label = fmt_date(t.date)
        date_str = f" [{date_label}{time_str}]" if date_label else (f" [{time_str.strip()}]" if time_str.strip() else "")
        status_icon = "✅" if t.status.value == "done" else "🔲"
        lines.append(f"{status_icon} {t.title}{date_str}")

    await call.message.edit_text("\n".join(lines))
    await call.answer()


@router.callback_query(F.data.startswith("task:"))
async def task_action_callback(call: CallbackQuery):
    parts = call.data.split(":")
    action = parts[1]
    task_id = int(parts[2])
    tg = call.from_user

    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id)

        if action == "done":
            task = await task_repo.complete_task(session, task_id)
            await repos.log_action(session, user.id, "complete_task",
                                    details={"task_id": task_id})
            if task:
                await call.message.edit_text(f"✅ Отметил выполненной:\n\n<b>{task.title}</b>")

        elif action == "delete":
            task = await task_repo.soft_delete_task(session, task_id)
            await repos.log_action(session, user.id, "delete_task",
                                    details={"task_id": task_id})
            if task:
                await call.message.edit_text(f"🗑 Удалил:\n\n<b>{task.title}</b>")
            else:
                await call.message.edit_text("🗑 Задача удалена.")

    await call.answer()
