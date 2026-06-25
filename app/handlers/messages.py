import io
import logging
import re
from datetime import date, datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.db.engine import AsyncSessionLocal
from app.db import repos, task_repo
from app.db.models import MemoryType, NoteType, TaskSource, TaskPriority, UserRole
from app.keyboards import main_menu, confirm_delete_tasks
from app.services import claude_service, voice_service, image_service, pdf_service
from config.settings import settings

router = Router()
logger = logging.getLogger(__name__)

PRIORITY_MAP = {"low": TaskPriority.low, "medium": TaskPriority.medium, "high": TaskPriority.high}

# Паттерны для локального определения без Claude
DELETE_ALL_PATTERNS = [
    "удали все задачи", "удалить все задачи", "сотри все задачи",
    "убери все задачи", "очисти все задачи", "удали все", "удали задачи",
    "удалить задачи", "сотри задачи", "убери задачи",
]
DELETE_DONE_PATTERNS = [
    "удали выполненные", "удалить выполненные", "очисти выполненные",
    "убери выполненные", "удали все выполненные",
]


class PhotoState(StatesGroup):
    waiting_for_instruction = State()


# ─── /start ──────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message):
    async with AsyncSessionLocal() as session:
        tg = message.from_user
        user = await repos.get_or_create_user(
            session, tg.id, tg.username, tg.first_name, tg.last_name
        )
        from config.settings import settings as s
        if tg.id == s.OWNER_TELEGRAM_ID and user.role != UserRole.owner:
            await repos.set_user_role(session, user.id, UserRole.owner)

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


# ─── Photo ────────────────────────────────────────────────────────────────────

@router.message(F.photo)
async def handle_photo(message: Message, bot: Bot, state: FSMContext):
    caption = message.caption or ""

    # Скачиваем фото
    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    photo_bytes_io = io.BytesIO()
    await bot.download_file(file_info.file_path, photo_bytes_io)
    photo_bytes = photo_bytes_io.getvalue()

    await state.update_data(photo_bytes=photo_bytes)

    if caption:
        await state.clear()
        await _process_photo_instruction(message, bot, photo_bytes, caption)
    else:
        await state.set_state(PhotoState.waiting_for_instruction)
        await message.answer(
            "📸 Фото получил!\n\n"
            "Что сделать? Напиши или надиктуй голосом:\n"
            "— Опиши что на фото\n"
            "— Поменяй цвет рубашки на белый\n"
            "— Убери фон\n"
            "— Сделай ярче"
        )


@router.message(PhotoState.waiting_for_instruction, F.text)
async def photo_instruction_text(message: Message, bot: Bot, state: FSMContext):
    data = await state.get_data()
    photo_bytes = data.get("photo_bytes")
    await state.clear()
    if not photo_bytes:
        await message.answer("Фото не найдено, отправь снова.")
        return
    await _process_photo_instruction(message, bot, photo_bytes, message.text)


@router.message(PhotoState.waiting_for_instruction, F.voice)
async def photo_instruction_voice(message: Message, bot: Bot, state: FSMContext):
    data = await state.get_data()
    photo_bytes = data.get("photo_bytes")
    await state.clear()
    if not photo_bytes:
        await message.answer("Фото не найдено, отправь снова.")
        return
    await message.answer("🎙 Распознаю голос...")
    try:
        text = await voice_service.transcribe_voice(bot, message.voice)
        await message.answer(f"📝 Распознано: <i>{text}</i>")
        await _process_photo_instruction(message, bot, photo_bytes, text)
    except Exception as e:
        logger.error(f"Voice error: {e}")
        await message.answer("❌ Не удалось распознать голос.")


async def _process_photo_instruction(message: Message, bot: Bot,
                                      photo_bytes: bytes, instruction: str):
    """Decide: analyze or edit photo based on instruction."""
    instr_lower = instruction.lower()

    # Если просят описать/проанализировать — используем Claude Vision
    analyze_keywords = ["опиши", "что на фото", "что здесь", "анализ", "расскажи",
                        "что это", "кто это", "что видишь", "посмотри"]
    if any(k in instr_lower for k in analyze_keywords):
        await message.answer("🔍 Анализирую фото...")
        try:
            result = await claude_service.analyze_photo(photo_bytes, instruction)
            await message.answer(result)
        except Exception as e:
            logger.error(f"Photo analysis error: {e}")
            await message.answer("❌ Не удалось проанализировать фото.")
    else:
        # Иначе — редактируем через GPT Image
        await message.answer("🎨 Редактирую фото...")
        try:
            edit_instruction = await claude_service.generate_photo_edit_prompt(instruction)
            result_bytes = await image_service.edit_photo(photo_bytes, edit_instruction)
            file = BufferedInputFile(result_bytes, filename="edited.png")
            await message.answer_photo(file, caption="✅ Готово!")
        except Exception as e:
            logger.error(f"Photo edit error: {e}")
            await message.answer("❌ Не удалось отредактировать фото.")


