from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

# ─── Main menu ───────────────────────────────────────────────────────────────

def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="✅ Задачи"),
                KeyboardButton(text="📁 Проекты"),
                KeyboardButton(text="⚙️ Настройки"),
            ]
        ],
        resize_keyboard=True,
        persistent=True,
    )


# ─── Tasks menu ──────────────────────────────────────────────────────────────

def tasks_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 На сегодня", callback_data="tasks:today")],
        [InlineKeyboardButton(text="⚠️ Просроченные", callback_data="tasks:overdue")],
        [InlineKeyboardButton(text="🕐 Без времени", callback_data="tasks:no_time")],
        [InlineKeyboardButton(text="📆 На завтра", callback_data="tasks:tomorrow")],
        [InlineKeyboardButton(text="📋 Все активные", callback_data="tasks:all")],
        [InlineKeyboardButton(text="✅ Выполненные", callback_data="tasks:done")],
    ])


def task_actions(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Выполнено", callback_data=f"task:done:{task_id}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"task:delete:{task_id}"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="tasks:today")],
    ])


def confirm_delete_tasks(task_list: list) -> InlineKeyboardMarkup:
    """For ambiguous delete: show numbered buttons."""
    buttons = []
    for i, task in enumerate(task_list, 1):
        buttons.append([
            InlineKeyboardButton(
                text=f"Удалить {i}: {task.title[:30]}",
                callback_data=f"task:delete:{task.id}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="Отмена", callback_data="tasks:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─── Projects menu ───────────────────────────────────────────────────────────

def projects_list(projects: list) -> InlineKeyboardMarkup:
    buttons = []
    for p in projects:
        buttons.append([
            InlineKeyboardButton(text=f"📁 {p.title}", callback_data=f"project:open:{p.id}")
        ])
    buttons.append([InlineKeyboardButton(text="➕ Создать проект", callback_data="project:create")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def project_menu(project_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Задачи", callback_data=f"project:tasks:{project_id}")],
        [InlineKeyboardButton(text="📝 Заметки", callback_data=f"project:notes:{project_id}")],
        [InlineKeyboardButton(text="🧠 Память", callback_data=f"project:memory:{project_id}")],
        [InlineKeyboardButton(text="📄 Сделать PDF", callback_data=f"project:pdf:{project_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="projects:list")],
    ])


# ─── Settings menu (owner only) ──────────────────────────────────────────────

def settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="settings:users")],
        [InlineKeyboardButton(text="🧠 Память бота", callback_data="settings:memory")],
        [InlineKeyboardButton(text="🤖 Модели AI", callback_data="settings:models")],
        [InlineKeyboardButton(text="🧾 Логи", callback_data="settings:logs")],
        [InlineKeyboardButton(text="🔄 Перезапустить бота", callback_data="settings:restart")],
    ])


def users_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Выдать доступ", callback_data="settings:invite")],
        [InlineKeyboardButton(text="📋 Список пользователей", callback_data="settings:users_list")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="settings:back")],
    ])


def roles_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 Админ", callback_data="invite:role:admin")],
        [InlineKeyboardButton(text="🤝 Помощник", callback_data="invite:role:assistant")],
        [InlineKeyboardButton(text="👷 Сотрудник", callback_data="invite:role:employee")],
        [InlineKeyboardButton(text="👁 Только просмотр", callback_data="invite:role:viewer")],
    ])


def pin_keyboard() -> InlineKeyboardMarkup:
    """Digits for PIN entry."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1", callback_data="pin:1"),
            InlineKeyboardButton(text="2", callback_data="pin:2"),
            InlineKeyboardButton(text="3", callback_data="pin:3"),
        ],
        [
            InlineKeyboardButton(text="4", callback_data="pin:4"),
            InlineKeyboardButton(text="5", callback_data="pin:5"),
            InlineKeyboardButton(text="6", callback_data="pin:6"),
        ],
        [
            InlineKeyboardButton(text="7", callback_data="pin:7"),
            InlineKeyboardButton(text="8", callback_data="pin:8"),
            InlineKeyboardButton(text="9", callback_data="pin:9"),
        ],
        [
            InlineKeyboardButton(text="⌫", callback_data="pin:back"),
            InlineKeyboardButton(text="0", callback_data="pin:0"),
            InlineKeyboardButton(text="✅", callback_data="pin:confirm"),
        ],
    ])
