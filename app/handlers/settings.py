from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, delete

from app.db.engine import AsyncSessionLocal
from app.db import repos
from app.db.models import AdminSession, UserRole, Memory, User
from app.keyboards import settings_menu, users_menu, roles_keyboard, pin_keyboard
from config.settings import settings

router = Router()
PIN_SESSION_HOURS = 4


class PinState(StatesGroup):
    entering_pin = State()


class InviteState(StatesGroup):
    choosing_role = State()


# ─── Settings button ──────────────────────────────────────────────────────────

@router.message(F.text == "⚙️ Настройки")
async def settings_button(message: Message, state: FSMContext):
    tg = message.from_user
    if tg.id != settings.OWNER_TELEGRAM_ID:
        await message.answer("⛔ Настройки доступны только владельцу.")
        return

    if await _pin_is_valid(tg.id):
        await message.answer("⚙️ Настройки:", reply_markup=settings_menu())
    else:
        await state.set_state(PinState.entering_pin)
        await state.update_data(pin_buffer="")
        await message.answer("🔐 Введи PIN для входа в настройки:",
                              reply_markup=pin_keyboard())


# ─── PIN keyboard ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("pin:"), PinState.entering_pin)
async def pin_input(call: CallbackQuery, state: FSMContext):
    digit = call.data.split(":")[1]
    data = await state.get_data()
    buf = data.get("pin_buffer", "")

    if digit == "back":
        buf = buf[:-1]
    elif digit == "confirm":
        if buf == settings.OWNER_PIN:
            await _save_pin_session(call.from_user.id)
            await state.clear()
            await call.message.edit_text("✅ PIN принят.")
            await call.message.answer("⚙️ Настройки:", reply_markup=settings_menu())
        else:
            buf = ""
            await call.answer("❌ Неверный PIN", show_alert=True)
    else:
        buf += digit

    await state.update_data(pin_buffer=buf)
    mask = "●" * len(buf)
    await call.message.edit_text(f"🔐 PIN: {mask or '—'}", reply_markup=pin_keyboard())
    await call.answer()


# ─── Settings callbacks ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("settings:"))
async def settings_callback(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != settings.OWNER_TELEGRAM_ID:
        await call.answer("⛔ Нет доступа.", show_alert=True)
        return

    if not await _pin_is_valid(call.from_user.id):
        await call.answer("🔐 Сессия истекла. Войди снова.", show_alert=True)
        return

    action = call.data.split(":")[1]

    if action == "users":
        await call.message.edit_text("👥 Пользователи:", reply_markup=users_menu())

    elif action == "users_list":
        async with AsyncSessionLocal() as session:
            users = await repos.get_all_users(session)
        lines = ["<b>👥 Пользователи</b>\n"]
        for u in users:
            name = u.first_name or u.username or str(u.telegram_id)
            lines.append(f"- {name} — {u.role.value} ({u.status.value})")
        await call.message.edit_text("\n".join(lines), reply_markup=users_menu())

    elif action == "invite":
        await state.set_state(InviteState.choosing_role)
        await call.message.edit_text("Выбери роль для нового пользователя:",
                                      reply_markup=roles_keyboard())

    elif action == "logs":
        async with AsyncSessionLocal() as session:
            logs = await repos.get_audit_logs(session, 20)
        if not logs:
            await call.message.edit_text("Логов пока нет.", reply_markup=settings_menu())
        else:
            lines = ["<b>🧾 Последние действия</b>\n"]
            for log in logs:
                dt = log.created_at.strftime("%d.%m %H:%M")
                lines.append(f"[{dt}] {log.action}")
            await call.message.edit_text("\n".join(lines), reply_markup=settings_menu())

    elif action == "memory":
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Очистить личную память", callback_data="memory:clear:personal")],
            [InlineKeyboardButton(text="🗑 Очистить глобальную память", callback_data="memory:clear:global")],
            [InlineKeyboardButton(text="🗑 Очистить ВСЮ память", callback_data="memory:clear:all")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="settings:back")],
        ])
        await call.message.edit_text(
            "🧠 Управление памятью:\n\n"
            "Выбери что очистить или напиши боту:\n"
            "<i>Запомни, что...</i>\n"
            "<i>Что ты помнишь?</i>",
            reply_markup=kb
        )

    elif action == "models":
        await call.message.edit_text(
            f"🤖 Модели:\n\n"
            f"Claude: <code>{settings.CLAUDE_MODEL}</code>\n"
            f"Whisper: <code>{settings.WHISPER_MODEL}</code>\n"
            f"Image: <code>{settings.IMAGE_MODEL}</code>",
            reply_markup=settings_menu()
        )

    elif action == "back":
        await call.message.edit_text("⚙️ Настройки:", reply_markup=settings_menu())

    await call.answer()


