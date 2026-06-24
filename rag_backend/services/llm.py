"""
LLM generation pipeline: calls Ollama via langchain with strict grounding prompt.
Falls back gracefully when Ollama is unreachable.
"""
import os
from typing import Tuple, List, Generator

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", 512))
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://vllm:8000/v1")
VLLM_MODEL = os.getenv("VLLM_MODEL", "Qwen/Qwen3-8B")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "local-vllm")

SYSTEM_PROMPT = """You are a precise, professional knowledge assistant.
Rules you MUST follow without exception:
1. Answer ONLY using the provided Context. Do not use outside knowledge.
2. Cite every fact using [Citation N] markers where N is the citation number.
3. If the Context does not contain enough information to answer, respond with EXACTLY:
   "Insufficient evidence to answer this question from your knowledge base."
4. Be concise and factual. Do not speculate or add caveats beyond what is in the Context.
5. Do not claim that you are a person mentioned in the Context.
6. For person-related questions, answer in third person using cited facts."""


def _citation_doc_key(metadata: dict) -> str:
    doc_id = metadata.get("doc_id")
    if doc_id:
        return f"doc:{doc_id}"
    title = metadata.get("title", "Unknown Source")
    source = metadata.get("source", "")
    return f"title:{title}|source:{source}"


def _build_context_and_citations(chunks: list) -> tuple[str, list[dict]]:
    context_parts = []
    citations = []
    citation_id_by_doc: dict[str, int] = {}

    for chunk in chunks:
        content = (chunk.get("content") or "").strip()
        metadata = chunk.get("metadata") or {}
        score = chunk.get("score", 0.0)

        doc_key = _citation_doc_key(metadata)
        citation_id = citation_id_by_doc.get(doc_key)
        if citation_id is None:
            citation_id = len(citations) + 1
            citation_id_by_doc[doc_key] = citation_id
            citations.append({
                "id": citation_id,
                "title": metadata.get("title", "Unknown Source"),
                "source": metadata.get("source", ""),
                "score": round(score, 4),
            })

        context_parts.append(f"[Citation {citation_id}]: {content}")

    return "\n\n".join(context_parts), citations


def _build_prompt(query: str, context_text: str, base_prompt: str = "") -> str:
    base_prompt_block = ""
    if base_prompt:
        base_prompt_block = f"\nTenant Base Prompt:\n{base_prompt}\n"

    return f"""{SYSTEM_PROMPT}{base_prompt_block}

Context:
{context_text}

Question: {query}

Answer:"""


def generate_rag_answer(query: str, chunks: list, base_prompt: str = "",
                        llm_config: dict | None = None) -> Tuple[str, List[dict]]:
    """
    Generates a grounded answer using the resolved provider.

    Provider selection: per-tenant ``llm_config`` (BYOK) overrides the env default,
    which defaults to the free Groq tier and degrades to local Ollama when no key
    is available. See ``providers.registry``.
    """
    from providers import get_provider

    context_text, citations = _build_context_and_citations(chunks)
    full_prompt = _build_prompt(query, context_text, base_prompt)

    try:
        answer = get_provider(llm_config).generate(full_prompt)
    except Exception as e:
        answer = f"The AI model is currently unavailable. Please try again shortly. (Error: {str(e)[:120]})"
        return answer, []

    # If the LLM signals insufficient evidence, clear citations so UI doesn't show misleading links
    if "insufficient evidence" in answer.lower():
        citations = []

    return answer, citations


def stream_rag_answer(query: str, chunks: list, base_prompt: str = "",
                      llm_config: dict | None = None) -> Generator[str, None, list]:
    """
    Streams a grounded answer token-by-token using the resolved provider.
    Yields text chunks as they are produced.
    Returns the citations list via StopIteration value (use as a generator).
    """
    from providers import get_provider

    context_text, citations = _build_context_and_citations(chunks)
    full_prompt = _build_prompt(query, context_text, base_prompt)

    try:
        for token in get_provider(llm_config).stream(full_prompt):
            yield token
    except Exception as e:
        yield f"The AI model is currently unavailable. Please try again shortly. (Error: {str(e)[:120]})"
        return []

    return citations
