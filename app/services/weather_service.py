import logging
import os
import aiohttp

logger = logging.getLogger(__name__)

WEATHER_ICONS = {
    "Clear": "☀️ ясно",
    "Clouds": "☁️ облачно",
    "Rain": "🌧 дождь",
    "Drizzle": "🌦 морось",
    "Thunderstorm": "⛈ гроза",
    "Snow": "❄️ снег",
    "Mist": "🌫 туман",
    "Fog": "🌫 туман",
    "Haze": "🌫 дымка",
}


async def get_weather(city: str = "Moscow") -> dict:
    """Get current weather via OpenWeatherMap."""
    api_key = os.environ.get("WEATHER_API_KEY", "")
    if not api_key:
        return {"error": "no_key"}

    url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?q={city}&appid={api_key}&units=metric&lang=ru"
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return {"error": f"status_{resp.status}"}
                data = await resp.json()

        main = data.get("weather", [{}])[0].get("main", "")
        desc = data.get("weather", [{}])[0].get("description", "")
        temp = round(data.get("main", {}).get("temp", 0))
        feels = round(data.get("main", {}).get("feels_like", 0))

        icon = WEATHER_ICONS.get(main, "🌤")

        return {
            "icon": icon,
            "description": desc,
            "temp": temp,
            "feels_like": feels,
            "city": city,
        }
    except Exception as e:
        logger.error(f"Weather error: {e}")
        return {"error": str(e)}
