from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

from llm.ollama_client import generate_response
from utils.config import load_settings


WEB_QUERY_RE = re.compile(
    r"\b(search\s+(?:the\s+)?web|web\s+search|look\s+up|google|online|internet|latest|current|today|recent|news|market\s+rate|updated|scrape|extract\s+(?:this\s+)?(?:url|page|website))\b",
    flags=re.I,
)
URL_RE = re.compile(r"https?://[^\s)>\]]+", flags=re.I)


@dataclass(frozen=True)
class WebResult:
    title: str
    url: str
    content: str
    score: float | None = None
    published_date: str | None = None


@dataclass(frozen=True)
class WebSearchResponse:
    answer: str
    results: list[WebResult]
    query: str


def _auth_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def wants_web_search(text: str) -> bool:
    return bool(WEB_QUERY_RE.search(text))


def _topic_for_query(query: str) -> str:
    lower = query.lower()
    if any(word in lower for word in ("news", "today", "latest", "recent")):
        return "news"
    if any(word in lower for word in ("stock", "finance", "market", "share price", "crypto")):
        return "finance"
    return "general"


def _time_range_for_query(query: str) -> str | None:
    lower = query.lower()
    if any(word in lower for word in ("today", "latest", "recent", "news")):
        return "week"
    return None


def tavily_search(query: str) -> WebSearchResponse:
    settings = load_settings()
    if not settings.allow_web_search:
        raise RuntimeError("Web search is disabled. Set ALLOW_WEB_SEARCH=true in .env.")
    if not settings.tavily_api_key:
        raise RuntimeError("TAVILY_API_KEY is missing in .env.")

    payload: dict[str, object] = {
        "query": query,
        "search_depth": settings.tavily_search_depth,
        "max_results": max(1, min(settings.tavily_max_results, 10)),
        "topic": _topic_for_query(query),
        "include_answer": "basic",
        "include_raw_content": "text",
        "include_favicon": False,
        "safe_search": True,
    }
    if time_range := _time_range_for_query(query):
        payload["time_range"] = time_range

    response = requests.post(
        "https://api.tavily.com/search",
        headers=_auth_headers(settings.tavily_api_key),
        json=payload,
        timeout=45,
    )
    response.raise_for_status()
    data = response.json()
    results = [
        WebResult(
            title=item.get("title", ""),
            url=item.get("url", ""),
            content=(item.get("raw_content") or item.get("content") or "")[:4000],
            score=item.get("score"),
            published_date=item.get("published_date"),
        )
        for item in data.get("results", [])
    ]
    return WebSearchResponse(answer=data.get("answer", ""), results=results, query=data.get("query", query))


def tavily_extract(urls: list[str], query: str | None = None) -> WebSearchResponse:
    settings = load_settings()
    if not settings.allow_web_search:
        raise RuntimeError("Web search is disabled. Set ALLOW_WEB_SEARCH=true in .env.")
    if not settings.tavily_api_key:
        raise RuntimeError("TAVILY_API_KEY is missing in .env.")

    payload: dict[str, object] = {
        "urls": urls,
        "extract_depth": "advanced",
        "format": "text",
        "include_images": False,
        "include_favicon": False,
        "timeout": 30,
    }
    if query:
        payload["query"] = query
        payload["chunks_per_source"] = 5

    response = requests.post(
        "https://api.tavily.com/extract",
        headers=_auth_headers(settings.tavily_api_key),
        json=payload,
        timeout=45,
    )
    response.raise_for_status()
    data = response.json()
    results = [
        WebResult(
            title=urlparse(item.get("url", "")).netloc,
            url=item.get("url", ""),
            content=(item.get("raw_content") or "")[:5000],
        )
        for item in data.get("results", [])
    ]
    failed = data.get("failed_results", [])
    answer = "" if not failed else "Some URLs could not be extracted: " + ", ".join(item.get("url", "") for item in failed)
    return WebSearchResponse(answer=answer, results=results, query=query or " ".join(urls))


def _format_sources(results: list[WebResult]) -> str:
    lines = []
    for index, result in enumerate(results, start=1):
        host = urlparse(result.url).netloc or result.url
        date = f", published {result.published_date}" if result.published_date else ""
        lines.append(f"{index}. {result.title or host} ({host}{date})\nURL: {result.url}\n{result.content[:1800]}")
    return "\n\n".join(lines)


def answer_with_web(query: str, local_context: str | None = None) -> tuple[str, list[str]]:
    urls = URL_RE.findall(query)
    search = tavily_extract(urls[:5], query=query) if urls else tavily_search(query)
    web_context = _format_sources(search.results)
    context_parts = []
    if local_context:
        context_parts.append(f"Local business context:\n{local_context}")
    if search.answer:
        context_parts.append(f"Tavily short answer:\n{search.answer}")
    if web_context:
        context_parts.append(f"Web sources:\n{web_context}")

    answer = generate_response(
        (
            "Answer the user's question using the local business context and current web sources. "
            "Prefer local business data for company-specific facts, and use web sources only for updated external information. "
            "Cite source URLs in a short Sources section. If sources disagree, say so."
            f"\n\nUser question:\n{query}"
        ),
        "\n\n".join(context_parts) if context_parts else None,
    )
    return answer, [result.url for result in search.results if result.url]
