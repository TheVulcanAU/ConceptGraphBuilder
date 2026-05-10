"""
Seed the database from test_output.json so we can smoke-test the API
without re-running the full extraction pipeline.
"""
import json, os, sys, uuid
sys.path.insert(0, os.path.dirname(__file__))

from backend.schema import ConceptGraph, Node, NodeType, Edge, EdgeType
from backend import storage

storage.init_db()

data = json.load(open("test_output.json"))

doc_id = str(uuid.uuid4())
storage.save_document("The Nature of the Firm (Coase 1937)", "…text omitted…", doc_id)

nodes = []
for n in data["nodes"]:
    nodes.append(Node(
        id=n["id"],
        label=n["label"],
        type=NodeType(n["type"]),
        description=n["description"],
        source_passages=n.get("source_passages", []),
        chunk_indices=n.get("chunk_indices", []),
    ))

edges = []
for e in data["edges"]:
    try:
        edges.append(Edge(
            id=e["id"],
            source_id=e["source_id"],
            target_id=e["target_id"],
            type=EdgeType(e["type"]),
            description=e.get("description", ""),
            source_passages=e.get("source_passages", []),
        ))
    except Exception as ex:
        print(f"Skipping edge {e.get('id')}: {ex}")

graph = ConceptGraph(document_id=doc_id, nodes=nodes, edges=edges)
storage.save_graph(graph)

print(f"Seeded document {doc_id}")
print(f"  {len(nodes)} nodes, {len(edges)} edges")
print(f"\nTest the graph at: http://127.0.0.1:8001/documents/{doc_id}/graph")
