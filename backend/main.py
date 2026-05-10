"""
FastAPI application.

Endpoints:
  POST   /documents              — ingest plain text
  POST   /documents/pdf          — ingest PDF upload
  GET    /documents              — list all documents
  GET    /documents/{id}/graph   — full graph for a document
  GET    /nodes/{id}             — single node with source passages
  POST   /nodes/{id}/dependencies — what does this node depend on (or what depends on it)
"""

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .schema import (
    ConceptGraph,
    DependencyQueryRequest,
    DependencyQueryResponse,
    Edge,
    IngestRequest,
    IngestResponse,
    Node,
)
from . import storage
from .extractor import extract_graph
from .chunker import extract_text_from_pdf

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _log_pipeline_reports(document_id: str, dedup_report: list, verify_report: list) -> None:
    """Log dedup and verification reports so the pipeline is auditable from server logs."""
    if dedup_report:
        logger.info("=== DEDUP REPORT (doc %s) ===", document_id)
        for r in dedup_report:
            logger.info("  KEPT %r, merged away: %s — %s", r["canonical"], r["merged_away"], r["reason"])
    else:
        logger.info("Dedup: no merges (doc %s)", document_id)

    flipped = [r for r in verify_report if r["action"] == "flipped"]
    removed = [r for r in verify_report if r["action"] == "removed"]
    logger.info("=== VERIFY REPORT (doc %s): %d flipped, %d removed ===", document_id, len(flipped), len(removed))
    for r in flipped:
        logger.info("  FLIPPED: [%s] --> [%s] — %s", r["source"], r["target"], r["reason"])
    for r in removed:
        logger.info("  REMOVED: [%s] --> [%s] — %s", r["source"], r["target"], r["reason"])

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.init_db()
    yield


app = FastAPI(title="Concept Graph Builder", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

@app.post("/documents", response_model=IngestResponse)
async def ingest_text(req: IngestRequest):
    document_id = str(uuid.uuid4())
    storage.save_document(req.title, req.text, document_id)
    graph, dedup_report, verify_report = extract_graph(req.text, document_id)
    storage.save_graph(graph)
    _log_pipeline_reports(document_id, dedup_report, verify_report)
    return IngestResponse(
        document_id=document_id,
        node_count=len(graph.nodes),
        edge_count=len(graph.edges),
    )


@app.post("/documents/pdf", response_model=IngestResponse)
async def ingest_pdf(title: str, file: UploadFile = File(...)):
    pdf_bytes = await file.read()
    text = extract_text_from_pdf(pdf_bytes)
    document_id = str(uuid.uuid4())
    storage.save_document(title, text, document_id)
    graph, dedup_report, verify_report = extract_graph(text, document_id)
    storage.save_graph(graph)
    _log_pipeline_reports(document_id, dedup_report, verify_report)
    return IngestResponse(
        document_id=document_id,
        node_count=len(graph.nodes),
        edge_count=len(graph.edges),
    )


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

@app.get("/documents")
async def list_documents():
    return storage.list_documents()


@app.get("/documents/{document_id}/graph", response_model=ConceptGraph)
async def get_graph(document_id: str):
    graph = storage.get_graph(document_id)
    if not graph:
        raise HTTPException(status_code=404, detail="Document not found")
    return graph


@app.get("/nodes/{node_id}", response_model=Node)
async def get_node(node_id: str):
    node = storage.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


# ---------------------------------------------------------------------------
# Dependency query — the killer feature
# ---------------------------------------------------------------------------

@app.post("/nodes/{node_id}/dependencies", response_model=DependencyQueryResponse)
async def query_dependencies(node_id: str, req: DependencyQueryRequest):
    """
    Returns the set of nodes connected to this node via depends-on edges.
    direction="upstream": what does this node depend on? (follows depends-on edges outward)
    direction="downstream": what depends on this node? (follows depends-on edges inward)
    """
    root = storage.get_node(node_id)
    if not root:
        raise HTTPException(status_code=404, detail="Node not found")

    all_edges = storage.get_edges_for_node(node_id)
    dep_edges = [e for e in all_edges if e.type.value == "depends-on"]

    if req.direction == "upstream":
        # This node depends on these targets
        relevant = [e for e in dep_edges if e.source_id == node_id]
        related_ids = {e.target_id for e in relevant}
    else:
        # These sources depend on this node
        relevant = [e for e in dep_edges if e.target_id == node_id]
        related_ids = {e.source_id for e in relevant}

    related_nodes = [storage.get_node(nid) for nid in related_ids]
    related_nodes = [n for n in related_nodes if n is not None]

    return DependencyQueryResponse(
        root_node=root,
        related_nodes=related_nodes,
        relevant_edges=relevant,
    )


# ---------------------------------------------------------------------------
# Serve frontend
# ---------------------------------------------------------------------------

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