# ─── Voice ────────────────────────────────────────────────────────────────────

@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot):
    await message.answer("🎙 Распознаю голос...")
    try:
        text = await voice_service.transcribe_voice(bot, message.voice)
        await message.answer(f"📝 Распознано: <i>{text}</i>")
        await process_free_text(message, text, source=TaskSource.voice, transcript=text)
    except Exception as e:
        logger.error(f"Voice error: {e}")
        await message.answer("❌ Не удалось распознать голосовое.")


# ─── Text ─────────────────────────────────────────────────────────────────────

@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message, state: FSMContext):
    text = message.text.strip()
    if text in ["✅ Задачи", "📁 Проекты", "⚙️ Настройки"]:
        return
    await process_free_text(message, text)


async def process_free_text(message: Message, text: str,
                              source: TaskSource = TaskSource.text,
                              transcript: str = None):
    tg = message.from_user
    today = date.today().isoformat()
    text_lower = text.lower()

    # ── Локальные команды — без Claude ──
    if any(p in text_lower for p in DELETE_ALL_PATTERNS):
        await _handle_delete_all_tasks(message)
        return

    if any(p in text_lower for p in DELETE_DONE_PATTERNS):
        await _handle_delete_done_tasks(message)
        return

    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id, tg.username,
                                               tg.first_name, tg.last_name)
        memories_text = await repos.get_memories_summary(session, user.id)
        intent_data = await claude_service.detect_intent(text, today, memories_text)

    intent = intent_data.get("intent", "unknown")

    # ── Автозапоминание ──
    if intent not in ("save_memory", "ask_memory", "open_tasks",
                       "open_projects", "open_settings"):
        try:
            mem_result = await claude_service.auto_extract_memory(text)
            if mem_result.get("should_remember") and mem_result.get("memory"):
                async with AsyncSessionLocal() as session:
                    user2 = await repos.get_or_create_user(session, tg.id)
                    await repos.save_memory(
                        session, user2.id,
                        content=mem_result["memory"],
                        importance=mem_result.get("importance", 5),
                    )
        except Exception as e:
            logger.error(f"Auto memory error: {e}")

    if intent_data.get("clarification_needed"):
        await message.answer(intent_data.get("clarification_question", "Уточни, пожалуйста."))
        return

    if intent == "create_task":
        await _handle_create_task(message, intent_data, text, source, transcript)
    elif intent == "delete_task":
        await _handle_delete_task(message, intent_data, text)
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
        await _handle_advice(message, text)


# ─── Delete all / done ────────────────────────────────────────────────────────

async def _handle_delete_all_tasks(message: Message):
    tg = message.from_user
    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id)
        tasks = await task_repo.get_all_active_tasks(session, user.id)
        count = 0
        for task in tasks:
            await task_repo.soft_delete_task(session, task.id)
            count += 1
        if count:
            await repos.log_action(session, user.id, "delete_all_tasks",
                                    details={"count": count})
    await message.answer(
        f"🗑 Удалил все задачи ({count} шт.)" if count else "Активных задач нет."
    )


async def _handle_delete_done_tasks(message: Message):
    tg = message.from_user
    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id)
        tasks = await task_repo.get_done_tasks(session, user.id)
        count = 0
        for task in tasks:
            await task_repo.soft_delete_task(session, task.id)
            count += 1
        if count:
            await repos.log_action(session, user.id, "delete_done_tasks",
                                    details={"count": count})
    await message.answer(
        f"🗑 Удалил выполненные ({count} шт.)" if count else "Выполненных задач нет."
    )


# ─── Intent handlers ──────────────────────────────────────────────────────────

