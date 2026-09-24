#!/usr/bin/env python3
"""ASM extractor for graphify's knowledge graph.

graphify (https://github.com/, installed as a uv tool) has no .asm parser, so
this script does the source-level extraction itself and hands the result to
graphify's OWN build/cluster/export pipeline (graphify.build.build_from_json,
graphify.cluster.cluster, graphify.export.to_json) so the output is a
first-class graphify graph, queryable with the regular
`graphify query|explain|path|affected --graph graphify-out/asm/graph.json`
CLI commands.

Scans every *.asm file under engine/, home/, data/, ram/, macros/,
constants/, maps/, scripts/, audio/ (skipping .claude/, graphify-out/, and
tools/) and extracts:

Nodes
  - one node per global label: a `Name:` / `Name::` definition at column 0
    (NOT a `.local` label, which starts with a dot and is never at column 0
    in this codebase's convention).
  - RAM symbols are the subset of global labels defined inside ram/*.asm
    (the wFoo::/hFoo:: convention) - tagged kind="ram_symbol".
  - one node per scanned file.

Edges
  - calls: call/jp/jr/rst and the far-call macros (callfar, farcall, jpfar,
    farjp, predef, homecall, homecall_sf, callab) whose operand resolves to a
    known global label. Attributed to the nearest global label above the
    call site (the enclosing function), since RGBDS has no other notion of
    "current function".
  - reads / writes: `ld a,[wFoo]` / `ld [wFoo],a` (and `ldh`/hFoo) where wFoo
    is a known RAM symbol.
  - references: `ld hl/bc/de, Label` where Label is any known global label
    (RAM symbol or code label) - e.g. loading a table/RAM address.
  - defined_in: label -> the file it is defined in.
  - includes: file -> file, from `INCLUDE "path"` (paths are project-root
    relative in this codebase).

Output: graphify-out/asm/graph.json, plus graphify-out/asm/graph.html when
the graph has <= 5000 nodes (graphify's own interactive viz is skipped above
that, same threshold graphify itself uses to avoid an unusable render).

Run by hand any time with:  python3 tools/asm_graph.py
It also reruns automatically from .git/hooks/post-commit whenever a commit
touches a .asm file.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_DIR_NAMES = [
    "engine", "home", "data", "ram", "macros", "constants", "maps", "scripts", "audio",
]
SKIP_DIR_NAMES = {".claude", "graphify-out", "tools"}
OUT_DIR = REPO_ROOT / "graphify-out" / "asm"
OUT_GRAPH = OUT_DIR / "graph.json"
OUT_HTML = OUT_DIR / "graph.html"
HTML_NODE_LIMIT = 5000


def _ensure_graphify_importable() -> None:
    """graphify is installed as a `uv tool` (its own isolated venv), not into
    whatever `python3` a caller happens to run this script with. Try a plain
    import first (covers running under graphify's own interpreter, or a repo
    that pip-installed it normally); otherwise locate graphify's site-packages
    next to the interpreter path graphify itself recorded in
    graphify-out/.graphify_python and add it to sys.path.
    """
    try:
        import graphify  # noqa: F401
        return
    except ImportError:
        pass
    marker = REPO_ROOT / "graphify-out" / ".graphify_python"
    if marker.exists():
        py = Path(marker.read_text(encoding="utf-8").strip())
        for pattern in ("lib*/python*/site-packages", "lib/python*/site-packages"):
            for sp in py.parent.parent.glob(pattern):
                sys.path.insert(0, str(sp))
    try:
        import graphify  # noqa: F401
    except ImportError as exc:
        sys.exit(
            f"error: graphify is not importable (looked next to {marker}): {exc}\n"
            "Run this with the interpreter graphify itself uses, e.g.:\n"
            "  $(cat graphify-out/.graphify_python) tools/asm_graph.py"
        )


_ensure_graphify_importable()

from graphify.build import build_from_json  # noqa: E402
from graphify.cluster import cluster  # noqa: E402
from graphify.export import to_json, to_html  # noqa: E402
from graphify.ids import normalize_id, make_id  # noqa: E402

# --- source patterns -----------------------------------------------------

# A global label definition: identifier at column 0 immediately followed by
# `:` or `::` (a `.local` label starts with `.`, which this char class
# excludes, so it's never mistaken for a global one).
GLOBAL_LABEL_RE = re.compile(r"^([A-Za-z_]\w*)(::?)(?!\w)")
INCLUDE_RE = re.compile(r'^\s*INCLUDE\s+"([^"]+)"', re.IGNORECASE)

CALL_MNEMONICS = (
    "call", "jp", "jr", "rst",
    "callfar", "farcall", "jpfar", "farjp",
    "predef", "homecall", "homecall_sf", "callab",
)
CALL_RE = re.compile(
    r"^\s*(" + "|".join(CALL_MNEMONICS) + r")\s+"
    r"(?:(?:z|nz|c|nc)\s*,\s*)?"
    r"([A-Za-z_]\w*)"
)
READ_RE = re.compile(r"^\s*ldh?\s+a\s*,\s*\[\s*([A-Za-z_]\w*)\s*\]")
WRITE_RE = re.compile(r"^\s*ldh?\s*\[\s*([A-Za-z_]\w*)\s*\]\s*,\s*a\b")
REF_RE = re.compile(r"^\s*ld\s+(?:hl|bc|de)\s*,\s*([A-Za-z_]\w*)")

REGISTERS = {"a", "b", "c", "d", "e", "h", "l", "hl", "bc", "de", "sp", "af", "hli", "hld", "pc"}


def iter_asm_files():
    for dname in SCAN_DIR_NAMES:
        top = REPO_ROOT / dname
        if not top.is_dir():
            continue
        for p in sorted(top.rglob("*.asm")):
            rel_parts = p.relative_to(REPO_ROOT).parts
            if any(part in SKIP_DIR_NAMES for part in rel_parts):
                continue
            yield p


def unique_node_id(base: str, label: str, ids_seen: dict) -> str:
    """normalize_id() casefolds, so two distinct (case-sensitive) RGBDS
    labels could in theory collapse onto the same id. Guard against silently
    merging two different symbols into one node."""
    nid = base
    n = 2
    while nid in ids_seen and ids_seen[nid] != label:
        nid = f"{base}_{n}"
        n += 1
    ids_seen[nid] = label
    return nid


def build_extraction():
    files = list(iter_asm_files())
    file_cache: dict[Path, list[str]] = {}

    nodes: list[dict] = []
    edges: list[dict] = []
    ids_seen: dict[str, str] = {}

    file_node_id: dict[str, str] = {}     # repo-relative posix path -> node id
    global_labels: dict[str, dict] = {}   # label name -> {id, file, line, is_ram}

    # --- pass 1: file nodes + every global label (so forward references
    # and cross-file calls resolve no matter which file is scanned first) --
    for p in files:
        rel = p.relative_to(REPO_ROOT).as_posix()
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        file_cache[p] = lines

        fid = unique_node_id(make_id(rel), rel, ids_seen)
        file_node_id[rel] = fid
        nodes.append({
            "id": fid, "label": rel, "file_type": "code",
            "source_file": rel, "source_location": f"{rel}:1",
            "_origin": "asm", "kind": "file",
        })

        is_ram = rel.startswith("ram/")
        for lineno, line in enumerate(lines, start=1):
            m = GLOBAL_LABEL_RE.match(line)
            if not m:
                continue
            name = m.group(1)
            nid = unique_node_id(normalize_id(name), name, ids_seen)
            global_labels[name] = {"id": nid, "file": rel, "line": lineno, "is_ram": is_ram}
            nodes.append({
                "id": nid, "label": name, "file_type": "code",
                "source_file": rel, "source_location": f"{rel}:{lineno}",
                "_origin": "asm", "kind": "ram_symbol" if is_ram else "label",
            })
            edges.append({
                "source": nid, "target": fid, "relation": "defined_in",
                "confidence": "EXTRACTED", "confidence_score": 1.0,
                "source_file": rel, "source_location": f"{rel}:{lineno}",
                "_origin": "asm", "weight": 1.0,
            })

    # --- pass 2: calls/reads/writes/references/includes within each file --
    for p in files:
        rel = p.relative_to(REPO_ROOT).as_posix()
        lines = file_cache.get(p)
        if lines is None:
            continue
        fid = file_node_id[rel]
        current = None  # node id of the nearest global label above the cursor

        for lineno, line in enumerate(lines, start=1):
            m = GLOBAL_LABEL_RE.match(line)
            if m:
                info = global_labels.get(m.group(1))
                if info is not None:
                    current = info["id"]
                continue

            m = INCLUDE_RE.match(line)
            if m:
                target_id = file_node_id.get(m.group(1).strip())
                if target_id is not None:
                    edges.append({
                        "source": fid, "target": target_id, "relation": "includes",
                        "confidence": "EXTRACTED", "confidence_score": 1.0,
                        "source_file": rel, "source_location": f"{rel}:{lineno}",
                        "_origin": "asm", "weight": 1.0,
                    })
                continue

            if current is None:
                # Header/macro-body lines above (or with no) enclosing global
                # label - nothing to attribute call/read/write/ref edges to.
                continue

            m = CALL_RE.match(line)
            if m:
                mnemonic, target_name = m.group(1), m.group(2)
                info = global_labels.get(target_name)
                if info is not None:
                    edges.append({
                        "source": current, "target": info["id"], "relation": "calls",
                        "confidence": "EXTRACTED", "confidence_score": 1.0,
                        "context": mnemonic,
                        "source_file": rel, "source_location": f"{rel}:{lineno}",
                        "_origin": "asm", "weight": 1.0,
                    })
                continue

            m = WRITE_RE.match(line)
            if m:
                sym = m.group(1)
                if sym.lower() not in REGISTERS:
                    info = global_labels.get(sym)
                    if info is not None and info["is_ram"]:
                        edges.append({
                            "source": current, "target": info["id"], "relation": "writes",
                            "confidence": "EXTRACTED", "confidence_score": 1.0,
                            "source_file": rel, "source_location": f"{rel}:{lineno}",
                            "_origin": "asm", "weight": 1.0,
                        })
                continue

            m = READ_RE.match(line)
            if m:
                sym = m.group(1)
                if sym.lower() not in REGISTERS:
                    info = global_labels.get(sym)
                    if info is not None and info["is_ram"]:
                        edges.append({
                            "source": current, "target": info["id"], "relation": "reads",
                            "confidence": "EXTRACTED", "confidence_score": 1.0,
                            "source_file": rel, "source_location": f"{rel}:{lineno}",
                            "_origin": "asm", "weight": 1.0,
                        })
                continue

            m = REF_RE.match(line)
            if m:
                sym = m.group(1)
                if sym.lower() not in REGISTERS:
                    info = global_labels.get(sym)
                    if info is not None:
                        edges.append({
                            "source": current, "target": info["id"], "relation": "references",
                            "confidence": "EXTRACTED", "confidence_score": 1.0,
                            "source_file": rel, "source_location": f"{rel}:{lineno}",
                            "_origin": "asm", "weight": 1.0,
                        })

    return {"nodes": nodes, "edges": edges}, len(files)


def _git_head() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or None if out.returncode == 0 else None
    except Exception:
        return None


def main() -> int:
    t0 = time.monotonic()
    extraction, n_files = build_extraction()
    t_extract = time.monotonic()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    G = build_from_json(extraction, directed=True, root=REPO_ROOT)
    t_build = time.monotonic()

    communities = cluster(G)
    t_cluster = time.monotonic()

    ok = to_json(G, communities, str(OUT_GRAPH), force=True, built_at_commit=_git_head())
    if not ok:
        print("error: to_json refused to write graphify-out/asm/graph.json", file=sys.stderr)
        return 1

    html_written = False
    n_nodes = G.number_of_nodes()
    if n_nodes <= HTML_NODE_LIMIT:
        try:
            html_written = bool(to_html(G, communities, str(OUT_HTML)))
        except Exception as exc:  # HTML is a bonus output; never fail the build over it
            print(f"warning: graph.html generation skipped: {exc}", file=sys.stderr)
    t_done = time.monotonic()

    print(
        f"asm_graph: {n_files} files scanned, {n_nodes} nodes, "
        f"{G.number_of_edges()} edges, {len(communities)} communities"
    )
    print(
        f"asm_graph: extract={t_extract - t0:.2f}s build={t_build - t_extract:.2f}s "
        f"cluster={t_cluster - t_build:.2f}s export={t_done - t_cluster:.2f}s "
        f"total={t_done - t0:.2f}s"
    )
    print(f"asm_graph: wrote {OUT_GRAPH}" + (f" and {OUT_HTML}" if html_written else " (no HTML)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
