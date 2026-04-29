"""Phase 9 B3: ingest API + job status + dry-run."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.discover.firecrawl_map import discover_from_seeds
from app.embed.openai_embedding_service import EmbeddingItem, OpenAIEmbeddingService
from app.models import Chunk
from app.pipeline import output_dir_slug, run_pipeline
from app.search.perplexity_search import build_seed_urls
from app.vector.pgvector_repository import PgVectorRepository, VectorRecord

app = FastAPI(title="CleanerRawData API", version="0.1.0")
logger = logging.getLogger(__name__)

JobStatus = Literal["queued", "running", "success", "failed"]
JOBS: dict[str, dict[str, Any]] = {}


def _debug_log(run_id: str, hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
    payload = {
        "sessionId": "72e706",
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    try:
        with Path("debug-72e706.log").open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


class IngestRequest(BaseModel):
    company: str | None = None
    website: str | None = None
    notebooklm_id: str | None = None
    manual_seeds: list[str] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=200)
    no_search: bool = False
    include_subdomains: bool | None = None
    map_limit: int | None = Field(default=None, ge=1)
    dry_run: bool = False


class ReindexRequest(BaseModel):
    website: str
    notebooklm_id: str | None = None
    limit: int = Field(default=0, ge=0)


class ApiError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, detail: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}


def _new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]


def _set_job(run_id: str, **kwargs: Any) -> None:
    if run_id not in JOBS:
        JOBS[run_id] = {
            "run_id": run_id,
            "status": "queued",
            "stage": "created",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "error": None,
            "result": None,
        }
    JOBS[run_id].update(kwargs)
    JOBS[run_id]["updated_at"] = datetime.now(timezone.utc).isoformat()


def _db_connect():
    settings = get_settings()
    dsn = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(dsn, autocommit=False)


def _db_upsert_ingest_run(
    run_id: str,
    *,
    company: str | None,
    website: str | None,
    notebooklm_id: str,
    status: str,
    total_urls: int = 0,
    processed_urls: int = 0,
    error_message: str | None = None,
    finished: bool = False,
) -> None:
    # region agent log
    _debug_log(
        run_id=run_id,
        hypothesis_id="H1",
        location="app/main.py:_db_upsert_ingest_run:pre_execute",
        message="About to upsert ingest_runs row",
        data={
            "status": status,
            "company_present": bool(company),
            "website_present": bool(website),
            "notebooklm_id_present": bool(notebooklm_id),
            "total_urls": total_urls,
            "processed_urls": processed_urls,
            "finished": finished,
        },
    )
    # endregion
    with _db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ingest_runs
            (run_id, company, website, notebooklm_id, status, total_urls, processed_urls, error_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id) DO UPDATE SET
                company = EXCLUDED.company,
                website = EXCLUDED.website,
                notebooklm_id = EXCLUDED.notebooklm_id,
                status = EXCLUDED.status,
                total_urls = EXCLUDED.total_urls,
                processed_urls = EXCLUDED.processed_urls,
                error_message = EXCLUDED.error_message,
                finished_at = CASE WHEN %s THEN NOW() ELSE ingest_runs.finished_at END;
            """,
            (
                run_id,
                company,
                website,
                notebooklm_id,
                status,
                total_urls,
                processed_urls,
                error_message,
                finished,
            ),
        )
        conn.commit()
    # region agent log
    _debug_log(
        run_id=run_id,
        hypothesis_id="H1",
        location="app/main.py:_db_upsert_ingest_run:post_execute",
        message="Upsert ingest_runs completed",
        data={"status": status},
    )
    # endregion


def _start_stage(run_id: str, stage: str) -> None:
    _set_job(run_id, stage=stage, stage_started_at=time.perf_counter())


def _finish_stage(run_id: str, stage: str) -> None:
    job = JOBS.get(run_id, {})
    t0 = job.get("stage_started_at")
    if not isinstance(t0, (int, float)):
        return
    durations = job.get("stage_durations_seconds") or {}
    durations[stage] = round(time.perf_counter() - t0, 3)
    _set_job(run_id, stage_durations_seconds=durations)


