"""Stage 4 generation: build final mindmap tree from retrieval context."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings

MINDMAP_TREE_JSON_SCHEMA: dict[str, Any] = {
    "name": "mindmap_tree_generation",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "type": {"type": "string", "enum": ["root", "theme", "insight", "action"]},
            "children": {"type": "array", "items": {"$ref": "#/$defs/node"}},
        },
        "required": ["title", "summary", "type", "children"],
        "$defs": {
            "node": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "type": {"type": "string", "enum": ["theme", "insight", "action"]},
                    "children": {"type": "array", "items": {"$ref": "#/$defs/node"}},
                },
                "required": ["title", "summary", "type", "children"],
            }
        },
    },
}


class Stage4GenerationError(RuntimeError):
    """Non-retryable generation error."""


def _fallback_title(node_type: str, *, allow_root: bool) -> str:
    if allow_root or node_type == "root":
        return "Strategic Mindmap"
    if node_type == "theme":
        return "Strategic Theme"
    if node_type == "insight":
        return "Key Insight"
    if node_type == "action":
        return "Recommended Action"
    return "Untitled Node"


def _fallback_summary(node_type: str) -> str:
    if node_type == "action":
        return "Insufficient evidence from retrieved context."
    if node_type == "insight":
        return "Derived from available context with limited detail."
    if node_type == "theme":
        return "Theme synthesized from retrieved context."
    return "Strategic structure generated from retrieved context."


def _strip_json_fence(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


def _with_network_retry(fn):
    return retry(
        reraise=True,
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError, httpx.ReadError)),
    )(fn)


def _validate_tree_node(
    node: Any,
    *,
    allow_root: bool = False,
    parent_type: str | None = None,
) -> dict[str, Any]:
    if not isinstance(node, dict):
        raise Stage4GenerationError("mindmap tree node must be an object")
    node_type = str(node.get("type") or "").strip()
    children = node.get("children") or []
    if not isinstance(children, list):
        raise Stage4GenerationError("mindmap tree node.children must be an array")
    if allow_root:
        allowed = {"root"}
    elif parent_type == "root":
        allowed = {"theme"}
    elif parent_type == "theme":
        allowed = {"insight"}
    elif parent_type == "insight":
        allowed = {"action"}
    elif parent_type == "action":
        allowed = set()
    else:
        allowed = {"theme", "insight", "action"}
    if node_type not in allowed:
        raise Stage4GenerationError(f"invalid node type {node_type!r}, allowed={sorted(allowed)}")

    # Enforce hierarchy size constraints from prompt contract.
    child_count = len(children)
    if allow_root:
        if child_count < 4 or child_count > 6:
            raise Stage4GenerationError("root must have 4-6 theme children")
    elif node_type == "theme":
        if child_count < 2 or child_count > 4:
            raise Stage4GenerationError("theme must have 2-4 insight children")
    elif node_type == "insight":
        if child_count < 1 or child_count > 3:
            raise Stage4GenerationError("insight must have 1-3 action children")
    elif node_type == "action":
        if child_count != 0:
            raise Stage4GenerationError("action must not have children")

    title = str(node.get("title") or "").strip() or _fallback_title(node_type, allow_root=allow_root)
    summary = str(node.get("summary") or "").strip() or _fallback_summary(node_type)
    return {
        "title": title,
        "summary": summary,
        "type": node_type,
        "children": [
            _validate_tree_node(c, parent_type=node_type) for c in children
        ],
    }


def _parse_generation_json(content: str) -> dict[str, Any]:
    raw = _strip_json_fence(content)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise Stage4GenerationError(f"invalid generation JSON at line {e.lineno} col {e.colno}: {e.msg}") from e
    return _validate_tree_node(data, allow_root=True)


def _normalize_text_for_key(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _dedupe_selected_context(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate by normalized title+text and keep highest-score item."""
    best_by_key: dict[str, dict[str, Any]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        text = str(item.get("text") or "").strip()
        key = _normalize_text_for_key(f"{title} {text}")
        if not key:
            continue
        score = float(item.get("final_score") or 0.0)
        prev = best_by_key.get(key)
        if prev is None or float(prev.get("final_score") or 0.0) < score:
            best_by_key[key] = item
    out = list(best_by_key.values())
    out.sort(key=lambda x: float(x.get("final_score") or 0.0), reverse=True)
    return out


def _sample_diverse_context(
    rows: list[dict[str, Any]],
    *,
    framework_tag: str,
    max_items: int,
) -> list[dict[str, Any]]:
    if max_items <= 0:
        return []
    if framework_tag != "SWOT":
        return rows[:max_items]

    buckets: dict[str, list[dict[str, Any]]] = {
        "Strength": [],
        "Weakness": [],
        "Opportunity": [],
        "Threat": [],
        "N_A": [],
    }
    for item in rows:
        swot = str(item.get("swot_category") or "N_A").strip()
        if swot not in buckets:
            swot = "N_A"
        buckets[swot].append(item)

    for key in buckets:
        buckets[key].sort(key=lambda x: float(x.get("final_score") or 0.0), reverse=True)

    # Pull up to 2 items from each SWOT bucket first.
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    ordered_buckets = ("Strength", "Weakness", "Opportunity", "Threat")
    for bucket in ordered_buckets:
        for item in buckets[bucket][:2]:
            cid = str(item.get("candidate_id") or "")
            if cid and cid not in seen and len(selected) < max_items:
                selected.append(item)
                seen.add(cid)

    # Fill remaining slots by global score.
    for item in rows:
        if len(selected) >= max_items:
            break
        cid = str(item.get("candidate_id") or "")
        if cid and cid in seen:
            continue
        selected.append(item)
        if cid:
            seen.add(cid)
    return selected[:max_items]


def _context_lines(
    retrieval_context: dict[str, Any],
    *,
    framework_tag: str,
    max_items: int = 12,
    text_limit: int = 360,
) -> list[str]:
    rows_raw = retrieval_context.get("selected_context") or []
    rows = [x for x in rows_raw if isinstance(x, dict)]
    rows = _dedupe_selected_context(rows)
    rows = _sample_diverse_context(rows, framework_tag=framework_tag, max_items=max_items)

    out: list[str] = []
    for i, item in enumerate(rows, start=1):
        title = str(item.get("title") or "").strip()
        text = str(item.get("text") or "").strip()
        if text_limit > 0:
            text = text[:text_limit]
        swot = str(item.get("swot_category") or "N_A").strip() or "N_A"
        funnel = str(item.get("funnel_stage") or "Unknown").strip() or "Unknown"
        score = float(item.get("final_score") or 0.0)
        line = f"[{i}] title={title}; swot={swot}; funnel={funnel}; score={score:.4f}; text={text}"
        out.append(line)
    return out


def _system_prompt(framework_tag: str) -> str:
    _ = framework_tag
    return (
        "You are a senior strategy synthesis engine.\n"
        "Your task is to generate ONE evidence-grounded business mindmap JSON from multi-cluster analyses.\n\n"
        "PRIMARY GOAL\n"
        "- Build a strategic mindmap that reflects the provided analyses faithfully.\n"
        "- Prioritize: fidelity to evidence, cross-cluster synthesis, and actionability.\n\n"
        "NON-NEGOTIABLE RULES\n"
        "1) Use ONLY information present in the input data.\n"
        "2) Do NOT invent facts, numbers, client names, competitors, certifications, or market claims.\n"
        "3) If evidence is weak/conflicting, explicitly write: 'Insufficient evidence from provided analyses.'\n"
        "4) Avoid duplicate nodes; merge semantically overlapping points.\n"
        "5) Keep hierarchy balanced and concise.\n\n"
        "TREE REQUIREMENTS\n"
        "- Root node type must be 'root' with 4-6 theme children.\n"
        "- Theme nodes type='theme', each with 2-4 insight children.\n"
        "- Insight nodes type='insight', each with 1-3 action children.\n"
        "- Action nodes type='action' and children must be empty.\n\n"
        "NODE WRITING RULES\n"
        "- title: 3-8 words, specific business language.\n"
        "- summary: exactly 1 sentence, <= 30 words.\n"
        "- Action summaries should start with a verb.\n\n"
        "COVERAGE CONSTRAINT\n"
        "- Cover signals from SWOT, DeepDive, Compare, RootCause, ProsCons when available.\n"
        "- Do not create one theme per framework; synthesize them into strategic themes.\n\n"
        "OUTPUT FORMAT\n"
        "- Return JSON only, no markdown, no extra commentary.\n"
        "- Root type must be 'root'. Allowed node types: root/theme/insight/action.\n"
        "- No extra keys outside schema."
    )


def _user_prompt(retrieval_context: dict[str, Any]) -> str:
    query = str(retrieval_context.get("query") or "").strip()
    framework_tag = str(retrieval_context.get("framework_tag") or "SWOT").strip()
    lines = _context_lines(retrieval_context, framework_tag=framework_tag)
    if not lines:
        raise Stage4GenerationError("selected_context is empty; cannot generate stage 4 tree")
    return (
        "Build a strategic mindmap from the provided context.\n\n"
        f"Context query: {query}\n"
        f"Context framework tag: {framework_tag}\n\n"
        "Retrieved context candidates:\n"
        + "\n".join(lines)
        + "\n\nInstructions:\n"
        + "1) Synthesize across clusters and perspectives, avoid mechanical item-by-item restatement.\n"
        + "2) Identify high-impact strategic themes that recur or materially influence decisions.\n"
        + "3) Convert themes into concrete insights and executable actions.\n"
        + "4) If a point is under-evidenced, write: 'Insufficient evidence from provided analyses.'\n"
        + "5) Return only one JSON tree following the schema."
    )


def _user_prompt_from_analyses(analyses_doc: dict[str, Any]) -> str:
    clusters = analyses_doc.get("clusters") or {}
    if not isinstance(clusters, dict) or not clusters:
        raise Stage4GenerationError("framework analyses input has no clusters")
    lines: list[str] = []
    for cluster_id, payload in clusters.items():
        if not isinstance(payload, dict):
            continue
        title = str(payload.get("cluster_title") or cluster_id).strip()
        synth = payload.get("cross_framework_synthesis") or {}
        if not isinstance(synth, dict):
            synth = {}
        priorities = synth.get("top_3_priorities") or []
        if not isinstance(priorities, list):
            priorities = []
        biggest_risk = str(synth.get("biggest_risk") or "").strip()
        next_action = str(synth.get("next_best_action") or "").strip()

        lines.append(f"[Cluster] id={cluster_id}; title={title}")
        for p in priorities[:3]:
            lines.append(f"  - priority: {str(p).strip()}")
        if biggest_risk:
            lines.append(f"  - risk: {biggest_risk}")
        if next_action:
            lines.append(f"  - next_action: {next_action}")

        fa = payload.get("framework_analyses") or {}
        if isinstance(fa, dict):
            for fw_name in ("SWOT", "DeepDive", "Compare", "RootCause", "ProsCons"):
                fw = fa.get(fw_name) or {}
                if isinstance(fw, dict):
                    summary = str(fw.get("summary") or "").strip()
                    if summary:
                        lines.append(f"  - {fw_name}.summary: {summary}")
    if not lines:
        raise Stage4GenerationError("framework analyses input has no usable content")
    return (
        "Build a strategic mindmap from multi-cluster framework analyses.\n\n"
        f"Cluster count: {len(clusters)}\n"
        "Frameworks covered per cluster: SWOT, DeepDive, Compare, RootCause, ProsCons\n\n"
        "Data:\n"
        + "\n".join(lines)
        + "\n\nInstructions:\n"
        + "1) Synthesize across clusters and frameworks (not cluster-by-cluster restatement).\n"
        + "2) Create 4-6 strategic themes, each with 2-4 insights and 1-3 actions per insight.\n"
        + "3) Keep output evidence-grounded to provided analyses only.\n"
        + "4) If evidence is weak, use: 'Insufficient evidence from provided analyses.'\n"
        + "5) Return only one JSON tree following schema."
    )


def _generate_tree_with_repair(system: str, user_base: str, provider: str) -> dict[str, Any]:
    last_err: Exception | None = None
    tree: dict[str, Any] | None = None
    for attempt in range(2):
        user = user_base
        if attempt > 0 and last_err is not None:
            user = (
                user_base
                + "\n\nPrevious output failed strict validation:\n"
                + f"- {last_err}\n"
                + "Regenerate a COMPLETE tree that strictly satisfies:\n"
                + "- root has 4-6 theme children\n"
                + "- each theme has 2-4 insight children\n"
                + "- each insight has 1-3 action children\n"
                + "- each action has empty children array\n"
                + "Return only valid JSON in required schema."
            )
        try:
            if provider == "groq":
                raw = _with_network_retry(lambda: _chat_groq(system, user))()
            else:
                raw = _with_network_retry(lambda: _chat_openai(system, user))()
            tree = _parse_generation_json(raw)
            break
        except Stage4GenerationError as e:
            last_err = e
            continue
    if tree is None:
        raise Stage4GenerationError(f"failed strict generation after retry: {last_err}") from last_err
    return tree


def _chat_openai(system: str, user: str) -> str:
    settings = get_settings()
    if not settings.OPENAI_API_KEY:
        raise Stage4GenerationError("OPENAI_API_KEY is required for stage 4 generation (openai)")
    headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload: dict[str, Any] = {
        "model": settings.MINDMAP_LLM_MODEL,
        "temperature": settings.MINDMAP_LLM_TEMPERATURE,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_schema", "json_schema": MINDMAP_TREE_JSON_SCHEMA},
    }
    with httpx.Client(timeout=settings.HTTP_TIMEOUT) as client:
        resp = client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    if resp.status_code in (429, 500, 502, 503, 504):
        raise httpx.ReadError(f"retryable status from chat API: {resp.status_code}")
    if resp.status_code >= 400:
        raise Stage4GenerationError(f"openai chat api error {resp.status_code}: {resp.text[:400]}")
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise Stage4GenerationError("openai chat api returned no choices")
    content = (choices[0].get("message") or {}).get("content")
    if not isinstance(content, str):
        raise Stage4GenerationError("openai chat api returned empty content")
    return content


def _chat_groq(system: str, user: str) -> str:
    try:
        from groq import Groq
    except ImportError as e:  # pragma: no cover
        raise Stage4GenerationError("Install the `groq` package for stage 4 groq provider") from e

    settings = get_settings()
    key = (settings.GROQ_API_KEY or os.environ.get("GROQ_API_KEY") or "").strip()
    if not key:
        raise Stage4GenerationError("GROQ_API_KEY is required for stage 4 generation (groq)")
    client = Groq(api_key=key)
    try:
        completion = client.chat.completions.create(
            model=settings.MINDMAP_GROQ_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=settings.MINDMAP_LLM_TEMPERATURE,
            response_format={"type": "json_object"},
            timeout=settings.HTTP_TIMEOUT,
        )
    except Exception as e:
        code = getattr(e, "status_code", None)
        if code in (429, 500, 502, 503, 504):
            raise httpx.ReadError(f"retryable status from groq API: {code}") from e
        raise Stage4GenerationError(f"groq chat api error: {e}") from e
    choices = completion.choices or []
    if not choices:
        raise Stage4GenerationError("groq chat api returned no choices")
    content = choices[0].message.content if choices[0].message is not None else None
    if not isinstance(content, str):
        raise Stage4GenerationError("groq chat api returned empty content")
    return content


def generate_stage4_tree(retrieval_context: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    provider = settings.MINDMAP_TOPIC_PROVIDER.strip().lower()
    framework_tag = str(retrieval_context.get("framework_tag") or "SWOT").strip()
    system = _system_prompt(framework_tag)
    user_base = _user_prompt(retrieval_context)
    tree = _generate_tree_with_repair(system, user_base, provider)
    return {
        "schema_version": 1,
        "flow_mode": "business_strategy",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": provider,
        "model": settings.MINDMAP_GROQ_MODEL if provider == "groq" else settings.MINDMAP_LLM_MODEL,
        "framework_tag": framework_tag or "SWOT",
        "query": retrieval_context.get("query") or "",
        "tree": tree,
    }


def generate_stage4_tree_from_analyses(analyses_doc: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    provider = settings.MINDMAP_TOPIC_PROVIDER.strip().lower()
    system = _system_prompt("SYNTHESIS")
    user_base = _user_prompt_from_analyses(analyses_doc)
    tree = _generate_tree_with_repair(system, user_base, provider)
    return {
        "schema_version": 1,
        "flow_mode": "business_strategy",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": provider,
        "model": settings.MINDMAP_GROQ_MODEL if provider == "groq" else settings.MINDMAP_LLM_MODEL,
        "framework_tag": "SYNTHESIS",
        "query": "overview synthesis from framework analyses",
        "tree": tree,
    }


def generate_stage4_from_file(
    retrieval_context_path: str | Path,
    *,
    output_path: str | Path | None = None,
) -> Path:
    in_path = Path(retrieval_context_path).resolve()
    retrieval_context = json.loads(in_path.read_text(encoding="utf-8"))
    generated = generate_stage4_tree(retrieval_context)
    out_path = Path(output_path).resolve() if output_path else in_path.parent / "mindmap_generated.json"
    out_path.write_text(json.dumps(generated, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def generate_stage4_from_analyses_file(
    analyses_path: str | Path,
    *,
    output_path: str | Path | None = None,
) -> Path:
    in_path = Path(analyses_path).resolve()
    analyses_doc = json.loads(in_path.read_text(encoding="utf-8"))
    generated = generate_stage4_tree_from_analyses(analyses_doc)
    out_path = Path(output_path).resolve() if output_path else in_path.parent / "mindmap_generated.json"
    out_path.write_text(json.dumps(generated, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def _tree_node_to_markdown_lines(node: dict[str, Any], *, depth: int = 0) -> list[str]:
    indent = "  " * depth
    title = str(node.get("title") or "").strip()
    summary = str(node.get("summary") or "").strip()
    node_type = str(node.get("type") or "").strip()
    line = f"{indent}- **{title}** ({node_type})"
    if summary:
        line += f": {summary}"
    lines = [line]
    for child in node.get("children") or []:
        if isinstance(child, dict):
            lines.extend(_tree_node_to_markdown_lines(child, depth=depth + 1))
    return lines


def stage4_json_to_markdown(stage4_payload: dict[str, Any]) -> str:
    tree = stage4_payload.get("tree")
    if not isinstance(tree, dict):
        raise Stage4GenerationError("stage4 payload must include object field 'tree'")
    framework = str(stage4_payload.get("framework_tag") or "SWOT").strip()
    query = str(stage4_payload.get("query") or "").strip()
    lines = [
        "# Mindmap Generated",
        "",
        f"- Framework: `{framework}`",
        f"- Query: {query}",
        "",
        "## Outline",
    ]
    lines.extend(_tree_node_to_markdown_lines(tree))
    return "\n".join(lines).rstrip() + "\n"


def stage4_json_file_to_markdown_file(
    stage4_json_path: str | Path,
    *,
    output_path: str | Path | None = None,
) -> Path:
    in_path = Path(stage4_json_path).resolve()
    payload = json.loads(in_path.read_text(encoding="utf-8"))
    md_text = stage4_json_to_markdown(payload)
    out_path = Path(output_path).resolve() if output_path else in_path.with_suffix(".md")
    out_path.write_text(md_text, encoding="utf-8")
    return out_path

