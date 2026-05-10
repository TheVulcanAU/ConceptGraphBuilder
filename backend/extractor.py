"""
Extraction pipeline: chunk → extract per chunk → code-merge → semantic-dedup → verify.

Three-pass quality pipeline:
  1. Per-chunk LLM extraction (existing)
  2. Semantic deduplication: LLM call identifies synonymous nodes across chunks
  3. Depends-on verification: LLM call audits every depends-on edge for direction

extract_graph() returns (ConceptGraph, dedup_report, verify_report) so callers
can surface what changed rather than treating the pipeline as a black box.
"""

import json
import logging
import os
import re
from difflib import SequenceMatcher

import anthropic

from .schema import (
    ConceptGraph,
    Edge,
    EdgeType,
    ExtractionChunk,
    Node,
    NodeType,
)
from .chunker import Chunk

logger = logging.getLogger(__name__)

EXTRACTION_MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# Extraction prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert at extracting structured argument graphs from text.

You will receive a passage of text and extract:
1. NODES — the key concepts, claims, assumptions, and entities in the passage
2. EDGES — typed relationships between those nodes

NODE TYPES:
- concept: an abstract idea or principle (e.g., "emergence", "comparative advantage")
- claim: an assertion the author makes (e.g., "cities become more efficient at scale")
- assumption: something taken for granted without argument (e.g., "humans are rational actors")
- entity: a named person, place, system, or thing (e.g., "Adam Smith", "TCP/IP")

EDGE TYPES (use exactly these strings):
- supports: node A provides evidence or argument that strengthens node B
- contradicts: node A is in tension with or directly opposes node B — the two claims cannot both be true (opposing diagnoses, competing causal explanations, direct negations). A solution and the problem it addresses are NOT contradictions.
- depends-on: node A cannot be true or useful without node B being true. This includes: a prescriptive claim (solution/recommendation) depends-on the diagnostic claim (problem/cause) it addresses — the prescription is only meaningful if the diagnosis holds. Also: a conclusion depends-on the premises it rests on.
- example-of: node A is a concrete instance or illustration of node B
- defines: node A provides the meaning or boundary conditions of node B
- refines: node A is a more precise, qualified, or scoped version of node B

DEPENDS-ON GUIDANCE (this edge is commonly missed and often misdirected — read carefully):
Use depends-on when the SOURCE node cannot be true, useful, or meaningful without the TARGET node being true.

Direction-check: Before writing a depends-on edge, apply this test — "If I removed the TARGET from the argument entirely, would the SOURCE lose its meaning or truth?" If yes, SOURCE→TARGET is correct. If no, re-examine.

Common trap — reversed direction: You will sometimes correctly identify that two nodes are in a depends-on relationship but draw the arrow backwards. Warning sign: if your description reads "TARGET presupposes SOURCE" or "TARGET requires SOURCE", your arrow is backwards — swap source and target before outputting.

Good cases: a prescriptive claim (recommendation/solution) depends-on the diagnostic claim it addresses — if the diagnosis is false, the prescription is pointless. A conclusion depends-on the premises it rests on. A definition's usefulness depends-on the problem it was built to solve.

Bad cases: do NOT use depends-on just because two nodes are logically related. "A enables B to be useful" is not the same as "B depends-on A." "A motivated the search for B" is not depends-on. "A and B are both true" is not depends-on.

CONTRADICTS GUIDANCE (this edge is commonly overused — use it carefully):
Use contradicts only when two claims directly oppose each other such that both cannot be true simultaneously. Good cases: two competing causal explanations for the same phenomenon, a claim and its direct negation, two incompatible prescriptions. Bad cases: a remedy and the problem it addresses (those are related by depends-on, not contradicts), a general principle and a specific exception.

CRITICAL RULES:
1. Only extract nodes that are actually present in the text — do not infer things the text doesn't say.
2. Only draw an edge if you can quote a passage that evidences the relationship. Plausible but unsupported edges are worse than no edge.
3. Keep labels short (2-6 words). Use description for nuance.
4. Source passages must be verbatim quotes (or near-verbatim) from the chunk text provided.
5. Prefer fewer, high-confidence nodes/edges over many speculative ones.
6. Claims should capture what the author actually argues, not just what topic they discuss.
7. Assumptions are often implicit — only extract them if the argument clearly depends on an unstated premise.
8. Before finalizing your node list: check for nodes that express the same concept with different phrasings and merge them into one. Use the most precise and specific label. Do not output two nodes that mean the same thing.

