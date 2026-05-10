"""
Standalone extraction test. Run with:
  python test_extraction.py

Prints raw extracted nodes and edges to stdout.
Requires ANTHROPIC_API_KEY in environment.
"""

import json
import os
import sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(__file__))

# Load .env if present
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from backend.chunker import chunk_text
from backend.extractor import _extract_chunk, merge_chunks, deduplicate_nodes, verify_depends_on_edges

# Coase, "The Nature of the Firm" (1937)
ESSAY = open(r"c:\Users\Vulcan\CLAUDE_2\data\coase_1937.txt", encoding="utf-8").read()

# Paul Graham, "Keep Your Identity Small" (2009) — short, clear argumentative structure
ESSAY_LEGACY = """
Keep Your Identity Small

February 2009

I finally realized why politics and religion yield such uniquely
fruitless discussions.

As a rule, any mention of religion near the top of a discussion is a
bad sign. But this rule has exceptions. For example, if one person
in the discussion is a religious expert, they may be able to add
genuinely useful information. And they may be able to refute false
claims that would otherwise go unchallenged.

What makes politics and religion such fertile ground for unproductive
argument? It's the fact that they involve questions where there are no
good answers, isn't it? No, I don't think that's it. There are other
areas of discussion, like abstract math, where there are also difficult
questions with no clear answers, yet people argue about them much more
productively.

I think what makes politics and religion such uniquely bad subjects
for discussion is that they involve questions where people's identities
are invested. And when people's identities are threatened, rationality
goes out the window.

The more labels you have for yourself, the dumber you get. If you
call yourself a "conservative" or a "liberal," you become less able
to think clearly about politics than you would if you were just trying
to figure out what was true.

The same thing happens with religion. Someone who has the identity of
"Christian" or "Muslim" or "atheist" will be much less able to think
clearly about religious questions than someone who is just trying to
figure out what's true.

Because it isn't what you believe that matters, it's how you hold
those beliefs. If you hold them as part of your identity, they stop
being something you can examine, and start being something you feel
compelled to defend.

So why do religious and political discussions go so wrong? I think
the problem is precisely that they touch on questions where people's
identities are so deeply involved. It's not the difficulty of the
questions that causes the dysfunction, but the identity investment.

The solution is to keep your identity small. If your identity doesn't
depend on your beliefs, you're free to examine them.

Most people who succeed at making good arguments are those who don't
have a lot invested in any particular conclusion. Experts in a field
often do better at this than non-experts, because their identity is
tied up in getting the right answer, not in any particular answer
being right.

Probably most people reading this have already had the experience of
having a good argument with someone on a subject where neither of you
had a strong identity investment, and noticing how much more
productive it was.

There's one simple rule that will help you avoid unproductive
arguments: never say that you are something you believe. Instead of
saying "I am a Christian," say "I believe Christianity is true."
Instead of "I'm a conservative," say "I think conservative policies
are better." The first form of statement locks you into an identity;
the second keeps you free to examine the belief.

If you can follow that rule, you'll save yourself a lot of unproductive
arguments. More importantly, you'll be able to think more clearly about
the things you care most about.
"""  # end ESSAY_LEGACY


def main():
    chunks = chunk_text(ESSAY)
    print(f"=== Chunked into {len(chunks)} chunk(s) ===\n")
    for c in chunks:
        print(f"Chunk {c.index}: {len(c.text)} chars")
    print()

    extracted = []
    for chunk in chunks:
        print(f"--- Extracting chunk {chunk.index} ---")
        result = _extract_chunk(
            __import__('anthropic').Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]),
            chunk
        )
        if result:
            extracted.append(result)
            print(f"  nodes: {len(result.nodes)}, edges: {len(result.edges)}")
        else:
            print("  FAILED")

    client = __import__('anthropic').Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    print("\n=== CODE MERGE ===\n")
    graph = merge_chunks(extracted)
    graph.document_id = "test"
    print(f"After code-merge: {len(graph.nodes)} nodes, {len(graph.edges)} edges")

    print("\n=== SEMANTIC DEDUP PASS ===\n")
    graph, dedup_report = deduplicate_nodes(client, graph)
    if dedup_report:
        print(f"Merged {sum(len(r['merged_away']) for r in dedup_report)} node(s) into {len(dedup_report)} canonical node(s):\n")
        for r in dedup_report:
            print(f"  KEPT:    \"{r['canonical']}\"")
            for m in r['merged_away']:
                print(f"  REMOVED: \"{m}\"")
            print(f"  REASON:  {r['reason']}")
            print()
    else:
        print("  No merges.")
    print(f"After dedup: {len(graph.nodes)} nodes, {len(graph.edges)} edges")

    print("\n=== VERIFICATION PASS ===\n")
    graph, verify_report = verify_depends_on_edges(client, graph)
    flipped = [r for r in verify_report if r['action'] == 'flipped']
    removed = [r for r in verify_report if r['action'] == 'removed']
    unreviewed = [r for r in verify_report if r['action'] == 'kept-unreviewed']
    print(f"Reviewed {len(verify_report)} depends-on edges: {len(flipped)} flipped, {len(removed)} removed, {len(unreviewed)} unreviewed\n")
    if flipped:
        print("FLIPPED (direction was reversed):")
        for r in flipped:
            print(f"  WAS:  [{r['source']}] --> [{r['target']}]")
            print(f"  NOW:  [{r['target']}] --> [{r['source']}]")
            print(f"  WHY:  {r['reason']}")
            print()
    if removed:
        print("REMOVED (not a depends-on relationship):")
        for r in removed:
            print(f"  [{r['source']}] --> [{r['target']}]")
            print(f"  WHY:  {r['reason']}")
            print()
    if unreviewed:
        print(f"WARNING: {len(unreviewed)} edge(s) not returned by verifier (kept as-is):")
        for r in unreviewed:
            print(f"  [{r['source']}] --> [{r['target']}]")
        print()

    print(f"After verification: {len(graph.nodes)} nodes, {len(graph.edges)} edges\n")

    print("=== FINAL NODES ===")
    for n in graph.nodes:
        print(f"\n[{n.type.upper()}] {n.label}")
        print(f"  desc: {n.description}")
        if n.source_passages:
            print(f"  passage: \"{n.source_passages[0][:120]}\"")

    print("\n=== FINAL EDGES ===")
    node_map = {n.id: n.label for n in graph.nodes}
    for e in graph.edges:
        src = node_map.get(e.source_id, "?")
        tgt = node_map.get(e.target_id, "?")
        print(f"\n  {src}  --[{e.type}]-->  {tgt}")
        print(f"  desc: {e.description}")
        if e.source_passages:
            print(f"  passage: \"{e.source_passages[0][:120]}\"")

    with open("test_output.json", "w") as f:
        json.dump({
            "nodes": [n.model_dump() for n in graph.nodes],
            "edges": [
                {**e.model_dump(), "_src_label": node_map.get(e.source_id,"?"), "_tgt_label": node_map.get(e.target_id,"?")}
                for e in graph.edges
            ],
            "dedup_report": dedup_report,
            "verify_report": verify_report,
        }, f, indent=2)
    print("\n\nFull output written to test_output.json")


if __name__ == "__main__":
    main()