def _output_dir_for_request(req: IngestRequest) -> Path:
    settings = get_settings()
    slug = output_dir_slug(req.company, req.website, req.manual_seeds or None)
    return Path(settings.OUTPUT_DIR) / slug


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _estimate_tokens_from_text(text: str) -> int:
    # Simple estimate for guardrails/cost summary.
    words = len(text.split())
    return max(1, math.ceil(words * 1.3))


def _estimate_tokens_from_chunks(chunks: list[Chunk]) -> int:
    return sum(_estimate_tokens_from_text(c.text) for c in chunks)


def _resolve_notebooklm_id(req: IngestRequest) -> str:
    if req.notebooklm_id and req.notebooklm_id.strip():
        return req.notebooklm_id.strip()
    base = (req.website or req.company or "default").strip().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    if not base:
        base = "default"
    return f"nb_{base}"


def _resolve_notebooklm_id_from_fields(
    *,
    notebooklm_id: str | None,
    company: str | None,
    website: str | None,
) -> str:
    if notebooklm_id and notebooklm_id.strip():
        return notebooklm_id.strip()
    base = (website or company or "default").strip().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    if not base:
        base = "default"
    return f"nb_{base}"


def _cost_summary(*, scrape_urls: int, embed_tokens: int) -> dict:
    settings = get_settings()
    scrape_est = round(scrape_urls * settings.SCRAPE_EST_COST_PER_URL_USD, 6)
    embed_est = round((embed_tokens / 1000.0) * settings.EMBED_EST_COST_PER_1K_TOKENS_USD, 6)
    return {
        "scrape_est_usd": scrape_est,
        "embed_est_usd": embed_est,
        "total_est_usd": round(scrape_est + embed_est, 6),
    }


def _enforce_ingest_guardrails(estimated_scrape_count: int) -> None:
    settings = get_settings()
    if estimated_scrape_count > settings.MAX_SCRAPE_URLS_PER_RUN:
        raise ApiError(
            code="quota_exceeded",
            message="estimated scrape urls exceeds MAX_SCRAPE_URLS_PER_RUN",
            status_code=429,
            detail={
                "estimated_scrape_count": estimated_scrape_count,
                "max_scrape_urls_per_run": settings.MAX_SCRAPE_URLS_PER_RUN,
            },
        )


def _enforce_embed_guardrails(embed_tokens: int) -> None:
    settings = get_settings()
    if embed_tokens > settings.MAX_EMBEDDING_TOKENS_PER_RUN:
        raise ApiError(
            code="quota_exceeded",
            message="estimated embedding tokens exceeds MAX_EMBEDDING_TOKENS_PER_RUN",
            status_code=429,
            detail={
                "estimated_embedding_tokens": embed_tokens,
                "max_embedding_tokens_per_run": settings.MAX_EMBEDDING_TOKENS_PER_RUN,
            },
        )