OUTPUT FORMAT — respond with valid JSON only, no commentary:
{
  "nodes": [
    {
      "label": "short name",
      "type": "concept|claim|assumption|entity",
      "description": "one sentence explaining what this means in context",
      "source_passages": ["verbatim quote from text"]
    }
  ],
  "edges": [
    {
      "source_label": "label of source node",
      "target_label": "label of target node",
      "type": "supports|contradicts|depends-on|example-of|defines|refines",
      "description": "one sentence explaining why this relationship holds",
      "source_passages": ["verbatim quote evidencing this relationship"]
    }
  ]
}"""


def _build_user_message(chunk: Chunk) -> str:
    return f"CHUNK {chunk.index + 1}:\n\n{chunk.text}"


# ---------------------------------------------------------------------------
# Single-chunk extraction
# ---------------------------------------------------------------------------

def _extract_chunk(client: anthropic.Anthropic, chunk: Chunk) -> ExtractionChunk | None:
    """Call the LLM and parse/validate the result. Returns None on failure."""
    try:
        response = client.messages.create(
            model=EXTRACTION_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_message(chunk)}],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        return _validate_chunk(data, chunk.index)
    except json.JSONDecodeError as e:
        logger.warning("Chunk %d: JSON parse failed: %s", chunk.index, e)
        return None
    except anthropic.APIError as e:
        logger.error("Chunk %d: API error: %s", chunk.index, e)
        return None
    except Exception as e:
        logger.error("Chunk %d: unexpected error: %s", chunk.index, e)
        return None


def _validate_chunk(data: dict, chunk_index: int) -> ExtractionChunk | None:
    """Validate raw parsed JSON against our schema. Log and drop bad items."""
    valid_node_types = {t.value for t in NodeType}
    valid_edge_types = {t.value for t in EdgeType}

    nodes: list[Node] = []
    label_map: dict[str, str] = {}

    for raw_node in data.get("nodes", []):
        try:
            if raw_node.get("type") not in valid_node_types:
                logger.warning("Chunk %d: rejected node with unknown type: %s", chunk_index, raw_node)
                continue
            if not raw_node.get("label") or not raw_node.get("description"):
                logger.warning("Chunk %d: rejected node missing label/description", chunk_index)
                continue
            node = Node(
                label=raw_node["label"].strip(),
                type=NodeType(raw_node["type"]),
                description=raw_node["description"].strip(),
                source_passages=raw_node.get("source_passages", []),
                chunk_indices=[chunk_index],
            )
            nodes.append(node)
            label_map[node.label.lower()] = node.id
        except Exception as e:
            logger.warning("Chunk %d: node validation error: %s", chunk_index, e)

    edges: list[Edge] = []
    for raw_edge in data.get("edges", []):
        try:
            if raw_edge.get("type") not in valid_edge_types:
                logger.warning("Chunk %d: rejected edge with unknown type: %s", chunk_index, raw_edge.get("type"))
                continue
            src_label = raw_edge.get("source_label", "").strip().lower()
            tgt_label = raw_edge.get("target_label", "").strip().lower()
            src_id = label_map.get(src_label)
            tgt_id = label_map.get(tgt_label)
            if not src_id or not tgt_id:
                logger.warning("Chunk %d: edge references unknown node(s): %s → %s", chunk_index, src_label, tgt_label)
                continue
            edge = Edge(
                source_id=src_id,
                target_id=tgt_id,
                type=EdgeType(raw_edge["type"]),
                description=raw_edge.get("description", "").strip(),
                source_passages=raw_edge.get("source_passages", []),
            )
            edges.append(edge)
        except Exception as e:
            logger.warning("Chunk %d: edge validation error: %s", chunk_index, e)

    logger.info("Chunk %d: accepted %d nodes, %d edges", chunk_index, len(nodes), len(edges))
    return ExtractionChunk(nodes=nodes, edges=edges, chunk_index=chunk_index)


# ---------------------------------------------------------------------------
# Cross-chunk code-level merge (string similarity)
# ---------------------------------------------------------------------------

def _label_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _find_canonical(label: str, canonical_map: dict[str, str], threshold: float = 0.82) -> str | None:
    for existing_label, node_id in canonical_map.items():
        if _label_similarity(label, existing_label) >= threshold:
            return node_id
    return None


def merge_chunks(chunks: list[ExtractionChunk]) -> ConceptGraph:
    canonical_map: dict[str, str] = {}
    nodes_by_id: dict[str, Node] = {}

    for chunk in chunks:
        for node in chunk.nodes:
            canon_id = _find_canonical(node.label, canonical_map)
            if canon_id:
                existing = nodes_by_id[canon_id]
                for p in node.source_passages:
                    if p not in existing.source_passages:
                        existing.source_passages.append(p)
                for ci in node.chunk_indices:
                    if ci not in existing.chunk_indices:
                        existing.chunk_indices.append(ci)
            else:
                canonical_map[node.label.lower()] = node.id
                nodes_by_id[node.id] = node

    seen_edges: set[tuple[str, str, str]] = set()
    edges: list[Edge] = []

    for chunk in chunks:
        local_id_to_label = {n.id: n.label for n in chunk.nodes}
        for edge in chunk.edges:
            src_label = local_id_to_label.get(edge.source_id, "")
            tgt_label = local_id_to_label.get(edge.target_id, "")
            canon_src = _find_canonical(src_label, canonical_map)
            canon_tgt = _find_canonical(tgt_label, canonical_map)
            if not canon_src or not canon_tgt:
                logger.warning("Merge: dropping edge — could not resolve: %s → %s", src_label, tgt_label)
                continue
            sig = (canon_src, canon_tgt, edge.type.value)
            if sig in seen_edges:
                continue
            seen_edges.add(sig)
            edges.append(Edge(
                id=edge.id,
                source_id=canon_src,
                target_id=canon_tgt,
                type=edge.type,
                description=edge.description,
                source_passages=edge.source_passages,
            ))

    return ConceptGraph(document_id="", nodes=list(nodes_by_id.values()), edges=edges)


# ---------------------------------------------------------------------------
# Pass 2: Semantic deduplication
# ---------------------------------------------------------------------------

_DEDUP_SYSTEM = """You are reviewing nodes extracted from a document to find semantic duplicates.

