import json
import re
import httpx
from bs4 import BeautifulSoup
from openai import AsyncOpenAI
from a2a.utils import new_agent_text_message


llm = AsyncOpenAI(
    base_url="http://localhost:8080/v1",
    api_key="local"
)


async def ask_llm(system_prompt: str, user_prompt: str) -> str:
    res = await llm.chat.completions.create(
        model="gpt-oss-20b",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2
    )
    return res.choices[0].message.content.strip()


async def ask_llm_json(system_prompt: str, user_prompt: str) -> dict:
    text = await ask_llm(system_prompt, user_prompt)

    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


async def duckduckgo_search(query: str, max_results: int = 5) -> str:
    url = "https://html.duckduckgo.com/html/"
    headers = {"User-Agent": "Mozilla/5.0"}

    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.post(url, data={"q": query}, headers=headers)

    soup = BeautifulSoup(res.text, "html.parser")
    results = []

    for item in soup.select(".result")[:max_results]:
        title_el = item.select_one(".result__title")
        snippet_el = item.select_one(".result__snippet")
        link_el = item.select_one(".result__a")

        title = title_el.get_text(" ", strip=True) if title_el else ""
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        link = link_el.get("href") if link_el else ""

        if title:
            results.append(f"- 제목: {title}\n  요약: {snippet}\n  링크: {link}")

    return "\n".join(results) if results else "검색 결과 없음"


def get_user_text(context) -> str:
    return context.get_user_input()


async def send_a2a_text(event_queue, text: str):
    await event_queue.enqueue_event(new_agent_text_message(text))


def extract_a2a_text(data: dict) -> str:
    texts = []

    def walk(obj):
        if isinstance(obj, dict):
            if isinstance(obj.get("text"), str):
                texts.append(obj["text"])
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for x in obj:
                walk(x)

    walk(data)
    return "\n".join(dict.fromkeys(texts))