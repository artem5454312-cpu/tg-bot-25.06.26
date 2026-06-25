import logging
import base64
import httpx
from openai import AsyncOpenAI
from config.settings import settings

logger = logging.getLogger(__name__)
openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def generate_image(prompt: str) -> bytes:
    """Generate image via DALL-E and return bytes."""
    response = await openai_client.images.generate(
        model=settings.IMAGE_MODEL,
        prompt=prompt,
        n=1,
        size="1024x1536",   # 9:16 vertical — ideal for reels/stories
        quality="high",
    )
    image_data = response.data[0]

    if hasattr(image_data, 'b64_json') and image_data.b64_json:
        return base64.b64decode(image_data.b64_json)

    if hasattr(image_data, 'url') and image_data.url:
        async with httpx.AsyncClient() as client:
            img_response = await client.get(image_data.url)
            img_response.raise_for_status()
            return img_response.content

    raise ValueError("No image data in response")


async def edit_photo(image_bytes: bytes, instruction: str) -> bytes:
    """Edit existing photo using GPT Image."""
    import io
    from PIL import Image as PILImage

    # Convert to PNG for API
    img = PILImage.open(io.BytesIO(image_bytes)).convert("RGBA")
    png_buffer = io.BytesIO()
    img.save(png_buffer, format="PNG")
    png_buffer.seek(0)

    response = await openai_client.images.edit(
        model=settings.IMAGE_MODEL,
        image=("image.png", png_buffer, "image/png"),
        prompt=instruction,
        n=1,
        size="1024x1536",
    )
    image_data = response.data[0]

    if hasattr(image_data, 'b64_json') and image_data.b64_json:
        return base64.b64decode(image_data.b64_json)

    if hasattr(image_data, 'url') and image_data.url:
        async with httpx.AsyncClient() as client:
            img_response = await client.get(image_data.url)
            img_response.raise_for_status()
            return img_response.content

    raise ValueError("No image data in response")