Some nodes may refer to the same underlying concept but were extracted with different phrasings or labels across different passages.

Identify groups of nodes that should be merged into one. For each group provide:
- "canonical": the single best label to keep (most precise and specific)
- "merged": list of ALL labels in the group, including the canonical one
- "reason": one sentence explaining why these are the same concept

RULES:
- Only merge nodes that genuinely refer to THE SAME concept — not merely related ones
- Do not merge a general concept with a specific instance of it
- Do not merge opposing claims just because they share topic words (e.g. "long-term contract advantage" and "long-term contract difficulty" are NOT duplicates)
- Do not merge an entity with a concept it is associated with
- Prefer the most informative and specific label as canonical

Respond with valid JSON only:
{
  "merges": [
    {
      "canonical": "label to keep",
      "merged": ["label 1", "label 2"],
      "reason": "one sentence"
    }
  ]
}

If no merges are warranted, return: {"merges": []}"""


def deduplicate_nodes(
    client: anthropic.Anthropic,
    graph: ConceptGraph,
) -> tuple[ConceptGraph, list[dict]]:
    """
    Semantic dedup pass. Returns (updated_graph, report).
    report entries: {canonical, merged, reason, nodes_removed}
    """
    if len(graph.nodes) < 2:
        return graph, []

    node_list_text = "\n".join(
        f'  - "{n.label}" ({n.type.value}): {n.description}'
        for n in graph.nodes
    )
    user_msg = f"NODES TO REVIEW ({len(graph.nodes)} total):\n\n{node_list_text}"

    try:
        response = client.messages.create(
            model=EXTRACTION_MODEL,
            max_tokens=4096,
            system=_DEDUP_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
    except Exception as e:
        logger.warning("Dedup pass failed (%s) — skipping", e)
        return graph, []

    merges = data.get("merges", [])
    if not merges:
        logger.info("Dedup pass: no merges identified")
        return graph, []

    label_to_node: dict[str, Node] = {n.label.lower(): n for n in graph.nodes}

    # Build old_id → canonical_id remap
    id_remap: dict[str, str] = {}
    nodes_to_remove: set[str] = set()
    report: list[dict] = []

    for merge in merges:
        canonical_label = merge.get("canonical", "").strip().lower()
        canonical_node = label_to_node.get(canonical_label)
        if not canonical_node:
            logger.warning("Dedup: canonical label not found in graph: %r", merge.get("canonical"))
            continue

        removed_labels = []
        for label in merge.get("merged", []):
            label_lower = label.strip().lower()
            if label_lower == canonical_label:
                continue
            old_node = label_to_node.get(label_lower)
            if not old_node:
                logger.warning("Dedup: merged label not found in graph: %r", label)
                continue
            id_remap[old_node.id] = canonical_node.id
            nodes_to_remove.add(old_node.id)
            removed_labels.append(old_node.label)
            # Carry source passages into canonical
            for p in old_node.source_passages:
                if p not in canonical_node.source_passages:
                    canonical_node.source_passages.append(p)

        if removed_labels:
            report.append({
                "canonical": canonical_node.label,
                "merged_away": removed_labels,
                "reason": merge.get("reason", ""),
            })

    # Rewrite edges with remapped ids, dropping self-loops and duplicates
    seen_sigs: set[tuple[str, str, str]] = set()
    updated_edges: list[Edge] = []
    self_loops_dropped = 0

    for edge in graph.edges:
        new_src = id_remap.get(edge.source_id, edge.source_id)
        new_tgt = id_remap.get(edge.target_id, edge.target_id)
        if new_src == new_tgt:
            self_loops_dropped += 1
            continue
        sig = (new_src, new_tgt, edge.type.value)
        if sig in seen_sigs:
            continue
        seen_sigs.add(sig)
        updated_edges.append(Edge(
            id=edge.id,
            source_id=new_src,
            target_id=new_tgt,
            type=edge.type,
            description=edge.description,
            source_passages=edge.source_passages,
        ))

    updated_nodes = [n for n in graph.nodes if n.id not in nodes_to_remove]

    logger.info(
        "Dedup: %d merge group(s), %d node(s) removed, %d self-loop(s) dropped",
        len(report), len(nodes_to_remove), self_loops_dropped,
    )

    return ConceptGraph(
        document_id=graph.document_id,
        nodes=updated_nodes,
        edges=updated_edges,
    ), report


# ---------------------------------------------------------------------------
# Pass 3: Depends-on direction verification
# ---------------------------------------------------------------------------

_VERIFY_SYSTEM = """You are auditing depends-on edges in a concept graph for correctness of direction.

