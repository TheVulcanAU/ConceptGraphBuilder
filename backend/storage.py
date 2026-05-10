"""
SQLite storage layer.

Schema:
  documents(id, title, source_text, created_at)
  nodes(id, document_id, label, type, description, source_passages_json, chunk_indices_json)
  edges(id, document_id, source_id, target_id, type, description, source_passages_json)
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .schema import ConceptGraph, Document, Edge, EdgeType, Node, NodeType

DB_PATH = Path(__file__).parent.parent / "data" / "graphs.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                source_text TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS nodes (
                id                   TEXT PRIMARY KEY,
                document_id          TEXT NOT NULL REFERENCES documents(id),
                label                TEXT NOT NULL,
                type                 TEXT NOT NULL,
                description          TEXT NOT NULL,
                source_passages_json TEXT NOT NULL DEFAULT '[]',
                chunk_indices_json   TEXT NOT NULL DEFAULT '[]'
            );

            CREATE TABLE IF NOT EXISTS edges (
                id                   TEXT PRIMARY KEY,
                document_id          TEXT NOT NULL REFERENCES documents(id),
                source_id            TEXT NOT NULL REFERENCES nodes(id),
                target_id            TEXT NOT NULL REFERENCES nodes(id),
                type                 TEXT NOT NULL,
                description          TEXT NOT NULL,
                source_passages_json TEXT NOT NULL DEFAULT '[]'
            );

            CREATE INDEX IF NOT EXISTS idx_nodes_doc   ON nodes(document_id);
            CREATE INDEX IF NOT EXISTS idx_edges_doc   ON edges(document_id);
            CREATE INDEX IF NOT EXISTS idx_edges_src   ON edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_edges_tgt   ON edges(target_id);
        """)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def save_document(title: str, source_text: str, document_id: str) -> Document:
    doc = Document(
        id=document_id,
        title=title,
        source_text=source_text,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    with get_connection() as conn:
        with transaction(conn):
            conn.execute(
                "INSERT INTO documents(id, title, source_text, created_at) VALUES (?,?,?,?)",
                (doc.id, doc.title, doc.source_text, doc.created_at),
            )
    return doc


def save_graph(graph: ConceptGraph) -> None:
    with get_connection() as conn:
        with transaction(conn):
            for node in graph.nodes:
                conn.execute(
                    """INSERT INTO nodes(id, document_id, label, type, description,
                       source_passages_json, chunk_indices_json)
                       VALUES (?,?,?,?,?,?,?)""",
                    (
                        node.id,
                        graph.document_id,
                        node.label,
                        node.type.value,
                        node.description,
                        json.dumps(node.source_passages),
                        json.dumps(node.chunk_indices),
                    ),
                )
            for edge in graph.edges:
                conn.execute(
                    """INSERT INTO edges(id, document_id, source_id, target_id, type,
                       description, source_passages_json)
                       VALUES (?,?,?,?,?,?,?)""",
                    (
                        edge.id,
                        graph.document_id,
                        edge.source_id,
                        edge.target_id,
                        edge.type.value,
                        edge.description,
                        json.dumps(edge.source_passages),
                    ),
                )


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def _row_to_node(row: sqlite3.Row) -> Node:
    return Node(
        id=row["id"],
        label=row["label"],
        type=NodeType(row["type"]),
        description=row["description"],
        source_passages=json.loads(row["source_passages_json"]),
        chunk_indices=json.loads(row["chunk_indices_json"]),
    )


def _row_to_edge(row: sqlite3.Row) -> Edge:
    return Edge(
        id=row["id"],
        source_id=row["source_id"],
        target_id=row["target_id"],
        type=EdgeType(row["type"]),
        description=row["description"],
        source_passages=json.loads(row["source_passages_json"]),
    )


def list_documents() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at FROM documents ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_graph(document_id: str) -> ConceptGraph | None:
    with get_connection() as conn:
        doc_row = conn.execute("SELECT id FROM documents WHERE id=?", (document_id,)).fetchone()
        if not doc_row:
            return None
        node_rows = conn.execute("SELECT * FROM nodes WHERE document_id=?", (document_id,)).fetchall()
        edge_rows = conn.execute("SELECT * FROM edges WHERE document_id=?", (document_id,)).fetchall()
    return ConceptGraph(
        document_id=document_id,
        nodes=[_row_to_node(r) for r in node_rows],
        edges=[_row_to_edge(r) for r in edge_rows],
    )


def get_node(node_id: str) -> Node | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
    return _row_to_node(row) if row else None


def get_edges_for_node(node_id: str) -> list[Edge]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM edges WHERE source_id=? OR target_id=?", (node_id, node_id)
        ).fetchall()
    return [_row_to_edge(r) for r in rows]
