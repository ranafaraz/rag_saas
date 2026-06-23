import os
import uuid
import hashlib
import re
import tempfile
import time
from collections import deque
from datetime import datetime, timezone
from urllib.parse import urljoin, urldefrag, urlparse
from urllib.robotparser import RobotFileParser
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance
from config import settings
import requests
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader
from services.embeddings import get_embedding_dimension, get_embeddings


def _normalize_url(raw_url: str) -> str:
    clean, _ = urldefrag((raw_url or '').strip())
    return clean


def _same_domain(a: str, b: str) -> bool:
    return urlparse(a).netloc == urlparse(b).netloc


def _allowed_by_robots(url: str, obey_robots_txt: bool, cache: dict) -> bool:
    if not obey_robots_txt:
        return True
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = cache.get(robots_url)
    if rp is None:
        rp = RobotFileParser()
        rp.set_url(robots_url)
        try:
            rp.read()
        except Exception:
            return True
        cache[robots_url] = rp
    try:
        return rp.can_fetch("*", url)
    except Exception:
        return True


def _discover_sitemap_urls(seed_url: str, max_pages: int) -> list[str]:
    parsed = urlparse(seed_url)
    sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
    try:
        res = requests.get(sitemap_url, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.content, 'xml')
        urls = [loc.text.strip() for loc in soup.find_all('loc') if (loc.text or '').strip()]
        return urls[:max_pages]
    except Exception:
        return []

def _build_source_reference(source_type: str, source_uri: str) -> str:
    if source_type == "url":
        return source_uri
    filename = os.path.basename(source_uri)
    return f"/files/{filename}"


def _hash_text(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _roles_signature(roles: list) -> str:
    normalized = sorted({str(role).strip().lower() for role in roles if str(role).strip()})
    return "|".join(normalized)


def _source_trust_score(source_type: str, source_uri: str) -> float:
    if source_type == "url":
        if re.search(r"\b(edu|gov)\b", source_uri.lower()):
            return 0.9
        return 0.75
    if source_type == "file":
        return 0.8
    return 0.7


def _extract_effective_date(text: str) -> str | None:
    patterns = [
        r"\b(20\d{2}-\d{2}-\d{2})\b",
        r"\b(\d{1,2}/\d{1,2}/20\d{2})\b",
    ]
    sample = (text or "")[:8000]
    for pattern in patterns:
        match = re.search(pattern, sample)
        if match:
            return match.group(1)
    return None


def _is_duplicate_for_tenant_role(
    qclient: QdrantClient,
    collection_name: str,
    tenant_id: str,
    content_hash: str,
) -> bool:
    from qdrant_client.http import models as qmodels

    duplicate_filter = qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="metadata.tenant_id",
                match=qmodels.MatchValue(value=tenant_id),
            ),
            qmodels.FieldCondition(
                key="metadata.content_hash",
                match=qmodels.MatchValue(value=content_hash),
            ),
        ]
    )

    points, _ = qclient.scroll(
        collection_name=collection_name,
        scroll_filter=duplicate_filter,
        limit=1,
        with_payload=False,
    )
    return len(points) > 0


def _merge_roles_for_existing_content(
    qclient: QdrantClient,
    collection_name: str,
    tenant_id: str,
    content_hash: str,
    new_roles: list,
) -> int:
    from qdrant_client.http import models as qmodels

    duplicate_filter = qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="metadata.tenant_id",
                match=qmodels.MatchValue(value=tenant_id),
            ),
            qmodels.FieldCondition(
                key="metadata.content_hash",
                match=qmodels.MatchValue(value=content_hash),
            ),
        ]
    )

    points, _ = qclient.scroll(
        collection_name=collection_name,
        scroll_filter=duplicate_filter,
        limit=2000,
        with_payload=True,
        with_vectors=False,
    )
    if not points:
        return 0

    normalized_new_roles = {str(role).strip() for role in new_roles if str(role).strip()}
    updated_count = 0
    for point in points:
        payload = point.payload or {}
        metadata = payload.get("metadata") or {}
        existing_roles = metadata.get("roles") or []
        merged_roles = sorted(set(existing_roles) | normalized_new_roles)
        if merged_roles == sorted(set(existing_roles)):
            continue

        metadata["roles"] = merged_roles
        metadata["roles_signature"] = _roles_signature(merged_roles)
        qclient.set_payload(
            collection_name=collection_name,
            payload={"metadata": metadata},
            points=[point.id],
        )
        updated_count += 1

    return updated_count