# ─── Memory clear callbacks ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("memory:clear:"))
async def memory_clear_callback(call: CallbackQuery):
    if call.from_user.id != settings.OWNER_TELEGRAM_ID:
        await call.answer("⛔ Нет доступа.", show_alert=True)
        return

    scope = call.data.split(":")[2]
    tg = call.from_user

    async with AsyncSessionLocal() as session:
        user = await repos.get_user_by_telegram_id(session, tg.id)
        if not user:
            await call.answer("Пользователь не найден.")
            return

        from app.db.models import MemoryType

        if scope == "personal":
            await session.execute(
                delete(Memory).where(
                    Memory.user_id == user.id,
                    Memory.type == MemoryType.personal
                )
            )
            await session.commit()
            await call.message.edit_text("🗑 Личная память очищена.")

        elif scope == "global":
            await session.execute(
                delete(Memory).where(
                    Memory.user_id == user.id,
                    Memory.type == MemoryType.global_memory
                )
            )
            await session.commit()
            await call.message.edit_text("🗑 Глобальная память очищена.")

        elif scope == "all":
            await session.execute(
                delete(Memory).where(Memory.user_id == user.id)
            )
            await session.commit()
            await call.message.edit_text("🗑 Вся память очищена.")

    await call.answer()


# ─── Invite role selection ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("invite:role:"), InviteState.choosing_role)
async def invite_role_selected(call: CallbackQuery, state: FSMContext):
    role_str = call.data.split(":")[2]
    role = UserRole(role_str)

    async with AsyncSessionLocal() as session:
        owner = await repos.get_user_by_telegram_id(session, call.from_user.id)
        invite = await repos.create_invite(
            session,
            created_by_user_id=owner.id,
            role=role,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )

    bot_username = (await call.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=invite_{invite.code}"

    await state.clear()
    await call.message.edit_text(
        f"✅ Инвайт-ссылка создана:\n\n"
        f"<code>{link}</code>\n\n"
        f"Роль: <b>{role.value}</b>\n"
        f"Срок: 24 часа\n"
        f"Использований: 1"
    )
    await call.answer()


# ─── PIN session helpers ──────────────────────────────────────────────────────

async def _pin_is_valid(telegram_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        user = await repos.get_user_by_telegram_id(session, telegram_id)
        if not user:
            return False
        result = await session.execute(
            select(AdminSession).where(AdminSession.user_id == user.id)
        )
        admin_session = result.scalar_one_or_none()
        if admin_session and admin_session.pin_verified_until:
            return admin_session.pin_verified_until > datetime.utcnow()
    return False


async def _save_pin_session(telegram_id: int):
    async with AsyncSessionLocal() as session:
        user = await repos.get_user_by_telegram_id(session, telegram_id)
        if not user:
            return
        result = await session.execute(
            select(AdminSession).where(AdminSession.user_id == user.id)
        )
        admin_session = result.scalar_one_or_none()
        expires = datetime.utcnow() + timedelta(hours=PIN_SESSION_HOURS)
        if admin_session:
            admin_session.pin_verified_until = expires
            admin_session.failed_attempts = 0
        else:
            session.add(AdminSession(user_id=user.id, pin_verified_until=expires))
        await session.commit()