async def _run_ingest_job(run_id: str, req: IngestRequest, notebooklm_id: str) -> None:
    try:
        _db_upsert_ingest_run(
            run_id,
            company=req.company,
            website=req.website,
            notebooklm_id=notebooklm_id,
            status="running",
            total_urls=req.limit,
            processed_urls=0,
        )
        _set_job(run_id, status="running")
        _start_stage(run_id, "pipeline")
        result = await run_pipeline(
            company=req.company,
            website=req.website,
            manual_seeds=req.manual_seeds or None,
            limit=req.limit,
            no_search=req.no_search,
            include_subdomains=req.include_subdomains,
            map_limit=req.map_limit,
            write_outputs=True,
        )
        out_dir = _output_dir_for_request(req)
        stats = _read_json(out_dir / "stats.json")
        _finish_stage(run_id, "pipeline")
        scrape_selected = int(stats.get("scrape_selected_count", stats.get("scrape_target_count", 0)))
        chunks = _load_chunks_for_reindex(out_dir, limit=0)
        embed_tokens = _estimate_tokens_from_chunks(chunks)
        _enforce_embed_guardrails(embed_tokens)

        _start_stage(run_id, "embedding")
        emb = OpenAIEmbeddingService()
        emb_items = [EmbeddingItem(chunk_id=c.chunk_id, text=c.text) for c in chunks]
        emb_results = emb.embed_items(emb_items)
        _finish_stage(run_id, "embedding")
        emb_path = _write_embeddings_jsonl(out_dir, emb_results)

        _start_stage(run_id, "vector_upsert")
        by_id = {c.chunk_id: c for c in chunks}
        notebooklm_id = _resolve_notebooklm_id_from_fields(
            notebooklm_id=req.notebooklm_id,
            company=None,
            website=req.website,
        )
        records: list[VectorRecord] = []
        for e in emb_results:
            c = by_id[e.chunk_id]
            records.append(
                VectorRecord(
                    chunk_id=e.chunk_id,
                    source_url=str(c.source_url),
                    embedding_model=e.embedding_model,
                    dim=e.dim,
                    vector=e.vector,
                    metadata={
                        "page_title": c.page_title,
                        "section_heading": c.section_heading,
                        "crawled_at": c.crawled_at.isoformat(),
                        "run_id": run_id,
                    },
                    notebooklm_id=notebooklm_id,
                    chunk_text=c.text,
                )
            )
        # region agent log
        _debug_log(
            run_id=run_id,
            hypothesis_id="H5",
            location="app/main.py:_run_ingest_job:records_prepared",
            message="Prepared vector records for upsert",
            data={
                "records_count": len(records),
                "notebooklm_id": notebooklm_id,
                "first_record_has_chunk_text": bool(records and records[0].chunk_text),
                "first_record_has_notebooklm_id": bool(records and records[0].notebooklm_id),
            },
        )
        # endregion
        upserted = 0
        if records:
            repo = PgVectorRepository(vector_dim=records[0].dim)
            repo.ensure_table()
            upserted = repo.upsert_embeddings(records)
        _finish_stage(run_id, "vector_upsert")

        _db_upsert_ingest_run(
            run_id,
            company=req.company,
            website=req.website,
            notebooklm_id=notebooklm_id,
            status="success",
            total_urls=int(stats.get("scrape_target_count", req.limit)),
            processed_urls=int(stats.get("cleaned_page_count", 0)),
            finished=True,
        )
        _set_job(
            run_id,
            status="success",
            stage="done",
            result={
                "output_dir": str(out_dir),
                "stats": stats,
                "cost_summary": _cost_summary(scrape_urls=scrape_selected, embed_tokens=embed_tokens),
                "embedding": {
                    "embedded": len(emb_results),
                    "upserted": upserted,
                    "embeddings_path": str(emb_path),
                },
                "summary": {
                    "seed_urls": len(result.seeds),
                    "discovered_urls": len(result.urls),
                    "cleaned_pages": len(result.pages),
                    "chunks": len(result.chunks),
                },
            },
        )
    except Exception as exc:
        # region agent log
        _debug_log(
            run_id=run_id,
            hypothesis_id="H7",
            location="app/main.py:_run_ingest_job:exception",
            message="Ingest background job failed",
            data={"error": str(exc)},
        )
        # endregion
        logger.exception("ingest job failed run_id=%s", run_id)
        try:
            _db_upsert_ingest_run(
                run_id,
                company=req.company,
                website=req.website,
                notebooklm_id=notebooklm_id,
                status="failed",
                total_urls=req.limit,
                processed_urls=0,
                error_message=str(exc),
                finished=True,
            )
        except Exception:
            logger.exception("failed updating ingest_runs for run_id=%s", run_id)
        _set_job(run_id, status="failed", stage="failed", error=str(exc))


def _estimate_dry_run(req: IngestRequest) -> dict:
    if req.no_search:
        if not req.website:
            raise ValueError("website is required when no_search=true")
        seeds = build_seed_urls(company=None, website=req.website, manual_seeds=req.manual_seeds or None)
    else:
        seeds = build_seed_urls(
            company=req.company,
            website=req.website,
            manual_seeds=req.manual_seeds or None,
        )
    if not seeds:
        return {"seed_count": 0, "discovered_count": 0, "estimated_scrape_count": 0}
    discovered = discover_from_seeds(
        seeds,
        limit=req.map_limit,
        include_subdomains=req.include_subdomains if req.include_subdomains else None,
    )
    scrape_n = min(req.limit, len(discovered))
    _enforce_ingest_guardrails(scrape_n)
    cost = _cost_summary(scrape_urls=scrape_n, embed_tokens=0)
    return {
        "seed_count": len(seeds),
        "discovered_count": len(discovered),
        "estimated_scrape_count": scrape_n,
        "estimated_embedding_count": None,
        "cost_summary": cost,
    }


