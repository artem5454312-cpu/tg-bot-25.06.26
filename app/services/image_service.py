import logging
import httpx
from openai import AsyncOpenAI
from config.settings import settings

logger = logging.getLogger(__name__)
openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def generate_image(prompt: str) -> bytes:
    """Generate image via GPT Image and return bytes."""
    response = await openai_client.images.generate(
        model=settings.IMAGE_MODEL,
        prompt=prompt,
        n=1,
        size="1024x1024",
        response_format="url"
    )
    image_url = response.data[0].url
    
    async with httpx.AsyncClient() as client:
        img_response = await client.get(image_url)
        img_response.raise_for_status()
        return img_response.content
