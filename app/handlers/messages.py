import logging
from datetime import date, datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import CommandStart, Command

from app.db.engine import AsyncSessionLocal
from app.db import repos, task_repo
from app.db.models import MemoryType, NoteType, TaskSource, TaskPriority, UserRole
from app.keyboards import main_menu
from app.services import claude_service, voice_service, image_service, pdf_service
from config.settings import settings

router = Router()
logger = logging.getLogger(__name__)

PRIORITY_MAP = {"low": TaskPriority.low, "medium": TaskPriority.medium, "high": TaskPriority.high}


# ─── /start ──────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message):
    async with AsyncSessionLocal() as session:
        tg = message.from_user
        user = await repos.get_or_create_user(
            session, tg.id, tg.username, tg.first_name, tg.last_name
        )

        # Auto-assign owner role on first launch
        from config.settings import settings as s
        if tg.id == s.OWNER_TELEGRAM_ID and user.role != UserRole.owner:
            await repos.set_user_role(session, user.id, UserRole.owner)

        # Check invite from deep link  e.g. /start invite_XXXXXXXX
        args = message.text.split()
        if len(args) > 1 and args[1].startswith("invite_"):
            code = args[1][len("invite_"):]
            invite = await repos.get_invite_by_code(session, code)
            if invite and await repos.use_invite(session, invite):
                await repos.set_user_role(session, user.id, invite.role)
                await message.answer(
                    f"✅ Доступ активирован!\nРоль: <b>{invite.role.value}</b>",
                    reply_markup=main_menu()
                )
                return
            else:
                await message.answer("❌ Ссылка недействительна или истекла.")
                return

    name = message.from_user.first_name or "друг"
    await message.answer(
        f"Привет, {name}! 👋\n\nЯ твой личный ассистент. "
        f"Пиши мне в свободной форме или голосом — я пойму.",
        reply_markup=main_menu()
    )


# ─── Voice messages ──────────────────────────────────────────────────────────

@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot):
    await message.answer("🎙 Распознаю голос...")
    try:
        text = await voice_service.transcribe_voice(bot, message.voice)
        await message.answer(f"📝 Распознано: <i>{text}</i>")
        await process_free_text(message, text, source=TaskSource.voice, transcript=text)
    except Exception as e:
        logger.error(f"Voice error: {e}")
        await message.answer("❌ Не удалось распознать голосовое. Попробуй ещё раз.")


# ─── Free text ───────────────────────────────────────────────────────────────

@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message):
    text = message.text.strip()

    # Menu buttons handled by other routers
    if text in ["✅ Задачи", "📁 Проекты", "⚙️ Настройки"]:
        return

    await process_free_text(message, text)


async def process_free_text(message: Message, text: str,
                              source: TaskSource = TaskSource.text,
                              transcript: str = None):
    tg = message.from_user
    today = date.today().isoformat()

    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id, tg.username,
                                               tg.first_name, tg.last_name)
        memories_text = await repos.get_memories_summary(session, user.id)
        intent_data = await claude_service.detect_intent(text, today, memories_text)

    intent = intent_data.get("intent", "unknown")

    # ── Clarification needed ──
    if intent_data.get("clarification_needed"):
        await message.answer(intent_data.get("clarification_question", "Уточни, пожалуйста."))
        return

    # ── Route by intent ──
    if intent == "create_task":
        await _handle_create_task(message, intent_data, text, source, transcript)
    elif intent == "delete_task":
        await _handle_delete_task(message, intent_data)
    elif intent == "complete_task":
        await _handle_complete_task(message, intent_data)
    elif intent == "create_project":
        await _handle_create_project(message, intent_data)
    elif intent in ("save_memory", "project_note"):
        await _handle_save_memory(message, intent_data, text)
    elif intent == "ask_memory":
        await _handle_ask_memory(message, intent_data)
    elif intent == "ask_advice":
        await _handle_advice(message, text)
    elif intent == "create_pdf":
        await _handle_create_pdf(message, intent_data)
    elif intent == "generate_image":
        await _handle_generate_image(message, text)
    elif intent == "create_training_record":
        await _handle_training_record(message, intent_data, text, source, transcript)
    elif intent == "ask_training_progress":
        await _handle_training_progress(message)
    elif intent == "generate_training_progress_image":
        await _handle_training_progress_image(message)
    elif intent == "create_note":
        await _handle_create_note(message, intent_data, text, source, transcript)
    elif intent == "open_tasks":
        from app.handlers.tasks import show_tasks_menu
        await show_tasks_menu(message)
    elif intent == "open_projects":
        from app.handlers.projects import show_projects_list
        await show_projects_list(message)
    else:
        # Fallback: treat as advice/question
        await _handle_advice(message, text)


# ─── Intent handlers ─────────────────────────────────────────────────────────

