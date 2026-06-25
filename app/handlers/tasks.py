from datetime import datetime, date, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.db.engine import AsyncSessionLocal
from app.db import repos, task_repo

router = Router()


class EditTaskState(StatesGroup):
    waiting_for_datetime = State()


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


def task_card(t) -> str:
    """Format single task as text card."""
    lines = [f"<b>{t.title}</b>"]
    if t.date or t.time:
        date_label = fmt_date(t.date)
        parts = []
        if date_label:
            parts.append(date_label)
        if t.time:
            parts.append(t.time)
        lines.append(f"🗓 {', '.join(parts)}")
    if t.description:
        lines.append(f"📝 {t.description[:100]}")
    priority_icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
    lines.append(priority_icons.get(t.priority.value if hasattr(t.priority, 'value') else t.priority, "🟡"))
    return "\n".join(lines)


def task_buttons(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Выполнено", callback_data=f"task:done:{task_id}"),
            InlineKeyboardButton(text="✏️ Изменить", callback_data=f"task:edit:{task_id}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"task:delete:{task_id}"),
        ]
    ])


def tasks_filter_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Сегодня", callback_data="tasks:today"),
         InlineKeyboardButton(text="📆 Завтра", callback_data="tasks:tomorrow")],
        [InlineKeyboardButton(text="⚠️ Просроченные", callback_data="tasks:overdue"),
         InlineKeyboardButton(text="🕐 Без времени", callback_data="tasks:no_time")],
        [InlineKeyboardButton(text="📋 Все активные", callback_data="tasks:all"),
         InlineKeyboardButton(text="✅ Выполненные", callback_data="tasks:done")],
    ])


async def show_tasks_menu(message: Message):
    await message.answer("📋 Выбери раздел:", reply_markup=tasks_filter_menu())


async def send_tasks_list(target, tasks: list, label: str):
    """Send tasks one by one with buttons. target = message or call.message"""
    if not tasks:
        await target.answer(f"{label}\n\nЗадач нет.")
        return

    await target.answer(f"{label} — {len(tasks)} шт.")
    for t in tasks:
        await target.answer(task_card(t), reply_markup=task_buttons(t.id))


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
            label = "📅 Сегодня"
        elif action == "overdue":
            tasks = await task_repo.get_tasks_overdue(session, user.id)
            label = "⚠️ Просроченные"
        elif action == "no_time":
            tasks = await task_repo.get_tasks_no_time(session, user.id)
            label = "🕐 Без времени"
        elif action == "tomorrow":
            tasks = await task_repo.get_tasks_tomorrow(session, user.id)
            label = "📆 Завтра"
        elif action == "all":
            tasks = await task_repo.get_all_active_tasks(session, user.id)
            label = "📋 Все активные"
        elif action == "done":
            tasks = await task_repo.get_done_tasks(session, user.id)
            label = "✅ Выполненные"
        elif action == "cancel":
            await call.message.edit_text("Отменено.")
            await call.answer()
            return
        else:
            await call.answer()
            return

    await call.answer()
    await call.message.edit_text(f"{label}...")
    await send_tasks_list(call.message, tasks, label)


@router.callback_query(F.data.startswith("task:"))
async def task_action_callback(call: CallbackQuery, state: FSMContext):
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
                await call.message.edit_text(
                    f"✅ Выполнено:\n\n<b>{task.title}</b>"
                )

        elif action == "delete":
            task = await task_repo.soft_delete_task(session, task_id)
            await repos.log_action(session, user.id, "delete_task",
                                    details={"task_id": task_id})
            if task:
                await call.message.edit_text(f"🗑 Удалено:\n\n<b>{task.title}</b>")

        elif action == "edit":
            # Запоминаем task_id и ждём новую дату/время
            await state.set_state(EditTaskState.waiting_for_datetime)
            await state.update_data(edit_task_id=task_id)
            task_result = await session.execute(
                __import__('sqlalchemy', fromlist=['select']).select(
                    __import__('app.db.models', fromlist=['Task']).Task
                ).where(
                    __import__('app.db.models', fromlist=['Task']).Task.id == task_id
                )
            )
            task = task_result.scalar_one_or_none()
            task_title = task.title if task else "задача"
            await call.message.answer(
                f"✏️ Изменяю: <b>{task_title}</b>\n\n"
                f"Напиши новую дату и время, например:\n"
                f"— завтра в 15:00\n"
                f"— 28 июня в 10:30\n"
                f"— послезавтра"
            )

    await call.answer()


@router.message(EditTaskState.waiting_for_datetime, F.text)
async def edit_task_datetime(message: Message, state: FSMContext):
    data = await state.get_data()
    task_id = data.get("edit_task_id")
    await state.clear()

    if not task_id:
        await message.answer("Ошибка — задача не найдена.")
        return

    # Используем Claude для парсинга даты
    from app.services.claude_service import detect_intent
    today = date.today().isoformat()
    intent_data = await detect_intent(
        f"перенеси задачу на {message.text}", today
    )

    new_date = intent_data.get("date")
    new_time = intent_data.get("time")

    if not new_date and not new_time:
        # Простой парсинг
        text = message.text.lower()
        if "завтра" in text:
            new_date = (date.today() + timedelta(days=1)).isoformat()
        elif "послезавтра" in text:
            new_date = (date.today() + timedelta(days=2)).isoformat()
        elif "сегодня" in text:
            new_date = date.today().isoformat()

        import re
        time_match = re.search(r'(\d{1,2})[:\.](\d{2})', text)
        if time_match:
            new_time = f"{int(time_match.group(1)):02d}:{time_match.group(2)}"

    updates = {}
    if new_date:
        updates["date"] = new_date
    if new_time:
        updates["time"] = new_time

    if not updates:
        await message.answer("Не смог распознать дату или время. Попробуй ещё раз.")
        return

    async with AsyncSessionLocal() as session:
        task = await task_repo.update_task(session, task_id, **updates)
        if task:
            date_str = fmt_date(new_date) if new_date else ""
            time_str = new_time or ""
            when = ", ".join(filter(None, [date_str, time_str]))
            await message.answer(
                f"✅ Перенёс задачу:\n\n<b>{task.title}</b>\n🗓 {when}"
            )
        else:
            await message.answer("Задача не найдена.")
