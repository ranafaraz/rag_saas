from pydantic import BaseModel, field_validator
from typing import List


class ChatRequest(BaseModel):
    query: str

    @field_validator("query")
    @classmethod
    def query_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("query must not be empty")
        if len(v) > 4096:
            raise ValueError("query too long (max 4096 chars)")
        return v


class CitationItem(BaseModel):
    id: int
    title: str
    source: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    citations: List[CitationItem]
    insufficient_evidence: bool = False


class StreamChatChunk(BaseModel):
    chunk: str
    done: bool
    citations: List[CitationItem] = []
    insufficient_evidence: bool = False


class CrawlOptions(BaseModel):
    crawl_mode: str = "single_page"
    include_pdfs: bool = True
    obey_robots_txt: bool = True
    max_depth: int = 2
    max_pages: int = 200
    max_pdfs: int = 100
    max_pdf_size_mb: int = 20
    requests_per_second: int = 2


class IngestUrlsRequest(BaseModel):
    tenant_id: str
    title: str
    roles: List[str]
    source_uris: List[str]
    crawl_options: CrawlOptions = CrawlOptions()