def init_qdrant_client():
    return QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)

def ensure_collection(client: QdrantClient, collection_name: str, vector_size: int = 768):
    collections = client.get_collections()
    if not any(c.name == collection_name for c in collections.collections):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

def run_ingestion_pipeline(
    tenant_id: str,
    title: str,
    roles: list,
    source_type: str,
    source_uri: str,
    preloaded_text: str | None = None,
):
    # 1. Load document
    docs = []
    text_content = ""
    
    try:
        if preloaded_text is not None:
            text_content = preloaded_text
        elif source_type == 'url':
            response = requests.get(source_uri, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            text_content = soup.get_text(separator=' ', strip=True)

        elif source_type == 'file' and source_uri.lower().endswith('.pdf'):
            reader = PdfReader(source_uri)
            for page in reader.pages:
                text_content += (page.extract_text() or '') + "\n"

        else:  # plain text file assumption
            with open(source_uri, 'r', encoding='utf-8', errors='ignore') as f:
                text_content = f.read()

        docs.append(Document(page_content=text_content, metadata={"source": source_uri}))
    except Exception as e:
        print(f"Error loading document {source_uri}: {e}")
        return 0

    source_reference = _build_source_reference(source_type, source_uri)
    ingested_at = datetime.now(timezone.utc).isoformat()
    effective_at = _extract_effective_date(text_content)
    source_trust = _source_trust_score(source_type, source_uri)
    roles_signature = _roles_signature(roles)
    content_hash = _hash_text(text_content)

    qclient = init_qdrant_client()
    collection_name = "rag_chunks"
    ensure_collection(qclient, collection_name, vector_size=get_embedding_dimension())

    if _is_duplicate_for_tenant_role(qclient, collection_name, tenant_id, content_hash):
        merged = _merge_roles_for_existing_content(
            qclient,
            collection_name,
            tenant_id,
            content_hash,
            roles,
        )
        print(
            f"[INGESTION] Duplicate skipped for tenant={tenant_id}, title={title}; "
            f"role visibility updated on {merged} chunks"
        )
        return 0

    # 2. Split into chunks
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = text_splitter.split_documents(docs)

    # 3. Add metadata (Multi-tenant & Role-based)
    doc_id = str(uuid.uuid4())
    for chunk in chunks:
        chunk.metadata.update({
            "tenant_id": tenant_id,
            "roles": roles,
            "doc_id": doc_id,
            "title": title,
            "source": source_reference,
            "ingested_at": ingested_at,
            "effective_at": effective_at,
            "source_type": source_type,
            "source_trust": source_trust,
            "roles_signature": roles_signature,
            "content_hash": content_hash,
        })

    # 4. Generate embeddings through the configured gateway and upsert to Qdrant.
    embeddings = get_embeddings()
    
    # LangChain Qdrant integration
    from langchain_community.vectorstores import Qdrant
    Qdrant.from_documents(
        chunks,
        embeddings,
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT,
        collection_name=collection_name,
        force_recreate=False
    )

    return len(chunks)


def crawl_url_content(seed_url: str, crawl_options: dict | None = None) -> tuple[list[Document], dict]:
    options = crawl_options or {}
    crawl_mode = options.get('crawl_mode', 'single_page')
    include_pdfs = bool(options.get('include_pdfs', True))
    obey_robots_txt = bool(options.get('obey_robots_txt', True))
    max_depth = int(options.get('max_depth', 2))
    max_pages = int(options.get('max_pages', 200))
    max_pdfs = int(options.get('max_pdfs', 100))
    max_pdf_size_mb = int(options.get('max_pdf_size_mb', 20))
    requests_per_second = max(int(options.get('requests_per_second', 2)), 1)

    docs: list[Document] = []
    failures = []
    visited = set()
    pdf_links = set()
    robots_cache = {}

    normalized_seed = _normalize_url(seed_url)
    queue = deque([(normalized_seed, 0)])
    if crawl_mode == 'full_site':
        for sitemap_url in _discover_sitemap_urls(normalized_seed, max_pages=max_pages):
            normalized = _normalize_url(sitemap_url)
            if normalized and _same_domain(normalized_seed, normalized):
                queue.append((normalized, 1))

    while queue and len(visited) < max_pages:
        current_url, depth = queue.popleft()
        if current_url in visited:
            continue
        if depth > max_depth:
            continue
        if not _allowed_by_robots(current_url, obey_robots_txt, robots_cache):
            continue

        try:
            res = requests.get(current_url, timeout=15)
            res.raise_for_status()
            time.sleep(1.0 / requests_per_second)
            content_type = (res.headers.get('content-type') or '').lower()

            if 'application/pdf' in content_type or current_url.lower().endswith('.pdf'):
                if include_pdfs and len(pdf_links) < max_pdfs:
                    pdf_links.add(current_url)
                visited.add(current_url)
                continue

            soup = BeautifulSoup(res.content, 'html.parser')
            text = soup.get_text(separator=' ', strip=True)
            if text:
                docs.append(Document(page_content=text, metadata={'source': current_url}))
            visited.add(current_url)

            if crawl_mode == 'single_page':
                continue

            for anchor in soup.find_all('a', href=True):
                href = _normalize_url(urljoin(current_url, anchor.get('href', '')))
                if not href:
                    continue
                if urlparse(href).scheme not in {'http', 'https'}:
                    continue
                if not _same_domain(normalized_seed, href):
                    continue

                if href.lower().endswith('.pdf'):
                    if include_pdfs and len(pdf_links) < max_pdfs:
                        pdf_links.add(href)
                    continue

                if crawl_mode == 'section_recursive':
                    seed_path = (urlparse(normalized_seed).path or '/').rstrip('/')
                    href_path = (urlparse(href).path or '/').rstrip('/')
                    if seed_path and not href_path.startswith(seed_path):
                        continue

                if href not in visited:
                    queue.append((href, depth + 1))
        except Exception as exc:
            failures.append(f"{current_url}: {exc}")

    for pdf_url in list(pdf_links)[:max_pdfs]:
        try:
            if not _allowed_by_robots(pdf_url, obey_robots_txt, robots_cache):
                continue
            pdf_res = requests.get(pdf_url, timeout=20)
            pdf_res.raise_for_status()
            time.sleep(1.0 / requests_per_second)
            if int(pdf_res.headers.get('content-length', 0) or 0) > max_pdf_size_mb * 1024 * 1024:
                failures.append(f"{pdf_url}: skipped because PDF exceeds size limit")
                continue
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                tmp.write(pdf_res.content)
                tmp_path = tmp.name
            reader = PdfReader(tmp_path)
            pdf_text = "\n".join((page.extract_text() or '') for page in reader.pages).strip()
            os.unlink(tmp_path)
            if pdf_text:
                docs.append(Document(page_content=pdf_text, metadata={'source': pdf_url}))
        except Exception as exc:
            failures.append(f"{pdf_url}: {exc}")

    return docs, {
        'pages_visited': len(visited),
        'pdf_links_found': len(pdf_links),
        'documents_extracted': len(docs),
        'failures': failures,
    }


def run_multi_url_ingestion(
    tenant_id: str,
    title: str,
    roles: list,
    source_uris: list[str],
    crawl_options: dict | None = None,
) -> dict:
    total_chunks = 0
    source_reports = []

    for source_uri in source_uris:
        docs, report = crawl_url_content(source_uri, crawl_options=crawl_options)
        if not docs:
            source_reports.append({'source_uri': source_uri, 'chunks': 0, 'report': report})
            continue

        chunks_total_for_source = 0
        for idx, doc in enumerate(docs, start=1):
            doc_title = f"{title} [{idx}]"
            source_ref = (doc.metadata or {}).get('source') or source_uri
            ingested = run_ingestion_pipeline(
                tenant_id=tenant_id,
                title=doc_title,
                roles=roles,
                source_type='url' if source_ref.startswith('http') else 'file',
                source_uri=source_ref if source_ref.startswith('http') else source_uri,
                preloaded_text=doc.page_content,
            )
            chunks_total_for_source += int(ingested or 0)

        total_chunks += chunks_total_for_source
        source_reports.append({'source_uri': source_uri, 'chunks': chunks_total_for_source, 'report': report})

    return {
        'total_chunks': total_chunks,
        'sources': source_reports,
    }
