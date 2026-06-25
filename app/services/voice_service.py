import logging
import tempfile
import os
from openai import AsyncOpenAI
from aiogram import Bot
from aiogram.types import Voice
from config.settings import settings

logger = logging.getLogger(__name__)
openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def transcribe_voice(bot: Bot, voice: Voice) -> str:
    """Download voice message from Telegram and transcribe via Whisper."""
    file_info = await bot.get_file(voice.file_id)
    
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        await bot.download_file(file_info.file_path, tmp_path)
        
        with open(tmp_path, "rb") as audio_file:
            transcript = await openai_client.audio.transcriptions.create(
                model=settings.WHISPER_MODEL,
                file=audio_file,
                language="ru"
            )
        return transcript.text
    except Exception as e:
        logger.error(f"Whisper transcription error: {e}")
        raise
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
