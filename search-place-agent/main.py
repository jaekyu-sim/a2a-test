from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict
import httpx
from bs4 import BeautifulSoup

from a2a_common import get_text_from_a2a, a2a_response, a2a_error

app = FastAPI(title="Place Search Agent")


class A2ARequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str
    params: Dict[str, Any]


@app.get("/.well-known/agent.json")
def agent_card():
    return {
        "name": "Place Search Agent",
        "description": "웹 검색 기반으로 장소 정보를 검색하는 Agent",
        "url": "http://localhost:8001/message/send",
        "version": "0.1.0",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False
        },
        "skills": [
            {
                "id": "search_place",
                "name": "Search Place",
                "description": "장소명, 관광지, 주변 장소 정보를 웹 검색으로 찾는다.",
                "inputModes": ["text/plain"],
                "outputModes": ["text/plain"]
            }
        ]
    }


async def search_duckduckgo(query: str) -> str:
    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.post(url, data={"q": query}, headers=headers)

    soup = BeautifulSoup(res.text, "html.parser")
    results = []

    for item in soup.select(".result")[:5]:
        title_el = item.select_one(".result__title")
        snippet_el = item.select_one(".result__snippet")

        title = title_el.get_text(" ", strip=True) if title_el else ""
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""

        if title:
            results.append(f"- {title}\n  {snippet}")

    if not results:
        return "검색 결과를 찾지 못했습니다."

    return "\n".join(results)


@app.post("/message/send")
async def message_send(req: A2ARequest):
    print("[Search Place Agent Called]")
    if req.method != "message/send":
        return a2a_error("지원하지 않는 method 입니다.", req.id)

    user_text = get_text_from_a2a(req.model_dump())
    query = f"{user_text} 장소 관광지 위치 주변 정보"

    result = await search_duckduckgo(query)

    return a2a_response(
        f"[Place Agent 검색 결과]\n질문: {user_text}\n\n{result}",
        req.id
    )

def main():
    print("Hello from search-place-agent!")


if __name__ == "__main__":
    main()
