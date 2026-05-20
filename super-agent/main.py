from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, Dict
import httpx
import uuid

from a2a_common import get_text_from_a2a, a2a_response, a2a_error

import json
from openai import OpenAI


app = FastAPI(title="Super Agent")

llm = OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="dummy"
)


PLACE_AGENT_URL = "http://localhost:8001"
WEATHER_AGENT_URL = "http://localhost:8002"


class A2ARequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str
    params: Dict[str, Any]


@app.get("/.well-known/agent.json")
def agent_card():
    return {
        "name": "Super Agent",
        "description": "Place Agent와 Weather Agent를 A2A로 호출해 결과를 통합하는 Agent",
        "url": "http://localhost:8000/message/send",
        "version": "0.1.0",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False
        },
        "skills": [
            {
                "id": "place_weather_orchestration",
                "name": "Place Weather Orchestration",
                "description": "장소 검색 Agent와 날씨 검색 Agent를 호출하여 통합 답변을 생성한다.",
                "inputModes": ["text/plain"],
                "outputModes": ["text/plain"]
            }
        ]
    }


def make_a2a_payload(text: str) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [
                    {
                        "kind": "text",
                        "text": text
                    }
                ]
            }
        }
    }


def extract_artifact_text(a2a_result: Dict[str, Any]) -> str:
    artifacts = a2a_result.get("result", {}).get("artifacts", [])
    texts = []

    for artifact in artifacts:
        for part in artifact.get("parts", []):
            if "text" in part:
                texts.append(part["text"])

    return "\n".join(texts)


async def call_agent(agent_base_url: str, text: str) -> str:
    async with httpx.AsyncClient(timeout=20) as client:
        card = await client.get(f"{agent_base_url}/.well-known/agent.json")
        card.raise_for_status()

        endpoint = card.json()["url"]

        res = await client.post(endpoint, json=make_a2a_payload(text))
        res.raise_for_status()

    return extract_artifact_text(res.json())


def plan_user_request(user_text: str) -> dict:
    prompt = f"""
너는 Super Agent의 Planner다.

사용자 질문을 분석해서 아래 JSON만 반환해라.

규칙:
- location은 날씨/장소 검색에 사용할 지역명만 추출한다.
- date는 오늘, 내일, 이번 주말 같은 시간 표현을 추출한다.
- 장소 검색이 필요하면 need_place=true
- 날씨 검색이 필요하면 need_weather=true
- 설명 문장 없이 JSON만 반환한다.

사용자 질문:
{user_text}

반환 형식:
{{
  "location": "지역명",
  "date": "시간 표현",
  "need_place": true,
  "need_weather": true
}}
"""

    response = llm.chat.completions.create(
        model="local-model",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0
    )

    content = response.choices[0].message.content.strip()

    try:
        return json.loads(content)
    except Exception:
        return {
            "location": user_text,
            "date": "",
            "need_place": True,
            "need_weather": True
        }


@app.post("/message/send")
async def message_send(req: A2ARequest):
    print("[Super Agent Called]")
    if req.method != "message/send":
        return a2a_error("지원하지 않는 method 입니다.", req.id)

    user_text = get_text_from_a2a(req.model_dump())

    #place_result = await call_agent(PLACE_AGENT_URL, user_text)
    #weather_result = await call_agent(WEATHER_AGENT_URL, user_text)
    plan = plan_user_request(user_text)

    location = plan.get("location", user_text)
    date = plan.get("date", "")

    place_result = ""
    weather_result = ""

    if plan.get("need_place", False):
        place_query = f"{location} 주변 갈만한 곳"
        place_result = await call_agent(PLACE_AGENT_URL, place_query)

    if plan.get("need_weather", False):
        weather_query = location
        weather_result = await call_agent(WEATHER_AGENT_URL, weather_query)

    final_answer = generate_final_answer(
        user_text=user_text,
        place_result=place_result,
        weather_result=weather_result
    )

    return a2a_response(final_answer, req.id)
    # final_answer = f"""
    #     [Super Agent 최종 답변]

    #     사용자 질문:
    #     {user_text}

    #     1. 장소 검색 결과
    #     {place_result}

    #     2. 날씨 검색 결과
    #     {weather_result}

    #     요약:
    #     위 장소 검색 결과를 참고하면 사용자가 요청한 지역/장소에 대한 기본 정보를 확인할 수 있습니다.
    #     날씨 정보는 Weather Agent가 웹 기반으로 조회한 현재 조건입니다.
    # """.strip()

    #return a2a_response(final_answer, req.id)


@app.post("/ask")
async def ask(body: Dict[str, str]):
    user_text = body["question"]

    place_result = await call_agent(PLACE_AGENT_URL, user_text)
    weather_result = await call_agent(WEATHER_AGENT_URL, user_text)

    return {
        "question": user_text,
        "place_result": place_result,
        "weather_result": weather_result,
        "final": f"{place_result}\n\n{weather_result}"
    }


def generate_final_answer(user_text: str, place_result: str, weather_result: str) -> str:
    prompt = f"""
너는 친절한 여행/날씨 안내 Agent다.

사용자 질문:
{user_text}

장소 검색 결과:
{place_result}

날씨 검색 결과:
{weather_result}

위 정보를 바탕으로 사용자에게 자연스럽게 답변해라.
단, 검색 결과에 없는 정보는 추측하지 마라.
"""

    response = llm.chat.completions.create(
        model="local-model",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )

    return response.choices[0].message.content.strip()


def main():
    print("Hello from super-agent!")


if __name__ == "__main__":
    main()
