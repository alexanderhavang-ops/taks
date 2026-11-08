# Martine Agents SDK migration — call graph and cutover

Status: source migration on feature branch; **not deployed**. Regression suites
are committed but have not yet been executed on a node. Real provider and CoT
network smoke tests are still required. Do not enable until key and service
runtime are provisioned and the tests below have passed.

## Entry points and callers

| Entry/caller | Existing path | Migrated behavior |
| --- | --- | --- |
| Live ATAK direct GeoChat | `martine.chat.cot_tls_client.handle_one_message` → `martine.agent.simple_agent.run_once` → `AgentLoop.run` → `MartineLlm` | Same interface → Agents SDK Runner → Martine MCP → response via existing CoT TLS socket |
| TAKCTL chat endpoint | `takctl.web.api.martine:POST /api/martine/ask` → `run_once` | Same return contract; separate thread |
| CLI `martine.main ask` | `run_once` | Same contract |
| TAKCTL LLM3 phases | `takctl.services.llm3.runner.run_phase2/run_phase3` → `AgentLoop.run` | JSON answer dictionary preserved; no cross-run chat session |
| Legacy UDP receiver | `martine.chat.udp_client.run_forever` → `run_once` | Same interface; not primary systemd path |
| Legacy DB polling | `martine.chat.cot_loop.run_once_cot` → `run_once` | Same interface; not primary systemd path |
| Direct MCP CLI/client | `martine.main mcp-tools/mcp-call/mcp-client-*` | Unchanged |
| Martine MCP server | `martine.mcp_server.fastmcp_app` | Reused through SDK `MCPServerStdio` |
| XMPP roster/inviter | `martine/bin/martine-xmpp-roster-sync`, `martine-xmpp-inviter` | Unchanged; not inference callers |
| Mumble voice | `martine.voice.main` → segmenter → faster-whisper → transcript store | Unchanged; transcriptions remain local |
| TAKCTL LLM2 reports | `takctl.services.llm2.llm_client.LlmClient` | Unchanged; separate Bedrock/local transport |
| TAK replay agent | `takctl/replay/unit_agent.py` → `llm_runner` | Separate simulation inference path; unaffected |
| CoT presence/onboarding | `cot_tls_client.session_loop` and `maybe_process_recent_devices` | Unchanged |

## Uploaded documents / RAG

- Upload: `POST /api/docs/upload` in `takctl.web.api.documents`. ZIP/PDF
  input is queued through `takctl.services.docs_ingest.queue_uploaded_pdf`.
- Processing: `docs_jobs` worker extracts text (OCR fallback), detects
  headings/sections and writes chunks to
  `/opt/tak/tools/takctl/state/docs/derived/<doc_id>/`.
- Registry: `state/docs/registry/docs.json`. Source PDFs, derived chunks
  and section data stay on the node and **must not be deleted in migration**.
