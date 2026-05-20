import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from common import ask_llm, ask_llm_json, duckduckgo_search, get_user_text, send_a2a_text


class WeatherAgentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue):
        user_question = get_user_text(context)

        plan = await ask_llm_json(
            system_prompt="""
너는 날씨 검색 Agent다.
사용자 질문을 보고 DuckDuckGo에서 날씨를 검색하기 위한 검색어를 JSON으로 만들어라.
지역명, 날짜 표현, 날씨 의도를 자유롭게 추론해라.
반드시 JSON만 반환해라.
""",
            user_prompt=f"""
사용자 질문:
{user_question}

반환 형식:
{{
  "search_query": "검색어",
  "location": "추론한 지역",
  "date": "추론한 날짜 표현",
  "user_intent": "사용자 의도 요약"
}}
"""
        )

        search_query = plan["search_query"]
        search_result = await duckduckgo_search(search_query)

        answer = await ask_llm(
            system_prompt="""
너는 웹 검색 결과를 바탕으로 날씨를 알려주는 Agent다.
검색 결과에 없는 날씨 정보는 추측하지 마라.
강수 여부, 기온, 체감상 주의사항이 있으면 요약해라.
한국어로 답변해라.
""",
            user_prompt=f"""
사용자 질문:
{user_question}

LLM이 만든 검색 계획:
{plan}

DuckDuckGo 검색 결과:
{search_result}

위 검색 결과를 바탕으로 날씨 답변을 작성해라.
"""
        )

        await send_a2a_text(event_queue, answer)

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        raise Exception("cancel not supported")


if __name__ == "__main__":
    skill = AgentSkill(
        id="weather_search",
        name="Weather Search",
        description="DuckDuckGo 검색 Tool과 LLM을 활용해 사용자 질문에 맞는 지역 날씨를 알려준다.",
        tags=["weather", "search"],
        examples=["이번 주말 강릉 날씨 알려줘"],
    )

    agent_card = AgentCard(
        name="Weather Agent",
        description="웹 검색 기반 날씨 Agent",
        url="http://localhost:8002/",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[skill],
    )

    handler = DefaultRequestHandler(
        agent_executor=WeatherAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=handler,
    )

    uvicorn.run(app.build(), host="0.0.0.0", port=8002)