def _load_chunks_for_reindex(out_dir: Path, limit: int) -> list[Chunk]:
    chunks_path = out_dir / "chunks_delta.jsonl"
    if not chunks_path.exists() or chunks_path.stat().st_size == 0:
        chunks_path = out_dir / "chunks.jsonl"
    if not chunks_path.exists():
        return []
    rows: list[Chunk] = []
    for line in chunks_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(Chunk.model_validate_json(line))
        if limit > 0 and len(rows) >= limit:
            break
    return rows


def _write_embeddings_jsonl(out_dir: Path, emb_results: list) -> Path:
    path = out_dir / "embeddings.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for r in emb_results:
            f.write(
                json.dumps(
                    {
                        "chunk_id": r.chunk_id,
                        "embedding_model": r.embedding_model,
                        "dim": r.dim,
                        "vector": r.vector,
                        "vector_checksum": r.vector_checksum,
                        "upsert_status": r.upsert_status,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    return path


async def _run_reindex_job(run_id: str, req: ReindexRequest) -> None:
    try:
        _set_job(run_id, status="running")
        _start_stage(run_id, "reindex_load")
        settings = get_settings()
        out_dir = Path(settings.OUTPUT_DIR) / output_dir_slug(None, req.website, None)
        chunks = _load_chunks_for_reindex(out_dir, req.limit)
        if not chunks:
            raise ValueError("no chunks/chunks_delta found for reindex")
        _finish_stage(run_id, "reindex_load")

        embed_tokens = _estimate_tokens_from_chunks(chunks)
        _enforce_embed_guardrails(embed_tokens)

        _start_stage(run_id, "embedding")
        emb = OpenAIEmbeddingService()
        emb_items = [EmbeddingItem(chunk_id=c.chunk_id, text=c.text) for c in chunks]
        emb_results = emb.embed_items(emb_items)
        _finish_stage(run_id, "embedding")

        _start_stage(run_id, "vector_upsert")
        by_id = {c.chunk_id: c for c in chunks}
        records: list[VectorRecord] = []
        for e in emb_results:
            c = by_id[e.chunk_id]
            records.append(
                VectorRecord(
                    chunk_id=e.chunk_id,
                    source_url=str(c.source_url),
                    embedding_model=e.embedding_model,
                    dim=e.dim,
                    vector=e.vector,
                    metadata={
                        "page_title": c.page_title,
                        "section_heading": c.section_heading,
                        "crawled_at": c.crawled_at.isoformat(),
                        "run_id": run_id,
                    },
                    notebooklm_id=notebooklm_id,
                    chunk_text=c.text,
                )
            )
        # region agent log
        _debug_log(
            run_id=run_id,
            hypothesis_id="H6",
            location="app/main.py:_run_reindex_job:records_prepared",
            message="Prepared reindex vector records for upsert",
            data={
                "records_count": len(records),
                "notebooklm_id": notebooklm_id,
                "first_record_has_chunk_text": bool(records and records[0].chunk_text),
            },
        )
        # endregion
        repo = PgVectorRepository(vector_dim=records[0].dim if records else 1536)
        repo.ensure_table()
        upserted = repo.upsert_embeddings(records)
        _finish_stage(run_id, "vector_upsert")
        _set_job(
            run_id,
            status="success",
            stage="done",
            result={
                "website": req.website,
                "embedded": len(emb_results),
                "upserted": upserted,
                "estimated_embedding_tokens": embed_tokens,
                "cost_summary": _cost_summary(scrape_urls=0, embed_tokens=embed_tokens),
            },
        )
    except Exception as exc:
        # region agent log
        _debug_log(
            run_id=run_id,
            hypothesis_id="H7",
            location="app/main.py:_run_reindex_job:exception",
            message="Reindex background job failed",
            data={"error": str(exc)},
        )
        # endregion
        logger.exception("reindex job failed run_id=%s", run_id)
        _set_job(run_id, status="failed", stage="failed", error=str(exc))


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.exception_handler(ApiError)
async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": exc.code,
            "message": exc.message,
            "detail": exc.detail,
        },
    )


@app.post("/ingest")
async def ingest(req: IngestRequest) -> dict:
    debug_run_id = f"ingest_req_{uuid4().hex[:8]}"
    # region agent log
    _debug_log(
        run_id=debug_run_id,
        hypothesis_id="H2",
        location="app/main.py:ingest:entry",
        message="Received /ingest request",
        data={
            "dry_run": req.dry_run,
            "no_search": req.no_search,
            "has_company": bool(req.company),
            "has_website": bool(req.website),
            "manual_seeds_count": len(req.manual_seeds),
            "limit": req.limit,
        },
    )
    # endregion
    if req.no_search and not req.website:
        # region agent log
        _debug_log(
            run_id=debug_run_id,
            hypothesis_id="H2",
            location="app/main.py:ingest:validation_error",
            message="Validation failed for no_search without website",
            data={},
        )
        # endregion
        raise ApiError(
            code="validation_error",
            message="website is required when no_search=true",
            status_code=400,
        )
    if req.dry_run:
        try:
            # region agent log
            _debug_log(
                run_id=debug_run_id,
                hypothesis_id="H3",
                location="app/main.py:ingest:dry_run_estimate_start",
                message="Starting dry-run estimate",
                data={},
            )
            # endregion
            return {"dry_run": True, "estimate": _estimate_dry_run(req)}
        except ApiError:
            raise
        except Exception as exc:
            # region agent log
            _debug_log(
                run_id=debug_run_id,
                hypothesis_id="H3",
                location="app/main.py:ingest:dry_run_estimate_error",
                message="Dry-run estimate failed",
                data={"error": str(exc)},
            )
            # endregion
            raise ApiError(code="validation_error", message=str(exc), status_code=400) from exc

    payload = req.model_dump()
    payload["dry_run"] = True
    # region agent log
    _debug_log(
        run_id=debug_run_id,
        hypothesis_id="H3",
        location="app/main.py:ingest:estimate_start",
        message="Starting pre-flight estimate for non-dry-run",
        data={},
    )
    # endregion
    estimate = _estimate_dry_run(IngestRequest(**payload))
    # region agent log
    _debug_log(
        run_id=debug_run_id,
        hypothesis_id="H3",
        location="app/main.py:ingest:estimate_done",
        message="Pre-flight estimate completed",
        data={"estimated_scrape_count": int(estimate.get("estimated_scrape_count", 0))},
    )
    # endregion
    _enforce_ingest_guardrails(int(estimate.get("estimated_scrape_count", 0)))
    notebooklm_id = _resolve_notebooklm_id(req)
    # region agent log
    _debug_log(
        run_id=debug_run_id,
        hypothesis_id="H1",
        location="app/main.py:ingest:notebooklm_id_resolved",
        message="Resolved notebooklm_id for ingest run",
        data={"notebooklm_id": notebooklm_id},
    )
    # endregion

    run_id = _new_run_id()
    try:
        # region agent log
        _debug_log(
            run_id=run_id,
            hypothesis_id="H1",
            location="app/main.py:ingest:db_upsert_start",
            message="Starting queued DB upsert",
            data={},
        )
        # endregion
        _db_upsert_ingest_run(
            run_id,
            company=req.company,
            website=req.website,
            notebooklm_id=notebooklm_id,
            status="queued",
            total_urls=req.limit,
            processed_urls=0,
        )
    except Exception as exc:
        # region agent log
        _debug_log(
            run_id=run_id,
            hypothesis_id="H1",
            location="app/main.py:ingest:db_upsert_error",
            message="Queued DB upsert failed",
            data={"error": str(exc)},
        )
        # endregion
        raise ApiError(code="upstream_error", message=f"database_error: {exc}", status_code=502) from exc
    _set_job(run_id, status="queued", stage="queued", result={"mode": "ingest"})
    asyncio.create_task(_run_ingest_job(run_id, req, notebooklm_id))
    return {"run_id": run_id, "status_url": f"/jobs/{run_id}"}


@app.post("/ingest/reindex")
async def ingest_reindex(req: ReindexRequest) -> dict:
    run_id = _new_run_id()
    _set_job(run_id, status="queued", stage="queued", result={"mode": "reindex"})
    asyncio.create_task(_run_reindex_job(run_id, req))
    return {"run_id": run_id, "status_url": f"/jobs/{run_id}"}


@app.get("/jobs/{run_id}")
def job_status(run_id: str) -> dict:
    job = JOBS.get(run_id)
    if not job:
        raise HTTPException(status_code=404, detail={"error_code": "job_not_found"})
    return job

