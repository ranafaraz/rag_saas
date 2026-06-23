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


def _generate_with_openai_compatible(prompt: str) -> str:
    from openai import OpenAI

    client = OpenAI(base_url=VLLM_BASE_URL, api_key=VLLM_API_KEY)
    response = client.chat.completions.create(
        model=VLLM_MODEL,
        temperature=0.0,
        max_tokens=OLLAMA_NUM_PREDICT,
        messages=[
            {"role": "system", "content": "Follow the user prompt exactly and answer only from provided context."},
            {"role": "user", "content": prompt},
        ],
    )
    return (response.choices[0].message.content or "").strip()


def generate_rag_answer(query: str, chunks: list, base_prompt: str = "") -> Tuple[str, List[dict]]:
    """
    Generates a grounded answer using the configured AI gateway.
    Production uses an OpenAI-compatible vLLM endpoint; local dev can use Ollama.
    """
    context_text, citations = _build_context_and_citations(chunks)
    full_prompt = _build_prompt(query, context_text, base_prompt)

    try:
        if LLM_PROVIDER in {"vllm", "openai_compatible", "openai-compatible"}:
            answer = _generate_with_openai_compatible(full_prompt)
        else:
            from langchain_community.llms import Ollama
            llm = Ollama(
                base_url=OLLAMA_BASE_URL,
                model=OLLAMA_MODEL,
                temperature=0.0,
                num_predict=OLLAMA_NUM_PREDICT,
            )
            answer = llm.invoke(full_prompt).strip()
    except Exception as e:
        answer = f"The AI model is currently unavailable. Please try again shortly. (Error: {str(e)[:120]})"
        return answer, []

    # If the LLM signals insufficient evidence, clear citations so UI doesn't show misleading links
    if "insufficient evidence" in answer.lower():
        citations = []

    return answer, citations


def stream_rag_answer(query: str, chunks: list, base_prompt: str = "") -> Generator[str, None, list]:
    """
    Streams a grounded answer token-by-token using Ollama.
    Yields text chunks as they are produced.
    Returns the citations list via StopIteration value (use as a generator).
    """
    context_text, citations = _build_context_and_citations(chunks)
    full_prompt = _build_prompt(query, context_text, base_prompt)

    try:
        if LLM_PROVIDER in {"vllm", "openai_compatible", "openai-compatible"}:
            from openai import OpenAI

            client = OpenAI(base_url=VLLM_BASE_URL, api_key=VLLM_API_KEY)
            stream = client.chat.completions.create(
                model=VLLM_MODEL,
                temperature=0.0,
                max_tokens=OLLAMA_NUM_PREDICT,
                stream=True,
                messages=[
                    {"role": "system", "content": "Follow the user prompt exactly and answer only from provided context."},
                    {"role": "user", "content": full_prompt},
                ],
            )
            for event in stream:
                token = event.choices[0].delta.content or ""
                if token:
                    yield token
        else:
            from langchain_community.llms import Ollama
            llm = Ollama(
                base_url=OLLAMA_BASE_URL,
                model=OLLAMA_MODEL,
                temperature=0.0,
                num_predict=OLLAMA_NUM_PREDICT,
            )
            for chunk in llm.stream(full_prompt):
                yield chunk
    except Exception as e:
        yield f"The AI model is currently unavailable. Please try again shortly. (Error: {str(e)[:120]})"
        return []

    return citations