async def _handle_create_task(message: Message, data: dict, original: str,
                               source: TaskSource, transcript: str):
    tg = message.from_user
    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id)

        # Resolve project
        project_id = None
        project_name = data.get("project")
        if project_name:
            project = await repos.get_project_by_title(session, user.id, project_name)
            if project:
                project_id = project.id

        # Parse date
        task_date = _resolve_date(data.get("date"))

        task = await task_repo.create_task(
            session,
            user_id=user.id,
            title=data.get("title", original[:100]),
            description=data.get("description"),
            task_date=task_date,
            task_time=data.get("time"),
            project_id=project_id,
            priority=PRIORITY_MAP.get(data.get("priority", "medium"), TaskPriority.medium),
            source=source,
            original_text=original,
            transcript=transcript,
            reminder_time=data.get("reminder_time"),
        )

        await repos.log_action(session, user.id, "create_task",
                                details={"task_id": task.id, "title": task.title})

    parts = [f"✅ Готово.\n\n<b>Задача:</b> {task.title}"]
    if task.date:
        parts.append(f"<b>Когда:</b> {_format_date(task.date)}" +
                     (f", {task.time}" if task.time else ""))
    if project_name:
        parts.append(f"<b>Проект:</b> {project_name}")
    if task.reminder_time:
        parts.append("Напомню. 🔔")

    await message.answer("\n".join(parts))


async def _handle_delete_task(message: Message, data: dict):
    tg = message.from_user
    keywords = data.get("title", "")
    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id)
        tasks = await task_repo.search_tasks_by_keywords(session, user.id, keywords)

        if not tasks:
            await message.answer("🔍 Задача не найдена.")
            return

        if len(tasks) == 1:
            await task_repo.soft_delete_task(session, tasks[0].id)
            await repos.log_action(session, user.id, "delete_task",
                                    details={"task_id": tasks[0].id})
            await message.answer(f"🗑 Удалил задачу:\n\n<b>{tasks[0].title}</b>")
        else:
            from app.keyboards import confirm_delete_tasks
            lines = ["Нашёл несколько похожих задач:\n"]
            for i, t in enumerate(tasks[:5], 1):
                dt = f" — {_format_date(t.date)}" if t.date else ""
                tm = f" {t.time}" if t.time else ""
                lines.append(f"{i}. {t.title}{dt}{tm}")
            lines.append("\nКакую удалить?")
            await message.answer("\n".join(lines),
                                  reply_markup=confirm_delete_tasks(tasks[:5]))


async def _handle_complete_task(message: Message, data: dict):
    tg = message.from_user
    keywords = data.get("title", "")
    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id)
        tasks = await task_repo.search_tasks_by_keywords(session, user.id, keywords)
        if tasks:
            await task_repo.complete_task(session, tasks[0].id)
            await repos.log_action(session, user.id, "complete_task",
                                    details={"task_id": tasks[0].id})
            await message.answer(f"✅ Отметил выполненной:\n\n<b>{tasks[0].title}</b>")
        else:
            await message.answer("🔍 Задача не найдена.")


async def _handle_create_project(message: Message, data: dict):
    tg = message.from_user
    title = data.get("title") or data.get("data", {}).get("project_name", "Новый проект")
    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id)
        project = await repos.create_project(session, user.id, title)
        await repos.log_action(session, user.id, "create_project",
                                details={"project_id": project.id})
    await message.answer(f"📁 Создал проект: <b>{title}</b>")


async def _handle_save_memory(message: Message, data: dict, original: str):
    tg = message.from_user
    content = data.get("description") or data.get("title") or original
    project_name = data.get("project")

    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id)
        project_id = None
        mem_type = MemoryType.personal

        if project_name:
            project = await repos.get_project_by_title(session, user.id, project_name)
            if project:
                project_id = project.id
                mem_type = MemoryType.project
        elif data.get("intent") == "project_note" and not project_name:
            mem_type = MemoryType.global_memory

        await repos.save_memory(session, user.id, content,
                                 memory_type=mem_type, project_id=project_id)

    await message.answer(f"🧠 Запомнил:\n\n<i>{content[:200]}</i>")


async def _handle_ask_memory(message: Message, data: dict):
    tg = message.from_user
    project_name = data.get("project")
    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id)
        project_id = None
        if project_name:
            project = await repos.get_project_by_title(session, user.id, project_name)
            if project:
                project_id = project.id
        summary = await repos.get_memories_summary(session, user.id, project_id)

    if summary:
        label = f"по проекту {project_name}" if project_name else "о тебе"
        await message.answer(f"🧠 Что я помню {label}:\n\n{summary}")
    else:
        await message.answer("🧠 Пока ничего не записано.")


async def _handle_advice(message: Message, text: str):
    tg = message.from_user
    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id)
        memories = await repos.get_memories_summary(session, user.id)
    answer = await claude_service.generate_advice(text, memories)
    await message.answer(answer)


