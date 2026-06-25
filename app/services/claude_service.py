import json
import logging
import re
import anthropic
from config.settings import settings

logger = logging.getLogger(__name__)
client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

INTENT_SYSTEM_PROMPT = """Ты — ядро Telegram-бота личного ассистента. Твоя задача — определить намерение пользователя и вернуть JSON.

Возможные intent:
create_task, delete_task, update_task, complete_task, move_task,
create_reminder, create_project, project_note, save_memory, delete_memory,
ask_memory, ask_advice, create_pdf, generate_image, edit_photo,
open_tasks, open_projects, open_settings,
grant_access, revoke_access,
create_note, create_training_record, ask_training_progress, generate_training_progress_image,
unknown

Отвечай ТОЛЬКО JSON, без markdown, без пояснений. Формат:
{
  "intent": "create_task",
  "title": "...",
  "description": "...",
  "date": "YYYY-MM-DD или null",
  "time": "HH:MM или null",
  "project": "название проекта или null",
  "priority": "low|medium|high",
  "reminder_time": "HH:MM или null",
  "clarification_needed": false,
  "clarification_question": null,
  "data": {}
}

Сегодняшняя дата будет передана в сообщении пользователя.
Если не уверен — поставь clarification_needed: true и задай короткий вопрос.
"""


def clean_markdown(text: str) -> str:
    """Remove markdown formatting for clean Telegram output."""
    # Remove headers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Remove bold/italic
    text = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,2}(.+?)_{1,2}', r'\1', text)
    # Remove markdown tables - convert to plain text
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        if re.match(r'^\s*\|[-:]+\|', line):
            continue  # skip separator rows
        if line.startswith('|') and line.endswith('|'):
            # Convert table row to plain text
            cells = [c.strip() for c in line.strip('|').split('|')]
            clean_lines.append('  '.join(cells))
        else:
            clean_lines.append(line)
    text = '\n'.join(clean_lines)
    # Remove code blocks
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'`(.+?)`', r'\1', text)
    # Clean multiple empty lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


async def detect_intent(user_message: str, today: str, memories: str = "") -> dict:
    context = f"Сегодня: {today}\n"
    if memories:
        context += f"Память пользователя:\n{memories}\n"
    context += f"Сообщение: {user_message}"

    try:
        response = await client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=1000,
            system=INTENT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": context}],
        )
        raw = response.content[0].text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        logger.error(f"Intent detection error: {e}")
        return {"intent": "unknown", "clarification_needed": False}


async def generate_morning_report(tasks_today: list, tasks_overdue: list,
                                   tasks_no_time: list, user_name: str,
                                   today: str) -> str:
    prompt = f"""Сгенерируй утренний план дня для {user_name} на {today}.

Задачи на сегодня:
{json.dumps(tasks_today, ensure_ascii=False, indent=2)}

Просроченные задачи:
{json.dumps(tasks_overdue, ensure_ascii=False, indent=2)}

Задачи без времени:
{json.dumps(tasks_no_time, ensure_ascii=False, indent=2)}

Формат ответа — простой текст БЕЗ markdown, без звёздочек, без решёток:
Доброе утро, [имя].
Сегодня N задач.
...список задач...
Просроченные задачи:...
Главный фокус:...
Комментарий:...

Пиши кратко, по-русски, ТОЛЬКО обычный текст."""

    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    return clean_markdown(response.content[0].text.strip())


async def generate_pdf_content(project_title: str, tasks: list,
                                notes: list, memories: list) -> str:
    prompt = f"""Создай структурированный отчёт по проекту "{project_title}".

Задачи:
{json.dumps(tasks, ensure_ascii=False, indent=2)}

Заметки:
{json.dumps(notes, ensure_ascii=False, indent=2)}

Важная информация:
{json.dumps(memories, ensure_ascii=False, indent=2)}

Напиши профессиональный отчёт. Используй только обычный текст, разделы обозначай строкой с двоеточием в конце. Без markdown, без звёздочек."""

    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


async def generate_image_prompt(user_request: str, project_context: str = "") -> str:
    prompt = f"""Ты профессиональный промпт-инженер для генерации изображений.
Улучши запрос пользователя до профессионального промпта для DALL-E 3.

Контекст проекта: {project_context}
Запрос пользователя: {user_request}

Требования к промпту:
- Детальное описание композиции, освещения, стиля
- Укажи стиль: photorealistic / cinematic / commercial photography
- Добавь детали про качество: 8k, sharp focus, professional lighting
- Для вертикальных форматов (рилс, сторис) укажи: vertical composition 9:16
- Верни ТОЛЬКО промпт на английском, одной строкой, без пояснений."""

    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


async def generate_photo_edit_prompt(user_request: str) -> str:
    """Generate edit instruction for GPT Image photo editing."""
    prompt = f"""Пользователь хочет отредактировать фото. Его запрос: "{user_request}"

Сформулируй чёткую инструкцию для редактирования на английском языке.
Верни ТОЛЬКО инструкцию одной строкой, без пояснений."""

    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


async def analyze_training_progress(trainings: list, user_name: str) -> str:
    if not trainings:
        return "Пока нет сохранённых тренировок."

    prompt = f"""Проанализируй тренировки пользователя {user_name}.

Данные:
{json.dumps(trainings, ensure_ascii=False, indent=2)}

Напиши анализ простым текстом БЕЗ markdown:
- Всего тренировок
- Общая дистанция
- Средняя дистанция
- Лучший результат
- Короткий комментарий

Пиши кратко, по-русски, только обычный текст."""

    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return clean_markdown(response.content[0].text.strip())


async def generate_advice(question: str, memories: str = "") -> str:
    system = """Ты умный личный ассистент. Отвечай чётко и практично на русском языке.
ВАЖНО: пиши только обычный текст — без markdown, без звёздочек (*), без решёток (#), без таблиц с вертикальными чертами (|). 
Используй обычные тире для списков."""

    context = ""
    if memories:
        context = f"Что ты знаешь о пользователе:\n{memories}\n\n"
    context += f"Вопрос: {question}"

    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=800,
        system=system,
        messages=[{"role": "user", "content": context}],
    )
    return clean_markdown(response.content[0].text.strip())
