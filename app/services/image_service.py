import logging
import base64
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
    )
    # gpt-image-1 returns base64 by default
    image_data = response.data[0]
    
    if hasattr(image_data, 'b64_json') and image_data.b64_json:
        return base64.b64decode(image_data.b64_json)
    
    # dall-e-3 returns URL
    if hasattr(image_data, 'url') and image_data.url:
        import httpx
        async with httpx.AsyncClient() as client:
            img_response = await client.get(image_data.url)
            img_response.raise_for_status()
            return img_response.content
    
    raise ValueError("No image data in response")
