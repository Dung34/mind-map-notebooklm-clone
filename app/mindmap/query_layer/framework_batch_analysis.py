"""LLM analysis for all 5 frameworks per cluster (one call per cluster)."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings

_REQUIRED_FRAMEWORKS = ("SWOT", "DeepDive", "Compare", "RootCause", "ProsCons")


def _with_network_retry(fn):
    return retry(
        reraise=True,
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError, httpx.ReadError)),
    )(fn)


def _find_latest_artifact_root(output_dir: str | Path, website: str | None = None) -> Path:
    base = Path(output_dir).resolve()
    if website:
        candidates = sorted((base / website / "mindmap").glob("mm_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    else:
        candidates = sorted(base.glob("*/mindmap/mm_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for c in candidates:
        if (c / "retrieval_context.json").exists():
            return c
    raise FileNotFoundError("No artifact run with retrieval_context.json found in output directory.")


def _normalize_json(content: str) -> dict[str, Any]:
    raw = content.strip()
    if raw.startswith("```"):
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("LLM output must be a JSON object.")
    fa = data.get("framework_analyses")
    if not isinstance(fa, dict):
        raise ValueError("Missing framework_analyses object.")
    for key in _REQUIRED_FRAMEWORKS:
        if key not in fa:
            raise ValueError(f"Missing framework: {key}")
    return data


def _system_prompt() -> str:
    return (
        "You are a senior Strategy Analyst specialized in evidence-grounded synthesis.\n"
        "You analyze ONE content cluster and must return ALL 5 frameworks in ONE JSON object.\n\n"
        "NON-NEGOTIABLE RULES\n"
        "1) Output JSON only. No markdown. No prose outside JSON.\n"
        "2) Use ONLY provided snippets and cluster metadata.\n"
        "3) Do NOT invent facts, numbers, competitor names, client names, certifications, or pricing.\n"
        "4) Every analytical item MUST contain:\n"
        "   - a concrete point/cause/signal/action\n"
        "   - snippet-grounded evidence citing snippet ids like [REP_1], [COV_2]\n"
        "   - confidence in [0,1]\n"
        "5) If evidence is weak, explicitly write: \"Insufficient evidence from retrieved context\"\n"
        "   and set confidence <= 0.40.\n"
        "6) Avoid generic statements unless directly evidenced.\n"
        "7) Keep each list concise: 2-4 items preferred.\n"
        "8) Summaries must be exactly 1 sentence, <= 30 words.\n\n"
        "QUALITY BAR\n"
        "- Good output is specific, evidenced, and decision-useful.\n"
        "- Bad output is vague, generic, or not traceable to snippet ids.\n"
        "- If no direct proof exists, state uncertainty explicitly instead of guessing.\n\n"
        "STRICT OUTPUT REQUIREMENTS\n"
        "- Include ALL frameworks in framework_analyses: SWOT, DeepDive, Compare, RootCause, ProsCons.\n"
        "- confidence values must be numeric in [0,1].\n"
        "- Evidence fields must reference at least one snippet id [REP_x] or [COV_x].\n"
        "- No extra top-level keys."
    )


def _user_prompt(cluster_id: str, cluster_title: str, cluster_summary: str, rep: list[str], cov: list[str]) -> str:
    rep_lines = [f"[REP_{i}] {s}" for i, s in enumerate(rep, start=1)]
    cov_lines = [f"[COV_{i}] {s}" for i, s in enumerate(cov, start=1)]
    return (
        "Analyze the following ONE cluster and return exactly ONE JSON object.\n\n"
        f"cluster_id: {cluster_id}\n"
        f"cluster_title: {cluster_title}\n"
        f"cluster_summary: {cluster_summary}\n\n"
        "REPRESENTATIVE_SNIPPETS\n"
        + ("\n".join(rep_lines) if rep_lines else "(none)")
        + "\n\nCOVERAGE_SNIPPETS\n"
        + ("\n".join(cov_lines) if cov_lines else "(none)")
        + "\n\nRequired output shape:\n"
        "{\n"
        '  "cluster_id": "string",\n'
        '  "cluster_title": "string",\n'
        '  "framework_analyses": {\n'
        '    "SWOT": {"strengths":[],"weaknesses":[],"opportunities":[],"threats":[],"summary":"string"},\n'
        '    "DeepDive": {"core_theme":"string","key_drivers":[],"implications":[],"recommended_focus":[],"summary":"string"},\n'
        '    "Compare": {"comparison_basis":[],"advantages_vs_market":[],"gaps_vs_market":[],"positioning_statement":"string","summary":"string"},\n'
        '    "RootCause": {"observed_signals":[],"likely_root_causes":[],"validation_checks":[],"summary":"string"},\n'
        '    "ProsCons": {"pros":[],"cons":[],"tradeoffs":[],"summary":"string"}\n'
        "  },\n"
        '  "cross_framework_synthesis": {"top_3_priorities":[],"biggest_risk":"string","next_best_action":"string"}\n'
        "}\n"
        "Do not add other top-level keys."
    )


def _chat_openai(system: str, user: str) -> str:
    settings = get_settings()
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is required for OpenAI provider")
    headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload: dict[str, Any] = {
        "model": settings.MINDMAP_LLM_MODEL,
        "temperature": settings.MINDMAP_LLM_TEMPERATURE,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
    }
    with httpx.Client(timeout=settings.HTTP_TIMEOUT) as client:
        resp = client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    if resp.status_code in (429, 500, 502, 503, 504):
        raise httpx.ReadError(f"retryable status from chat API: {resp.status_code}")
    if resp.status_code >= 400:
        raise RuntimeError(f"openai error {resp.status_code}: {resp.text[:400]}")
    data = resp.json()
    choices = data.get("choices") or []
    content = (choices[0].get("message") or {}).get("content") if choices else None
    if not isinstance(content, str):
        raise RuntimeError("OpenAI returned empty content")
    return content


def _chat_groq(system: str, user: str) -> str:
    try:
        from groq import Groq
    except ImportError as e:  # pragma: no cover
        raise ImportError("Install `groq` package to use Groq provider") from e
    settings = get_settings()
    key = (settings.GROQ_API_KEY or os.environ.get("GROQ_API_KEY") or "").strip()
    if not key:
        raise ValueError("GROQ_API_KEY is required for Groq provider")
    client = Groq(api_key=key)
    try:
        completion = client.chat.completions.create(
            model=settings.MINDMAP_GROQ_MODEL,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=settings.MINDMAP_LLM_TEMPERATURE,
            response_format={"type": "json_object"},
            timeout=settings.HTTP_TIMEOUT,
        )
    except Exception as e:
        code = getattr(e, "status_code", None)
        if code in (429, 500, 502, 503, 504):
            raise httpx.ReadError(f"retryable status from groq API: {code}") from e
        raise
    choices = completion.choices or []
    content = choices[0].message.content if choices and choices[0].message is not None else None
    if not isinstance(content, str):
        raise RuntimeError("Groq returned empty content")
    return content


def _call_llm(system: str, user: str) -> dict[str, Any]:
    provider = get_settings().MINDMAP_TOPIC_PROVIDER.strip().lower()
    if provider == "groq":
        content = _with_network_retry(lambda: _chat_groq(system, user))()
    else:
        content = _with_network_retry(lambda: _chat_openai(system, user))()
    return _normalize_json(content)


def _group_cluster_context(retrieval_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = defaultdict(lambda: {"title": "", "summary": "", "rep": [], "cov": []})
    for row in retrieval_payload.get("selected_context") or []:
        if not isinstance(row, dict):
            continue
        cluster_id = str(row.get("source_ref") or "").strip()
        if not cluster_id:
            continue
        bucket = out[cluster_id]
        bucket["title"] = str(row.get("title") or bucket["title"] or cluster_id).strip()
        text = str(row.get("text") or "").strip()
        if not bucket["summary"] and text:
            bucket["summary"] = text[:200]
        tag = str(row.get("framework_tag") or "").strip().lower()
        if tag == "representative":
            bucket["rep"].append(text)
        else:
            bucket["cov"].append(text)
    return out


def generate_overview_framework_analyses(
    artifact_root: str | Path,
    *,
    output_path: str | Path | None = None,
) -> Path:
    root = Path(artifact_root).resolve()
    retrieval_path = root / "retrieval_context.json"
    payload = json.loads(retrieval_path.read_text(encoding="utf-8"))
    clusters = _group_cluster_context(payload)

    system = _system_prompt()
    analyses: dict[str, Any] = {}
    for cluster_id, ctx in clusters.items():
        user = _user_prompt(
            cluster_id=cluster_id,
            cluster_title=str(ctx.get("title") or cluster_id),
            cluster_summary=str(ctx.get("summary") or ""),
            rep=[s for s in ctx.get("rep") or [] if s][:5],
            cov=[s for s in ctx.get("cov") or [] if s][:5],
        )
        analyses[cluster_id] = _call_llm(system, user)

    settings = get_settings()
    provider = settings.MINDMAP_TOPIC_PROVIDER.strip().lower()
    model = settings.MINDMAP_GROQ_MODEL if provider == "groq" else settings.MINDMAP_LLM_MODEL
    out_doc = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "artifact_root": str(root),
        "provider": provider,
        "model": model,
        "cluster_count": len(analyses),
        "frameworks": list(_REQUIRED_FRAMEWORKS),
        "clusters": analyses,
    }
    out = Path(output_path).resolve() if output_path else root / "framework_analyses_overview.json"
    out.write_text(json.dumps(out_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def generate_overview_framework_analyses_for_latest(
    *,
    output_dir: str | Path | None = None,
    website: str | None = None,
    output_path: str | Path | None = None,
) -> Path:
    settings = get_settings()
    base_out = Path(output_dir).resolve() if output_dir else Path(settings.OUTPUT_DIR).resolve()
    latest_root = _find_latest_artifact_root(base_out, website=website)
    return generate_overview_framework_analyses(latest_root, output_path=output_path)

