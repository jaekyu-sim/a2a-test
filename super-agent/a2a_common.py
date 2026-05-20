import uuid
import httpx
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from common import ask_llm, ask_llm_json, extract_a2a_text, get_user_text, send_a2a_text


PLACE_AGENT_URL = "http://localhost:8001"
WEATHER_AGENT_URL = "http://localhost:8002"


def make_a2a_payload(text: str) -> dict:
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
                ],
                "messageId": str(uuid.uuid4())
            }
        }
    }


async def call_a2a_agent(agent_url: str, text: str) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        await client.get(f"{agent_url}/.well-known/agent.json")
        res = await client.post(agent_url, json=make_a2a_payload(text))
        res.raise_for_status()
        return extract_a2a_text(res.json())


class SuperAgentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue):
        user_question = get_user_text(context)

        plan = await ask_llm_json(
            system_prompt="""
너는 A2A Super Agent다.
사용자 질문을 보고 어떤 하위 Agent를 호출할지 결정해라.
반드시 JSON만 반환해라.

Agent 목록:
1. Place Agent: 장소 추천, 관광지, 갈만한 곳 검색
2. Weather Agent: 날씨, 기온, 비, 주말 날씨 검색
""",
            user_prompt=f"""
사용자 질문:
{user_question}

반환 형식:
{{
  "call_place_agent": true,
  "call_weather_agent": true,
  "place_agent_question": "Place Agent에게 보낼 질문",
  "weather_agent_question": "Weather Agent에게 보낼 질문",
  "reason": "호출 판단 이유"
}}
"""
        )

        place_result = ""
        weather_result = ""

        if plan.get("call_place_agent"):
            place_result = await call_a2a_agent(
                PLACE_AGENT_URL,
                plan["place_agent_question"]
            )

        if plan.get("call_weather_agent"):
            weather_result = await call_a2a_agent(
                WEATHER_AGENT_URL,
                plan["weather_agent_question"]
            )

        final_answer = await ask_llm(
            system_prompt="""
너는 A2A Super Agent다.
하위 Agent들의 답변을 종합해 최종 답변을 작성해라.
검색 결과에 없는 내용은 추측하지 마라.
한국어로 답변해라.
""",
            user_prompt=f"""
사용자 질문:
{user_question}

Super Agent 호출 계획:
{plan}

Place Agent 답변:
{place_result}

Weather Agent 답변:
{weather_result}

최종 답변을 작성해라.
"""
        )

        await send_a2a_text(event_queue, final_answer)

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        raise Exception("cancel not supported")


if __name__ == "__main__":
    skill = AgentSkill(
        id="super_orchestration",
        name="Super Agent Orchestration",
        description="LLM이 사용자 질문을 분석하고 Place Agent와 Weather Agent를 A2A로 호출한다.",
        tags=["a2a", "super-agent", "orchestration"],
        examples=["강릉 이번 주말 날씨랑 갈만한 곳 알려줘"],
    )

    agent_card = AgentCard(
        name="Super Agent",
        description="A2A 기반 하위 Agent orchestration Agent",
        url="http://localhost:8000/",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[skill],
    )

    handler = DefaultRequestHandler(
        agent_executor=SuperAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=handler,
    )

    uvicorn.run(app.build(), host="0.0.0.0", port=8000)