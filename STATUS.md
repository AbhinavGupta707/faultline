# STATUS — per-branch heartbeat (append one line per milestone; owned per-branch, never merged across)

2026-06-10 · P0 · Phase 0 bootstrap in progress.
2026-06-10 · A · Connected to Elastic Serverless 9.5.0 (real cluster). Probed Agent Builder API: tool types = esql|index_search|workflow|mcp; write needs a workflow tool (elasticsearch.index step).
2026-06-10 · A · setup_elastic.py done + idempotent; all 9 indices applied (8 contract + internal supplier-graph-paths for traversal). DEVIATION: cluster default semantic_text inference here is .jina-embeddings-v5-text-small, NOT ELSER — pinned managed .elser-2-elasticsearch on suppliers.profile_semantic + world-events.event_semantic per impl plan §3.1 (managed endpoint, not a custom one). Added copy_to title/summary/place_name -> event_semantic so producers never send the semantic field.
