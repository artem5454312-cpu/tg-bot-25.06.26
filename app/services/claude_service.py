import json
import logging
import re
from datetime import date, datetime
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

AUTO_MEMORY_PROMPT = """Ты анализируешь сообщение пользователя и решаешь — есть ли в нём важный факт который стоит запомнить.

Запоминать стоит:
- Имена людей и их роли ("Игорь — клиент по бассейнам")
- Предпочтения пользователя ("работаю до 22:00", "не люблю звонки утром")
- Важные факты о проектах
- Договорённости и решения

НЕ запоминать:
- Обычные вопросы и ответы
- Задачи (они и так сохраняются)
- Приветствия и мелочи

Верни JSON:
{
  "should_remember": true/false,
  "memory": "краткий факт для запоминания или null",
  "importance": 1-10
}

Только JSON, без пояснений."""


def clean_markdown(text: str) -> str:
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,2}(.+?)_{1,2}', r'\1', text)
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        if re.match(r'^\s*\|[-:]+\|', line):
            continue
        if line.startswith('|') and line.endswith('|'):
            cells = [c.strip() for c in line.strip('|').split('|')]
            clean_lines.append('  '.join(cells))
        else:
            clean_lines.append(line)
    text = '\n'.join(clean_lines)
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'`(.+?)`', r'\1', text)
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


async def auto_extract_memory(message: str) -> dict:
    """Automatically extract important facts from user message."""
    try:
        response = await client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=200,
            system=AUTO_MEMORY_PROMPT,
            messages=[{"role": "user", "content": message}],
        )
        raw = response.content[0].text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        logger.error(f"Auto memory error: {e}")
        return {"should_remember": False}


async def generate_morning_report(tasks_today: list, tasks_overdue: list,
                                   tasks_no_time: list, user_name: str,
                                   today: str) -> str:
    # Формируем анализ просроченных
    overdue_analysis = ""
    if tasks_overdue:
        overdue_analysis = f"\nПросроченных задач: {len(tasks_overdue)}. Это важно упомянуть и подтолкнуть закрыть."

    prompt = f"""Сгенерируй утренний план дня для {user_name} на {today}.
{overdue_analysis}

Задачи на сегодня:
{json.dumps(tasks_today, ensure_ascii=False, indent=2)}

Просроченные задачи:
{json.dumps(tasks_overdue, ensure_ascii=False, indent=2)}

Задачи без времени:
{json.dumps(tasks_no_time, ensure_ascii=False, indent=2)}

Формат — простой текст БЕЗ markdown:
Доброе утро, [имя].
Сегодня N задач.
...список...
Просроченные:...
Главный фокус:...
Комментарий (короткий, по делу, как мудрый советник):...

Пиши кратко, по-русски, только обычный текст."""

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

Напиши профессиональный отчёт. Только обычный текст, разделы обозначай строкой с двоеточием. Без markdown."""

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

Требования:
- Детальное описание композиции, освещения, стиля
- Укажи стиль: photorealistic / cinematic / commercial photography
- Добавь: 8k, sharp focus, professional lighting
- Для вертикальных форматов: vertical composition 9:16
- Верни ТОЛЬКО промпт на английском, одной строкой."""

    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


async def generate_photo_edit_prompt(user_request: str) -> str:
    prompt = f"""Пользователь хочет отредактировать фото. Его запрос: "{user_request}"
Сформулируй чёткую инструкцию для редактирования на английском языке.
Верни ТОЛЬКО инструкцию одной строкой."""

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
- Короткий комментарий по прогрессу

Пиши кратко, по-русски."""

    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return clean_markdown(response.content[0].text.strip())


async def search_web(query: str) -> str:
    """Search web via Tavily."""
    try:
        import os
        from tavily import TavilyClient
        api_key = os.environ.get("TAVILY_API_KEY", "")
        if not api_key:
            return ""
        client_tavily = TavilyClient(api_key=api_key)
        results = client_tavily.search(query, max_results=3, search_depth="basic")
        snippets = []
        for r in results.get("results", []):
            title = r.get("title", "")
            content = r.get("content", "")[:400]
            snippets.append(f"{title}: {content}")
        return "\n".join(snippets)
    except Exception as e:
        logger.error(f"Web search error: {e}")
        return ""


async def needs_web_search(question: str) -> bool:
    """Check if question needs fresh web data."""
    try:
        response = await client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=10,
            system="Ответь только 'да' или 'нет'.",
            messages=[{"role": "user", "content":
                f"Этот вопрос требует актуальных данных из интернета (новости, текущие события, результаты матчей, курсы валют, погода, цены)? Вопрос: {question}"}],
        )
        return "да" in response.content[0].text.lower()
    except Exception:
        return False


async def generate_proactive_message(stale_tasks: list, user_name: str) -> str:
    """Generate proactive message about stale tasks."""
    prompt = f"""Ты личный ассистент {user_name}. У пользователя есть задачи которые висят давно и не закрыты.

Задачи:
{json.dumps(stale_tasks, ensure_ascii=False, indent=2)}

Напиши короткое проактивное сообщение — как мудрый советник, без занудства.
Спроси что с этими задачами, предложи закрыть или перенести.
Максимум 3-4 строки. Только обычный текст, без markdown."""

    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    return clean_markdown(response.content[0].text.strip())


async def generate_advice(question: str, memories: str = "",
                          dialog_history: list = None) -> str:
    current_date = date.today().strftime("%d.%m.%Y")
    system = f"""Ты мудрый личный ассистент. Сегодня {current_date}.

Стиль общения:
- Отвечай кратко и по делу — если вопрос простой, 2-4 строки максимум
- Если нужен развёрнутый ответ — пиши развёрнуто, но без воды
- Говори как умный друг, а не как справочник
- Если знаешь человека по памяти — используй это в ответе
- Если вопрос о текущих событиях и есть данные из поиска — опирайся на них
- Если информация может быть устаревшей — честно скажи об этом
- Помни контекст предыдущих сообщений в диалоге

Формат: только обычный текст, без markdown, без звёздочек, без решёток, без таблиц.
Используй тире для списков."""

    system_context = ""
    if memories:
        system_context = f"Что ты знаешь о пользователе:\n{memories}"

    # Web search if needed
    web_context = ""
    if await needs_web_search(question):
        search_results = await search_web(question)
        if search_results:
            web_context = f"\n\nАктуальные данные из интернета:\n{search_results}"

    # Build messages with dialog history
    messages = []
    if dialog_history:
        for msg in dialog_history[-6:]:  # last 6 messages (3 exchanges)
            messages.append(msg)

    # Add system context to last user message
    final_question = question
    if system_context or web_context:
        final_question = f"{system_context}{web_context}\n\nВопрос: {question}"

    messages.append({"role": "user", "content": final_question})

    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=800,
        system=system,
        messages=messages,
    )
    return clean_markdown(response.content[0].text.strip())


async def analyze_photo(photo_bytes: bytes, instruction: str) -> str:
    """Analyze photo using Claude Vision."""
    import base64
    image_data = base64.standard_b64encode(photo_bytes).decode("utf-8")

    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": image_data,
                    },
                },
                {
                    "type": "text",
                    "text": f"{instruction}\n\nОтвечай на русском языке, кратко и по делу. Без markdown."
                }
            ],
        }],
    )
    return clean_markdown(response.content[0].text.strip())