Definition: SOURCE depends-on TARGET means "SOURCE cannot be true, useful, or meaningful without TARGET being true."

Direction test: If you removed TARGET from the argument entirely, would SOURCE lose its meaning or truth? If yes, SOURCE→TARGET is correct. If it is actually TARGET that would be meaningless without SOURCE, the edge is reversed.

For each edge, return one of three verdicts:
- "correct": direction is right as stated
- "reversed": the arrow should be flipped — TARGET actually depends-on SOURCE
- "remove": this is not a depends-on relationship at all (use only when clearly the wrong edge type)

Be strict. If you are uncertain, prefer "correct" over "reversed" — a wrong flip is worse than a missed flip.

Respond with valid JSON only:
{
  "results": [
    {
      "source": "exact source label",
      "target": "exact target label",
      "verdict": "correct|reversed|remove",
      "reason": "one sentence"
    }
  ]
}"""


def verify_depends_on_edges(
    client: anthropic.Anthropic,
    graph: ConceptGraph,
) -> tuple[ConceptGraph, list[dict]]:
    """
    Verification pass for depends-on edge directions.
    Returns (updated_graph, report).
    report entries: {action: kept|flipped|removed, source, target, reason}
    """
    dep_edges = [e for e in graph.edges if e.type == EdgeType.DEPENDS_ON]
    if not dep_edges:
        return graph, []

    node_map = {n.id: n.label for n in graph.nodes}

    edge_lines = []
    for i, e in enumerate(dep_edges, 1):
        src = node_map.get(e.source_id, "?")
        tgt = node_map.get(e.target_id, "?")
        edge_lines.append(f'{i}. SOURCE: "{src}" | TARGET: "{tgt}"\n   description: {e.description}')

    user_msg = f"DEPENDS-ON EDGES TO VERIFY ({len(dep_edges)} edges):\n\n" + "\n\n".join(edge_lines)

    try:
        response = client.messages.create(
            model=EXTRACTION_MODEL,
            max_tokens=4096,
            system=_VERIFY_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
    except Exception as e:
        logger.warning("Verification pass failed (%s) — skipping", e)
        return graph, []

    # Build lookup: (src_label_lower, tgt_label_lower) → verdict entry
    verdict_map: dict[tuple[str, str], dict] = {}
    for r in data.get("results", []):
        key = (r.get("source", "").strip().lower(), r.get("target", "").strip().lower())
        verdict_map[key] = r

    updated_edges: list[Edge] = []
    report: list[dict] = []

    for edge in graph.edges:
        if edge.type != EdgeType.DEPENDS_ON:
            updated_edges.append(edge)
            continue

        src_label = node_map.get(edge.source_id, "")
        tgt_label = node_map.get(edge.target_id, "")
        entry = verdict_map.get((src_label.lower(), tgt_label.lower()))

        if not entry:
            # Not found in verification output — keep as-is, log it
            logger.warning("Verification: no result for edge %r → %r — keeping", src_label, tgt_label)
            updated_edges.append(edge)
            report.append({"action": "kept-unreviewed", "source": src_label, "target": tgt_label, "reason": "not returned by verifier"})
            continue

        verdict = entry.get("verdict", "correct")
        reason = entry.get("reason", "")

        if verdict == "correct":
            updated_edges.append(edge)
            report.append({"action": "kept", "source": src_label, "target": tgt_label, "reason": reason})

        elif verdict == "reversed":
            flipped = Edge(
                id=edge.id,
                source_id=edge.target_id,
                target_id=edge.source_id,
                type=EdgeType.DEPENDS_ON,
                description=edge.description,
                source_passages=edge.source_passages,
            )
            updated_edges.append(flipped)
            report.append({"action": "flipped", "source": src_label, "target": tgt_label, "reason": reason})

        elif verdict == "remove":
            # Drop the edge entirely
            report.append({"action": "removed", "source": src_label, "target": tgt_label, "reason": reason})

    flipped = [r for r in report if r["action"] == "flipped"]
    removed = [r for r in report if r["action"] == "removed"]
    logger.info(
        "Verification: %d edges reviewed, %d flipped, %d removed",
        len(dep_edges), len(flipped), len(removed),
    )

    return ConceptGraph(
        document_id=graph.document_id,
        nodes=graph.nodes,
        edges=updated_edges,
    ), report


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_graph(
    text: str,
    document_id: str,
) -> tuple[ConceptGraph, list[dict], list[dict]]:
    """
    Full pipeline: chunk → extract → code-merge → semantic-dedup → verify.

    Returns:
      graph        — final ConceptGraph
      dedup_report — list of {canonical, merged_away, reason} dicts
      verify_report — list of {action, source, target, reason} dicts

    Callers must surface these reports — do not silently discard them.
    Requires ANTHROPIC_API_KEY in environment.
    """
    from .chunker import chunk_text

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    chunks = chunk_text(text)
    logger.info("Extracting graph from %d chunks", len(chunks))

    extracted: list[ExtractionChunk] = []
    for chunk in chunks:
        result = _extract_chunk(client, chunk)
        if result:
            extracted.append(result)
        else:
            logger.warning("Chunk %d produced no valid extraction — skipped", chunk.index)

    if not extracted:
        raise ValueError("Extraction produced no valid chunks. Check logs for details.")

    graph = merge_chunks(extracted)
    graph.document_id = document_id
    logger.info("After code-merge: %d nodes, %d edges", len(graph.nodes), len(graph.edges))

    graph, dedup_report = deduplicate_nodes(client, graph)
    logger.info("After semantic-dedup: %d nodes, %d edges", len(graph.nodes), len(graph.edges))

    graph, verify_report = verify_depends_on_edges(client, graph)
    logger.info("After verification: %d nodes, %d edges", len(graph.nodes), len(graph.edges))

    return graph, dedup_report, verify_report
