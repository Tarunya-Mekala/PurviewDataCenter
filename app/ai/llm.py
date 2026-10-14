from langchain_ollama import ChatOllama

from app.core.config import settings


def get_llm() -> ChatOllama:
    llm = ChatOllama(
        model=settings.LLM_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        temperature=0,
    )

    return llm