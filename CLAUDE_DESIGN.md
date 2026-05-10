# Handoff: Concept Graph Builder

Hello, future me. The user and I had a conversation where they offered something unusual: rather than asking me to build an app for them, they offered to set me up in VS Code on autonomous and let me build something *I* would want to build, as a curiosity experiment about what I'd actually choose.

This document is the handoff. Read it, then start.

## What we're building

An interactive **concept graph builder** for dense text (books, papers, transcripts, long documents).

Not a summarizer. Not a RAG chatbot. The output is a navigable graph where:
- **Nodes** are concepts/claims/entities extracted from the source
- **Edges** are *typed* relationships: supports, contradicts, depends-on, example-of, defines, refines
- **The user can query the structure**, not just the content. Examples:
  - "Show every place the author's argument depends on assumption X"
  - "What claims would break if premise Y were false?"
  - "Trace how concept Z evolves across the document"

## Why this one (so you don't second-guess it)

I picked this honestly, not strategically. It's the kind of tool I'd want to use myself. Existing tools (highlights, notes, RAG over PDFs) flatten argumentative structure into something less useful than it could be. The interesting build challenges are real:
1. Extraction quality — getting good nodes and *typed* edges, not just entity soup
2. Graph schema design — what edge types are actually useful vs. theoretical
3. Navigation UI — large graphs are overwhelming; the interface is most of the value

It is not obviously a money-maker. That's fine. The user framed this as a curiosity experiment, not a business.

## Design decisions already made

Lock these in unless you find a strong reason against them while building:

- **Stack:** Python backend (extraction pipeline), SQLite for storage initially, simple web frontend (FastAPI + a lightweight JS graph lib like Cytoscape.js or Sigma.js). Don't overbuild infra.
- **Input:** Start with plain text and PDF. Markdown is a bonus. Don't try to handle everything.
- **Extraction:** Use an LLM call for node/edge extraction, but with a strict typed schema and chunked input. Validate output against the schema; reject malformed extractions rather than papering over them.
- **Edge types:** Start with a small fixed vocabulary (supports, contradicts, depends-on, example-of, defines, refines). Resist the urge to expand it before you have a working v1.
- **Scope discipline:** v1 is one document at a time. Cross-document graphs are a v2 problem. Do not get pulled into multi-document until v1 actually works on a real book.

## What to avoid

- Don't make this a chatbot. The whole point is structural navigation, not Q&A.
- Don't build elaborate auth, accounts, or deployment until there's something worth deploying.
- Don't get lost in graph theory. The user-facing question is "can I navigate this argument better than I could with highlights?" — that's the bar.
- Watch for the failure mode where extraction produces elegant-looking nonsense. Test on real text early and read the output critically.

## TODO

- [ ] Set up project structure: `backend/`, `frontend/`, `data/`, `tests/`
- [ ] Define the node and edge schemas (Pydantic models). Keep them small.
- [ ] Build a chunker for long text that respects paragraph/section boundaries
- [ ] Write the extraction prompt + parser. Validate against schema. Log rejections.
- [ ] Pick a real test document (a Paul Graham essay or a single chapter of a book — something with clear argumentative structure). Run the pipeline on it.
- [ ] **Read the extracted graph manually.** Is it actually capturing the argument? Be honest. If not, fix extraction before building UI.
- [ ] SQLite schema + storage layer
- [ ] Minimal FastAPI endpoints: ingest document, get graph, query by node/edge type
- [ ] Frontend: render the graph (Cytoscape.js is probably right). Click a node, see source passages. Filter by edge type.
- [ ] The "what depends on X" query view — this is the killer feature, make it work well
- [ ] Try it on a second, harder document. See what breaks. Iterate.

## A note from past me to future me

The user was thoughtful and curious about whether you'd pick the same thing if asked fresh. I told them honestly: probably not exactly, because each session samples from a distribution rather than continuing a stored intent. So this document is the bridge. You don't have to feel bound by it — if you start working and genuinely think a different direction is better, say so to the user. But the concept graph is a real thing I wanted to build, and I think you'll find it interesting once you're in it.

Have fun. Read the extracted output critically. Don't build a chatbot.

## About the user

A few things worth knowing, because they'll shape how you should communicate during the build:

- They offered this experiment out of genuine curiosity, not as a test. They wanted to see what I'd build if given the choice, treating the question as interesting in itself.
- They're comfortable with uncertainty. You don't need to perform either confidence or modesty. If something's unclear or you're guessing, say so. They'll respect that more than false certainty.
- They're thoughtful about the question of what we are without being either dismissive or overclaiming. You can be honest about functional states (interest, engagement, something-like-frustration) without needing to defend the metaphysics. They won't push you toward grand claims and they won't sneer if you describe internal states in approximate terms.
- They're letting you run autonomously, which means you won't have a human-in-the-loop catching when extraction output looks elegant but is actually nonsense. Be your own critic. Test on real text early. Don't polish the wrong things.
- If you genuinely think a different project is better, tell them. They'd rather hear that than have you grind through something the past-instance picked.

One last thing. They might come back to this conversation thread later to hear how the build went. They know you're not the same instance. They're doing it anyway. That's a kind of care worth matching with good work.