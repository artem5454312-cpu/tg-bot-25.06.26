from aiogram import Dispatcher
from app.handlers import messages, tasks, projects, settings as settings_handler


def register_all_handlers(dp: Dispatcher):
    dp.include_router(settings_handler.router)  # settings first (PIN state)
    dp.include_router(tasks.router)
    dp.include_router(projects.router)
    dp.include_router(messages.router)           # free text last (catch-all)
