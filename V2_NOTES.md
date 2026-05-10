# V2 Schema Notes

## The core problem: depends-on is doing two jobs

The v1 `depends-on` edge type conflates two logically distinct relations. Both feel like "dependency" but they answer different questions and the model conflates them under pressure.

### Argumentative depends-on
**Definition:** A holds *because* B holds. Remove B from the argument and A's *claim* fails or becomes unwarranted.

This is what the killer query ("what would break if premise X were false?") actually needs. Traversing these edges answers: "what is this claim resting on?"

Example from Coase: `firms arise voluntarily` depends-on `cost of using price mechanism`. If there were no cost to using the price mechanism, the claim that firms emerge as more efficient alternatives collapses entirely. This is an argumentative dependency — the premise grounds the claim.

### Epistemic/definitional presupposes
**Definition:** A is only *meaningful* given B. Remove B and A's *concept* becomes undefined or empty — but A's argumentative status is unaffected.

Example from Coase: `optimum amount of planning` presupposes `firms arise voluntarily`. The concept of an "optimum" degree of internal planning only has referent if firms actually exist and vary in size. This is conceptual scaffolding, not argumentative grounding.

---

## The canonical failure case

**Node:** `optimum amount of planning`
**Edge as stored (v1):** `optimum amount of planning` --[depends-on]--> `firms arise voluntarily`
**Description the model gave:** "The optimum has meaning only if firms arise voluntarily"

This is the epistemic reading. It's internally coherent. The verification pass accepted it.

**Correct argumentative reading:** The arrow should be `firms arise voluntarily` --[depends-on]--> `optimum amount of planning`. Coase's argument is that a competitive system produces an optimum degree of internal planning, and this is *why* firms arise voluntarily rather than being imposed. The optimum is the explanation; voluntary emergence is the explanandum.

The verification pass cannot reliably distinguish these two readings with a single edge type — both are defensible as "dependency" and the model picks whichever is locally more salient.

---

## Proposed v2 schema

Split `depends-on` into two edge types:

**`depends-on` (argumentative):** A's *claim* rests on B being true. Use this for the killer query. Traverse these edges to answer "what premises does this argument require?"

**`presupposes` (definitional):** A's *concept* requires B to have a referent. Use this to map conceptual scaffolding. Traverse these to answer "what must exist for this idea to be meaningful?"

### Extraction prompt guidance for v2
The distinction to give the model: "Ask yourself whether removing B would make A *false* (use `depends-on`) or merely *undefined/contentless* (use `presupposes`). If the claim would survive but become about nothing, it's `presupposes`. If the claim would be wrong, it's `depends-on`."

The Coase case is the worked example to include: `firms arise voluntarily` depends-on `cost of using price mechanism` (removing transaction costs makes the claim false); `optimum amount of planning` presupposes `firms arise voluntarily` (removing firm existence makes "optimum" contentless, but doesn't make the claim about optima false — it makes it vacuous).

---

## Other v2 schema observations

**`contradicts` is underproduced on dense academic text.** The Coase paper has genuine competing explanations (Knight's uncertainty theory vs. Coase's transaction cost theory; Usher/Dobb's division-of-labour theory vs. Coase's refutation of it) but the extraction tended to represent these as `supports`/`refines` rather than as competing accounts that `contradict` one another. The `contradicts` guidance may need worked examples from academic argument rather than the current examples which are more suited to essayistic writing.

**Entity nodes inflate edge count without adding structural value.** Nodes for `R. H. Coase`, `Maurice Dobb`, `Sir Arthur Salter` generate citation edges (`Dobb defines islands-of-conscious-power`) that look like structural relationships but are really attribution. Consider filtering entity nodes out of the dependency graph view, or typing them differently so they don't participate in `depends-on` traversal.