- Embeddings: `martine.tools.docs_vectors` uses local FastEmbed
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` and
  `vectors.json` per document. No need for OpenAI vector stores.
- Retrieval: MCP tools `list_reference_docs`,
  `search_reference_docs`, `search_reference_docs_semantic`,
  `get_reference_doc_context`, `list_reference_doc_sections` and
  `get_reference_section` remain in `fastmcp_app`.
- This migration **does not change** document upload, processing, index
  format, search ranking or access to active reference documents.

## New execution boundary

`AgentLoop` is now a thin compatibility facade, not a hand-written
model/tool/repair loop. An Agents SDK `Runner` drives Martine's existing
MCP server via stdio. For interactive CoT sender UIDs, SDK `SQLiteSession`
stores per-sender history under `martine_state_dir/sessions/`. Batch LLM3
jobs intentionally do not reuse conversations. SDK telemetry export is disabled;
Martine retains local per-run traces.

`martine_agent_provider=openai`: OpenAI Responses API. The key is read
from `OPENAI_API_KEY` or `martine_openai_api_key` in protected
`/opt/tak/tools/takctl/secrets.d/martine.conf`. Never commit the key.
`martine_agent_provider=local`: OpenAI-compatible Chat Completions at
loopback `martine_agent_base_url`; configure model name explicitly.

NOTE: A client's callsign is **not** an authenticated UID. Conversation
session selection uses the CoT sender UID. The HTTP `/ask` interface has no
sender authentication context passed into `run_once` and remains stateless.

## Cutover validation (must run before deployment)

1. Install `openai-agents` in a disposable Martine venv.
2. `PYTHONPATH=martine python -m unittest discover -s martine/tests -v`.
3. Smoke MCP stdio tools: ping, semantic document search, retrieve section.
4. With scoped API key: run a single `martine.main ask` and confirm model,
   token usage and no hosted trace export.
5. Run LLM3 phase 2 and phase 3 against fixture prompts and check JSON shape.
6. Test a fresh CoT mTLS session with authenticated recipient, reply, and
   follow-up to verify per-UID memory.
7. Test local-model backend and service restart.
8. Update node bundle, deploy with rollback, inspect service logs and health.

## Existing risks outside the agent rewrite

- CoT TLS `recv_xml` now uses a bounded `CoTEventFramer` to retain incomplete
  events and separate concatenated XML events; real network validation remains.
- CoT `handle_one_message` runs inference synchronously on the receive loop.
- Some legacy MCP dispatcher tool names differ from `fastmcp_app`.
- Login/identity and secret store permissions must be checked before enabling
  remote inference; absence of key results in an explicit error.
- Automatic document reindex is local and may consume RAM; do not substitute
  a hosted vector database without an explicit data-handling decision.

## Regression test matrix

| Use case | Test or probe | External effect |
| --- | --- | --- |
| Chat reply contract / error handling | `test_agents_migration.py` | None |
| Per-UID persistent context and different UID isolation | `test_agents_sdk_workflows.py` | SQLite fixture only |
| OpenAI Agents SDK basic turn and tool execution | `test_agents_sdk_workflows.py` | ScriptedModel, no API calls |
| MCP stdio discovery, current time | `test_martine_use_cases.py` | Local child MCP only |
| Uploaded document list, keyword search, context retrieval | `test_martine_use_cases.py` | Synthetic fixture, no upload |
| Document tools through SDK/MCP | `test_agents_sdk_workflows.py` | Local child MCP, no API calls |
| CoT GeoChat XML parse, address and reply | `test_martine_use_cases.py` | Mock send, no TAK socket |
| CoT TLS fragmentation/coalescing | `test_martine_use_cases.py` | Synthetic socket only |
| Tactical calculations, OSRM parameter validation | `test_martine_use_cases.py` | No DB/network |
| Voice, plugin and map onboarding validation | `test_martine_use_cases.py` | Invalid requests only, no delivery |
| LLM3 JSON result compatibility | `test_agents_migration.py`, `test_agents_sdk_workflows.py` | Local fixture only |
| Live OpenAI Responses API key/billing/inference | `martine.main llm-smoke` | **Paid API call**; explicitly opt in |
| Live CoT and ATAK end-to-end, onboarding delivery | Manual controlled integration scenarios | Requires an operational TAK node |
| Semantic vector retrieval | Existing FastEmbed on-node index + dedicated smoke test | May load local embedding model |

The offline test tool is `martine_offline_self_test`, exposed by Martine's
FastMCP server and excluded from the agent's model-visible tool catalog. On an
installed node it invokes these fixed suites with no OpenAI API calls:

```bash
/opt/tak/tools/martine/.venv/bin/python -m unittest discover \\
  -s /opt/tak/tools/martine/tests -p 'test_*.py' -v
```

Or, through the existing stdio MCP transport:

```bash
/opt/tak/tools/martine/.venv/bin/python -m martine.main \\
  mcp-client-call martine_offline_self_test '{}'
```

The test suite is installed alongside the Martine runtime by
`tak-installer/tak_installer/actions/martine_runtime.py`. It does **not** run
by default when building a node, so deployment cannot silently generate
OpenAI API charges. Save the test results as an artifact before enabling the
new agent in production.
