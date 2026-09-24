# graphify

graphify-out/graph.json only covers .py/.md (graphify has no .asm parser).
For .asm (engine/ home/ data/ ram/ macros/ constants/ maps/ scripts/ audio/),
tools/asm_graph.py builds graphify-out/asm/graph.json: nodes for global
labels, RAM symbols (wX/hX), and files; edges for calls/reads/writes/
references/defined_in/includes.
Before grepping .asm sources, query it:
  graphify explain "<Label>" --graph graphify-out/asm/graph.json
  graphify affected "<Label>" --relation calls --depth 1 --graph graphify-out/asm/graph.json
  graphify path "<A>" "<B>" --graph graphify-out/asm/graph.json

It rebuilds automatically from .git/hooks/post-commit when a commit touches a
.asm file (backgrounded; log: ~/.cache/graphify-rebuild.log). For uncommitted
edits, rebuild by hand: `python3 tools/asm_graph.py`.
