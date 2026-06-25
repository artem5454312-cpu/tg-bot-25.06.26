import json
import logging
from openai import AsyncOpenAI
from config.settings import settings

logger = logging.getLogger(__name__)

client = AsyncOpenAI(
    api_key=settings.ANTHROPIC_API_KEY,
    base_url="https://openrouter.ai/api/v1",
)

INTENT_SYSTEM_PROMPT = """Ты — ядро Telegram-бота личного ассистента. Твоя задача — определить намерение пользователя и вернуть JSON.

Возможные intent:
create_task, delete_task, update_task, complete_task, move_task,
create_reminder, create_project, project_note, save_memory, delete_memory,
ask_memory, ask_advice, create_pdf, generate_image,
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


def _extract(response) -> str:
    return response.choices[0].message.content.strip()


async def detect_intent(user_message: str, today: str, memories: str = "") -> dict:
    context = f"Сегодня: {today}\n"
    if memories:
        context += f"Память пользователя:\n{memories}\n"
    context += f"Сообщение: {user_message}"

    try:
        response = await client.chat.completions.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=1000,
            messages=[
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ],
        )
        raw = _extract(response)
        # Strip possible ```json fences
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

Формат ответа:
Доброе утро, [имя].
Сегодня N задач.
...список задач...
Просроченные задачи:...
Главный фокус:...
Комментарий:...

Пиши кратко, по-русски, без markdown."""

    response = await client.chat.completions.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract(response)


async def generate_pdf_content(project_title: str, tasks: list,
                                notes: list, memories: list) -> str:
    prompt = f"""Создай структурированный отчёт по проекту "{project_title}".

Задачи:
{json.dumps(tasks, ensure_ascii=False, indent=2)}

Заметки:
{json.dumps(notes, ensure_ascii=False, indent=2)}

Важная информация:
{json.dumps(memories, ensure_ascii=False, indent=2)}

Напиши профессиональный отчёт в виде обычного текста, разделы через пустую строку."""

    response = await client.chat.completions.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract(response)


async def generate_image_prompt(user_request: str, project_context: str = "") -> str:
    prompt = f"""Улучши этот запрос на генерацию изображения для GPT Image.
Контекст проекта: {project_context}
Запрос пользователя: {user_request}

Верни только улучшенный промпт на английском, одной строкой, без пояснений."""

    response = await client.chat.completions.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract(response)


async def analyze_training_progress(trainings: list, user_name: str) -> str:
    if not trainings:
        return "Пока нет сохранённых тренировок."

    prompt = f"""Проанализируй тренировки пользователя {user_name} и дай текстовый анализ прогресса.

Данные тренировок:
{json.dumps(trainings, ensure_ascii=False, indent=2)}

Ответ должен содержать:
- Всего тренировок
- Общая дистанция
- Средняя дистанция
- Лучший результат
- Короткий комментарий по прогрессу

Пиши кратко, по-русски."""

    response = await client.chat.completions.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract(response)


async def generate_advice(question: str, memories: str = "") -> str:
    system = "Ты умный личный ассистент. Давай чёткие, практичные советы на русском языке."
    context = ""
    if memories:
        context = f"Что ты знаешь о пользователе:\n{memories}\n\n"
    context += f"Вопрос: {question}"

    response = await client.chat.completions.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=800,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": context},
        ],
    )
    return _extract(response)
