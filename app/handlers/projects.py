from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from app.db.engine import AsyncSessionLocal
from app.db import repos, task_repo
from app.keyboards import projects_list, project_menu

router = Router()


async def show_projects_list(message: Message):
    tg = message.from_user
    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id)
        projects = await repos.get_user_projects(session, user.id)

    if not projects:
        await message.answer(
            "📁 Проектов пока нет.\n\nНапиши: <i>Создай проект [название]</i>",
            reply_markup=projects_list([])
        )
    else:
        lines = ["<b>📁 Проекты</b>\n"]
        for i, p in enumerate(projects, 1):
            lines.append(f"{i}. {p.title}")
        await message.answer("\n".join(lines), reply_markup=projects_list(projects))


@router.message(F.text == "📁 Проекты")
async def projects_button(message: Message):
    await show_projects_list(message)


@router.callback_query(F.data.startswith("projects:"))
async def projects_callback(call: CallbackQuery):
    action = call.data.split(":")[1]
    if action == "list":
        tg = call.from_user
        async with AsyncSessionLocal() as session:
            user = await repos.get_or_create_user(session, tg.id)
            projects = await repos.get_user_projects(session, user.id)
        lines = ["<b>📁 Проекты</b>\n"]
        for i, p in enumerate(projects, 1):
            lines.append(f"{i}. {p.title}")
        await call.message.edit_text("\n".join(lines) if projects else "Проектов нет.",
                                      reply_markup=projects_list(projects))
    await call.answer()


@router.callback_query(F.data.startswith("project:"))
async def project_callback(call: CallbackQuery):
    parts = call.data.split(":")
    action = parts[1]
    tg = call.from_user

    if action == "create":
        await call.message.answer("Напиши название нового проекта:")
        await call.answer()
        return

    project_id = int(parts[2])

    async with AsyncSessionLocal() as session:
        user = await repos.get_or_create_user(session, tg.id)
        project = await repos.get_project_by_id(session, project_id)

        if not project:
            await call.answer("Проект не найден.")
            return

        if action == "open":
            tasks = await task_repo.get_all_active_tasks(session, user.id)
            project_tasks = [t for t in tasks if t.project_id == project_id]
            lines = [f"<b>📁 {project.title}</b>\n"]
            if project_tasks:
                lines.append(f"Задач: {len(project_tasks)}")
                for t in project_tasks[:5]:
                    lines.append(f"  🔲 {t.title}")
                if len(project_tasks) > 5:
                    lines.append(f"  ... и ещё {len(project_tasks) - 5}")
            else:
                lines.append("Задач нет.")
            await call.message.edit_text("\n".join(lines), reply_markup=project_menu(project_id))

        elif action == "tasks":
            tasks = await task_repo.get_all_active_tasks(session, user.id)
            project_tasks = [t for t in tasks if t.project_id == project_id]
            if project_tasks:
                lines = [f"<b>📋 Задачи: {project.title}</b>\n"]
                for t in project_tasks:
                    dt = f" [{t.date}]" if t.date else ""
                    lines.append(f"🔲 {t.title}{dt}")
                await call.message.edit_text("\n".join(lines),
                                              reply_markup=project_menu(project_id))
            else:
                await call.message.edit_text("Задач в проекте нет.",
                                              reply_markup=project_menu(project_id))

        elif action == "memory":
            from app.db.models import MemoryType
            mems = await repos.get_user_memories(session, user.id,
                                                  project_id=project_id)
            if mems:
                lines = [f"<b>🧠 Память: {project.title}</b>\n"]
                for m in mems:
                    lines.append(f"• {m.content[:100]}")
                await call.message.edit_text("\n".join(lines),
                                              reply_markup=project_menu(project_id))
            else:
                await call.message.edit_text("Памяти по проекту нет.",
                                              reply_markup=project_menu(project_id))

        elif action == "pdf":
            await call.message.answer(f"Напиши: <i>Сделай PDF по проекту {project.title}</i>")

    await call.answer()
