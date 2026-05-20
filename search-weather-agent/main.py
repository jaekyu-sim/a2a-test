from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict
import httpx

from a2a_common import get_text_from_a2a, a2a_response, a2a_error


app = FastAPI(title="Weather Search Agent")

class A2ARequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str
    params: Dict[str, Any]


@app.get("/.well-known/agent.json")
def agent_card():
    return {
        "name": "Weather Search Agent",
        "description": "웹 기반 날씨 정보를 조회하는 Agent",
        "url": "http://localhost:8002/message/send",
        "version": "0.1.0",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False
        },
        "skills": [
            {
                "id": "search_weather",
                "name": "Search Weather",
                "description": "지역명을 받아 현재 날씨와 예보를 조회한다.",
                "inputModes": ["text/plain"],
                "outputModes": ["text/plain"]
            }
        ]
    }


async def get_weather(location: str) -> str:
    url = f"https://wttr.in/{location}?format=j1"

    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(url)

    data = res.json()
    current = data["current_condition"][0]
    area = data.get("nearest_area", [{}])[0]

    area_name = area.get("areaName", [{"value": location}])[0]["value"]
    country = area.get("country", [{"value": ""}])[0]["value"]

    temp = current.get("temp_C")
    feels = current.get("FeelsLikeC")
    humidity = current.get("humidity")
    desc = current.get("weatherDesc", [{"value": ""}])[0]["value"]
    wind = current.get("windspeedKmph")

    return f"""
지역: {area_name}, {country}
현재 날씨: {desc}
기온: {temp}℃
체감온도: {feels}℃
습도: {humidity}%
풍속: {wind} km/h
""".strip()


@app.post("/message/send")
async def message_send(req: A2ARequest):
    print("[Search Weather Agent Called]")
    if req.method != "message/send":
        return a2a_error("지원하지 않는 method 입니다.", req.id)

    user_text = get_text_from_a2a(req.model_dump())
    result = await get_weather(user_text)

    return a2a_response(
        f"[Weather Agent 검색 결과]\n질문: {user_text}\n\n{result}",
        req.id
    )

def main():
    print("Hello from search-weather-agent!")


if __name__ == "__main__":
    main()
