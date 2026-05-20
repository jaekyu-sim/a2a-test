import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from common import ask_llm, ask_llm_json, duckduckgo_search, get_user_text, send_a2a_text


class PlaceAgentExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue):
        user_question = get_user_text(context)

        plan = await ask_llm_json(
            system_prompt="""
너는 장소 추천 Agent다.
사용자 질문을 보고 DuckDuckGo 검색에 적합한 검색어를 JSON으로 만들어라.
반드시 JSON만 반환해라.
""",
            user_prompt=f"""
사용자 질문:
{user_question}

반환 형식:
{{
  "search_query": "검색어",
  "user_intent": "사용자 의도 요약"
}}
"""
        )

        search_query = plan["search_query"]
        search_result = await duckduckgo_search(search_query)

        answer = await ask_llm(
            system_prompt="""
너는 웹 검색 결과를 바탕으로 장소를 추천하는 Agent다.
검색 결과에 없는 내용은 추측하지 마라.
한국어로 답변해라.
""",
            user_prompt=f"""
사용자 질문:
{user_question}

검색어:
{search_query}

DuckDuckGo 검색 결과:
{search_result}

위 검색 결과를 바탕으로 적절한 장소를 추천해라.
"""
        )

        await send_a2a_text(event_queue, answer)

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        raise Exception("cancel not supported")


if __name__ == "__main__":
    skill = AgentSkill(
        id="place_recommendation",
        name="Place Recommendation",
        description="DuckDuckGo 검색 Tool과 LLM을 활용해 사용자 질문에 맞는 장소를 추천한다.",
        tags=["place", "search", "recommendation"],
        examples=["강릉에서 비 오는 날 갈만한 곳 추천해줘"],
    )

    agent_card = AgentCard(
        name="Place Agent",
        description="웹 검색 기반 장소 추천 Agent",
        url="http://localhost:8001/",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[skill],
    )

    handler = DefaultRequestHandler(
        agent_executor=PlaceAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=handler,
    )

    uvicorn.run(app.build(), host="0.0.0.0", port=8001)