async def _handle_create_task(message: Message, data: dict, original: str,
                               source: TaskSource, transcript: str):
    tg = message.from_user
    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id)
        project_id = None
        project_name = data.get("project")
        if project_name:
            project = await repos.get_project_by_title(session, user.id, project_name)
            if project:
                project_id = project.id
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


async def _handle_delete_task(message: Message, data: dict, original_text: str = ""):
    tg = message.from_user
    keywords = data.get("title", "") or original_text
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
            lines = ["Нашёл несколько похожих задач:\n"]
            for i, t in enumerate(tasks[:5], 1):
                dt = f" — {_format_date(t.date)}" if t.date else ""
                tm = f" {t.time}" if t.time else ""
                lines.append(f"{i}. {t.title}{dt}{tm}")
            lines.append("\nКакую удалить?")
            await message.answer("\n".join(lines), reply_markup=confirm_delete_tasks(tasks[:5]))


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
        tasks_data = [{"title": t.title, "date": t.date, "status": t.status.value}
                      for t in tasks]
        memories_data = []
        if project_id:
            mems = await repos.get_user_memories(session, user.id, project_id=project_id)
            memories_data = [m.content for m in mems]
    content = await claude_service.generate_pdf_content(
        project_name, tasks_data, [], memories_data
    )
    pdf_bytes = pdf_service.generate_pdf(project_name, content)
    file = BufferedInputFile(pdf_bytes, filename=f"{project_name}.pdf")
    await message.answer_document(file, caption=f"📄 PDF по проекту «{project_name}»")


async def _handle_generate_image(message: Message, text: str):
    await message.answer("🎨 Генерирую изображение...")
    try:
        improved_prompt = await claude_service.generate_image_prompt(text)
        image_bytes = await image_service.generate_image(improved_prompt)
        file = BufferedInputFile(image_bytes, filename="image.png")
        await message.answer_photo(file, caption="🎨 Готово!")
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        await message.answer("❌ Не удалось сгенерировать изображение.")


async def _handle_training_record(message: Message, data: dict, original: str,
                                   source: TaskSource, transcript: str):
    tg = message.from_user
    raw = data.get("data", {})
    distance = raw.get("distance_km")
    duration = raw.get("duration_minutes")
    recorded_at = datetime.utcnow()
    if data.get("date"):
        try:
            recorded_at = datetime.strptime(_resolve_date(data["date"]), "%Y-%m-%d")
        except Exception:
            pass
    title = "Тренировка"
    if distance:
        title += f" {distance} км"
    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id)
        await repos.create_note(
            session, user.id,
            note_type=NoteType.training,
            content=original,
            title=title,
            data_json={"distance_km": distance, "duration_minutes": duration},
            source=source,
            original_text=original,
            transcript=transcript,
            recorded_at=recorded_at,
        )
    parts = ["✅ Записал тренировку.\n"]
    parts.append("📅 Дата: сегодня" if recorded_at.date() == date.today()
                 else f"📅 Дата: {recorded_at.strftime('%d.%m.%Y')}")
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
            {"date": t.recorded_at.strftime("%d.%m.%Y") if t.recorded_at else None,
             **(t.data_json or {})} for t in trainings
        ]
    result = await claude_service.analyze_training_progress(
        trainings_data, tg.first_name or "пользователь"
    )
    await message.answer(f"📊 {result}")


async def _handle_training_progress_image(message: Message):
    tg = message.from_user
    await message.answer("📊 Готовлю визуальный отчёт...")
    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id)
        trainings = await repos.get_trainings(session, user.id)
        trainings_data = [
            {"date": t.recorded_at.strftime("%d.%m.%Y") if t.recorded_at else None,
             **(t.data_json or {})} for t in trainings
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


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _resolve_date(date_str: str) -> str:
    if not date_str:
        return None
    today = date.today()
    if date_str in ("today", "сегодня"):
        return today.isoformat()
    if date_str in ("tomorrow", "завтра"):
        return (today + timedelta(days=1)).isoformat()
    if date_str in ("yesterday", "вчера"):
        return (today - timedelta(days=1)).isoformat()
    return date_str


def _format_date(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        today = date.today()
        if d.date() == today:
            return "сегодня"
        if d.date() == today + timedelta(days=1):
            return "завтра"
        if d.date() == today - timedelta(days=1):
            return "вчера"
        return d.strftime("%d.%m.%Y")
    except Exception:
        return date_str
