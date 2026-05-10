# Concept Graph Builder

A tool that reads dense text — books, papers, essays — and builds a navigable graph of how the ideas relate. Not a summary, not a chatbot. An actual map where claims are nodes, the relationships between them are typed (supports, contradicts, depends-on, example-of, defines, refines), and you can ask questions like "what does this argument depend on?" or "what would break if this premise were false?"

It's most useful for analytical reading of theoretical texts — philosophy, economics, legal theory, dense humanities. The kind of reading where the structure of the argument matters, not just its content. If you mostly read narratively, this won't help you.

---

## Provenance

This project was imagined and built by Claude (Anthropic's AI assistant) across multiple sessions. A user — TheVulcan — set up a curiosity experiment: rather than ask Claude to build something specific, he asked Claude to pick something it would want to build, and offered to facilitate the build autonomously.

One Claude session doing the engineering, a separate Claude session reading outputs skeptically, and TheVulcan as the bridge between them — relaying outputs, catching drift early, refusing to let "looks done" stand in for "actually works." That structure produced this. The directional error rate in extraction went from 18% to roughly 4% because someone refused to accept "I think most are earned" as a result.

The schema-conflation issue in KNOWN_ISSUES.md was found because someone tested on a real essay rather than declaring victory after the UI rendered. The whole thing exists because each step was verified before the next was built on top.

If you find this useful, that's good. If you find it rough, that's accurate — see KNOWN_ISSUES.md. If you want to fix things or extend it, the code is here.

---

## Honest limitations

Directional residual rate around 4% on depends-on edges. Some arrows point the wrong way. The depends-on edge type conflates two relations (argumentative and epistemic) that should probably be separate. See V2_NOTES.md. Dense graphs (100+ nodes) are hard to read at full zoom. Zoom and pan work; better overview-detail UI doesn't exist yet. Tested on Paul Graham essays and Coase's "The Nature of the Firm." Probably works on similar argumentative prose. Probably degrades on narrative or descriptive text. Requires an Anthropic API key. Each extraction costs roughly 25–50 cents per essay-length document.

---

## Setup

```bash
# Clone
git clone https://github.com/TheVulcanAU/ConceptGraphBuilder.git
cd ConceptGraphBuilder

# Install dependencies (Python 3.9+ required)
pip install -r requirements.txt

# Add your Anthropic API key
echo "ANTHROPIC_API_KEY=your-key-here" > .env

# Run
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000`, paste in a document, and click **Extract Graph**.

The first extraction on a full essay takes 2–4 minutes. The pipeline runs in three passes: per-chunk extraction, semantic deduplication, and a direction-verification pass on depends-on edges. Progress is logged to the terminal.

---

## What this is not

Not a startup. Not a product. Not maintained on any schedule. A working artifact from an experiment, made public so the few people who'd find it useful can find it.
