# Known Issues — v1

Discovered during extraction testing (Coase 1937, Paul Graham "Keep Your Identity Small") and live UI smoke test. Not for shipping — for continuity across sessions.

---

## 1. Residual directional error rate (~4%)

**What:** After the verification pass, approximately 4% of `depends-on` edges remain incorrectly directed. Confirmed case: `optimum amount of planning` → `firms arise voluntarily` (arrow reversed; see V2_NOTES.md for full analysis).

**Why it persists:** The verification pass catches systematic reversals but cannot reliably adjudicate cases where both directions are locally coherent. The model picks whichever reading is most salient in the chunk context.

**Impact:** The killer query ("what depends on X?") returns wrong results for nodes involved in reversed edges. A reversed edge is worse than a missing edge because it actively misleads.

**Fix path:** Structural — requires splitting `depends-on` into argumentative and epistemic edge types (see V2_NOTES.md). Not addressable by further prompt iteration on the current schema.

---

## 2. Schema conflation: depends-on does two jobs

**What:** The `depends-on` edge type conflates argumentative dependency (A's *claim* fails without B) and epistemic/definitional presupposition (A's *concept* is undefined without B). The killer query needs only the former; the extraction produces both indiscriminately.

**Confirmed case:** See issue #1 above and V2_NOTES.md for the canonical Coase example.

**Impact:** Dependency traversal returns a mix of "what this argument rests on" and "what this concept presupposes" — structurally different questions, returned as if equivalent.

**Fix path:** v2 schema change — new `presupposes` edge type. No workaround within v1 schema.

---

## 3. Dense-view readability at full zoom

**What:** With 100+ nodes, the full-graph view is unreadable — nodes overlap, labels collide, edge crossings make the structure invisible.

**Confirmed:** Coase graph at full zoom in Cytoscape.js with cose layout.

**What works:** Zoomed-in neighbourhood view is clear. Typed edges (depends-on, contradicts, etc.) are legible at node level.

**Fix path (UI):** Several approaches not yet implemented:
- **Focus mode:** When a node is selected, dim everything outside its n-hop neighbourhood. Currently implemented for 1-hop (`focusNeighbourhood`) but not surfaced prominently enough.
- **Edge type filtering as primary navigation:** Default to showing only `depends-on` edges; let user layer in other types. Currently all types shown by default.
- **Clustering by document section:** Group nodes extracted from the same chunk, collapse groups by default.
- **Overview + detail layout:** Small overview panel for orientation; main panel for the focused subgraph.

None of these require extraction changes — purely UI work.

---

## 4. Empty-state UX in dependency query

**What:** When a node has no `depends-on` edges, the dependency query panel shows a generic empty state. It doesn't tell the user *why* there are no results or what edges the node does have.

**Confirmed:** `agent freedom of employment` node (connected only via `refines`). Empty state correctly displayed but not informative.

**Better behaviour:** "No depends-on edges found. This node connects to [X] via [refines]." — tells the user what's actually there rather than just what isn't.

**Fix path:** Small frontend change. In `queryDependencies()` in `app.js`, when `related_nodes.length === 0`, fetch the node's full edge list from the graph state (already loaded as `currentGraph`) and surface the actual edge types present.

---

## 5. One confirmed bad dedup merge

**What:** In the semantic deduplication pass on Coase, `Knight fails to explain price mechanism supersession` absorbed `knowledge can be sold as advice`. These are two distinct critiques — one is the conclusion of Coase's critique of Knight, the other is a specific argument supporting that conclusion.

**Impact:** One node lost. The structural relationship between the argument and its conclusion is not representable in the graph because they were merged.

**Fix path:** The dedup prompt's "only merge nodes that genuinely refer to THE SAME concept" rule was not sufficient to prevent this. Could add: "Do not merge a conclusion with one of its supporting arguments, even if they are topically closely related."

---

## 6. Entity nodes participate in dependency traversal

**What:** Entity nodes (`R. H. Coase`, `Maurice Dobb`, `Sir Arthur Salter`) generate edges that look structural but are actually attribution. They appear in dependency queries as if they were claims or concepts.

**Impact:** Low — mostly noise in results rather than misleading direction. But adds clutter to the dependency graph view.

**Fix path:** Either filter entity-type nodes from `depends-on` traversal, or add UI filtering by node type so users can exclude entities.
