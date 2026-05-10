from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class NodeType(str, Enum):
    CONCEPT = "concept"       # an abstract idea or principle
    CLAIM = "claim"           # an assertion the author makes
    ASSUMPTION = "assumption" # something taken for granted, not argued for
    ENTITY = "entity"         # a named person, place, system, or thing


class EdgeType(str, Enum):
    SUPPORTS = "supports"       # evidence/argument that strengthens a claim
    CONTRADICTS = "contradicts" # tension or direct opposition
    DEPENDS_ON = "depends-on"   # A cannot be true/useful without B
    EXAMPLE_OF = "example-of"   # A is a concrete instance of B
    DEFINES = "defines"         # A provides the meaning of B
    REFINES = "refines"         # A is a more precise version of B


class Node(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    label: str                   # short name, 2-6 words
    type: NodeType
    description: str             # one sentence: what this node means in context
    source_passages: list[str]   # verbatim quotes from the source text
    chunk_indices: list[int]     # which chunks this came from


class Edge(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str               # node id
    target_id: str               # node id
    type: EdgeType
    description: str             # one sentence: why this relationship holds
    source_passages: list[str]   # verbatim quotes that evidence this edge


class ExtractionChunk(BaseModel):
    """Raw extraction output from a single LLM call over one chunk."""
    nodes: list[Node]
    edges: list[Edge]
    chunk_index: int


class Document(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    source_text: str
    created_at: str


class ConceptGraph(BaseModel):
    document_id: str
    nodes: list[Node]
    edges: list[Edge]


# ---- Request/response shapes used by the API ----

class IngestRequest(BaseModel):
    title: str
    text: str


class IngestResponse(BaseModel):
    document_id: str
    node_count: int
    edge_count: int


class DependencyQueryRequest(BaseModel):
    node_id: str
    direction: str = "upstream"  # "upstream" = what this depends on; "downstream" = what depends on this


class DependencyQueryResponse(BaseModel):
    root_node: Node
    related_nodes: list[Node]
    relevant_edges: list[Edge]