async def _handle_create_pdf(message: Message, data: dict):
    project_name = data.get("project") or data.get("title", "Отчёт")
    tg = message.from_user
    await message.answer(f"📄 Готовлю PDF по проекту <b>{project_name}</b>...")

    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id)
        project = await repos.get_project_by_title(session, user.id, project_name)
        project_id = project.id if project else None

        tasks = await task_repo.get_all_active_tasks(session, user.id)
        if project_id:
            tasks = [t for t in tasks if t.project_id == project_id]
        tasks_data = [{"title": t.title, "date": t.date, "status": t.status.value} for t in tasks]

        notes_data = []
        memories_data = []
        if project_id:
            mems = await repos.get_user_memories(session, user.id,
                                                  project_id=project_id)
            memories_data = [m.content for m in mems]

    content = await claude_service.generate_pdf_content(
        project_name, tasks_data, notes_data, memories_data
    )
    pdf_bytes = pdf_service.generate_pdf(project_name, content)
    file = BufferedInputFile(pdf_bytes, filename=f"{project_name}.pdf")
    await message.answer_document(file, caption=f"📄 PDF по проекту «{project_name}»")


async def _handle_generate_image(message: Message, text: str):
    tg = message.from_user
    await message.answer("🎨 Генерирую изображение...")
    try:
        improved_prompt = await claude_service.generate_image_prompt(text)
        image_bytes = await image_service.generate_image(improved_prompt)
        file = BufferedInputFile(image_bytes, filename="image.png")
        await message.answer_photo(file, caption=f"🎨 Готово!")
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        await message.answer("❌ Не удалось сгенерировать изображение.")


async def _handle_training_record(message: Message, data: dict, original: str,
                                   source: TaskSource, transcript: str):
    tg = message.from_user
    raw = data.get("data", {})
    distance = raw.get("distance_km")
    duration = raw.get("duration_minutes")

    # Try to parse date
    recorded_at = datetime.utcnow()
    if data.get("date"):
        try:
            recorded_at = datetime.strptime(_resolve_date(data["date"]), "%Y-%m-%d")
        except Exception:
            pass

    content = original
    title = f"Тренировка"
    if distance:
        title += f" {distance} км"

    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id)
        await repos.create_note(
            session, user.id,
            note_type=NoteType.training,
            content=content,
            title=title,
            data_json={"distance_km": distance, "duration_minutes": duration},
            source=source,
            original_text=original,
            transcript=transcript,
            recorded_at=recorded_at,
        )

    parts = ["✅ Записал тренировку.\n"]
    if recorded_at.date() == date.today():
        parts.append("📅 Дата: сегодня")
    else:
        parts.append(f"📅 Дата: {recorded_at.strftime('%d.%m.%Y')}")
    if distance:
        parts.append(f"🏃 Дистанция: {distance} км")
    if duration:
        parts.append(f"⏱ Время: {duration} мин")
    await message.answer("\n".join(parts))


async def _handle_training_progress(message: Message):
    tg = message.from_user
    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id)
        trainings = await repos.get_trainings(session, user.id)
        trainings_data = [
            {
                "date": t.recorded_at.strftime("%d.%m.%Y") if t.recorded_at else None,
                **(t.data_json or {}),
            }
            for t in trainings
        ]
    result = await claude_service.analyze_training_progress(
        trainings_data, tg.first_name or "пользователь"
    )
    await message.answer(f"📊 {result}")


async def _handle_training_progress_image(message: Message):
    tg = message.from_user
    await message.answer("📊 Готовлю визуальный отчёт по тренировкам...")
    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id)
        trainings = await repos.get_trainings(session, user.id)
        trainings_data = [
            {"date": t.recorded_at.strftime("%d.%m.%Y") if t.recorded_at else None,
             **(t.data_json or {})}
            for t in trainings
        ]
    summary = await claude_service.analyze_training_progress(
        trainings_data, tg.first_name or "пользователь"
    )
    prompt = f"Motivational running progress infographic. Data: {summary}. Clean, modern design."
    try:
        image_bytes = await image_service.generate_image(prompt)
        file = BufferedInputFile(image_bytes, filename="training_progress.png")
        await message.answer_photo(file, caption="🏃 Прогресс тренировок")
    except Exception as e:
        logger.error(f"Training image error: {e}")
        await message.answer(f"📊 Текстовый анализ:\n\n{summary}")


async def _handle_create_note(message: Message, data: dict, original: str,
                               source: TaskSource, transcript: str):
    tg = message.from_user
    content = data.get("description") or data.get("title") or original
    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id)
        await repos.create_note(
            session, user.id,
            note_type=NoteType.note,
            content=content,
            source=source,
            original_text=original,
            transcript=transcript,
        )
    await message.answer(f"📝 Записал заметку:\n\n<i>{content[:200]}</i>")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _resolve_date(date_str: str) -> str:
    """Convert relative dates to YYYY-MM-DD."""
    if not date_str:
        return None
    today = date.today()
    if date_str in ("today", "сегодня"):
        return today.isoformat()
    if date_str in ("tomorrow", "завтра"):
        return (today + timedelta(days=1)).isoformat()
    if date_str in ("yesterday", "вчера"):
        return (today - timedelta(days=1)).isoformat()
    # Already in YYYY-MM-DD
    return date_str


def _format_date(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        today = date.today()
        if d.date() == today:
            return "сегодня"
        if d.date() == today + timedelta(days=1):
            return "завтра"
        return d.strftime("%d.%m.%Y")
    except Exception:
        return date_str
