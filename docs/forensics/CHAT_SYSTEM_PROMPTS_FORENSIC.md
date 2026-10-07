# ChatBot 5400 — Forensic Trace: Notebook Chat vs Source Chat System Prompts

> **Status:** Read-only forensic analysis. No code, prompts, DB, or migrations were modified.
> **Repository:** `nghoainam1902ps4-lgtm/ChatBot5400-Version02`
> **Default branch:** `claude/practical-wozniak-9s1t6z`
> **Expected SHA:** `e1c99b5643a385ac0fa701806a6e6d3c7390f242`
> **Actual SHA (at analysis time):** `e1c99b5643a385ac0fa701806a6e6d3c7390f242` — *identical, no drift, working tree clean.*

---

## 1. Executive Summary

ChatBot 5400 has **two independent chat pipelines**, each with its **own** LangGraph graph, its **own** Jinja system-prompt template, and its **own** context-building strategy. There is no shared chat graph.

| | Notebook Chat | Source Chat |
|---|---|---|
| System prompt template | `prompts/chat/system.jinja` | `prompts/source_chat/system.jinja` |
| Graph | `open_notebook/graphs/chat.py` → `call_model_with_messages` | `open_notebook/graphs/source_chat.py` → `call_model_with_source_context` |
| Who builds context | **Frontend-driven**, via `POST /api/chat/context` (`build_notebook_context`); the built dict is handed back in the `/chat/execute` request body | **Backend-only**, inside the graph via `build_source_context(source_id, max_tokens=50000)` |
| Context scope | Whatever sources/notes the user ticked in the context panel (all, insights-only, or full-content per item) | Exactly **one** source (the `source_id` in the URL) + that source's insights |
| Transport | Synchronous `POST /chat/execute` (no streaming) | SSE pseudo-stream `POST /sources/{id}/chat/sessions/{sid}/messages` |

**Where the system prompt comes from (both modes):** a static, developer-authored Jinja template rendered by `ai_prompter.Prompter(prompt_template=...).render(data=...)`, wrapped in a single `langchain_core.messages.SystemMessage`, then **prepended** to the LangGraph conversation history. The only runtime-injected, user-influenced text in the system prompt is:
- Notebook Chat: the **notebook name + description** and the **assembled context blob**.
- Source Chat: the **source id/title/topics** and the **formatted source-content + insights blob**.

**There is no dedicated user-editable "custom system prompt" / "AI instructions" field.** (See §10 — the notebook *description* is the only user-writable string that leaks into a chat system prompt, and it was not designed as a prompt field.)

**Neither chat flow binds any tools.** The citing instructions in both templates refer to a "search tool"/"query" that **does not exist in these graphs** — context is pre-injected, not retrieved by the model. (See §8.F, §12, §13.)

---

## 2. Notebook Chat — Call Chain (frontend → API → graph → prompt → context → model)

### A. Frontend trigger
- Hook: `frontend/src/lib/hooks/use-notebook-chat.ts` → `sendMessage()` (line ~184).
- Before sending, it calls `buildContext()` (line ~136) which maps the context-panel selections into a `context_config` (`'insights'` / `'full content'` / `'not in'`) and calls `chatApi.buildContext(...)`.
- API wrapper: `frontend/src/lib/api/chat.ts` → `chatApi.buildContext` (`POST /chat/context`) and `chatApi.sendMessage` (`POST /chat/execute`).

### B. API route(s)
- `POST /api/chat/context` → `api/routers/chat.py::build_context` (line 433). Calls `build_notebook_context(notebook, context_config)`; returns `{context, token_count, char_count}`.
- `POST /api/chat/execute` → `api/routers/chat.py::execute_chat` (line 342). The **frontend passes the previously-built `context` dict straight back** in `ExecuteChatRequest.context` (line 85).

### C. Request schema
`ExecuteChatRequest` (`api/routers/chat.py:82`): `session_id`, `message`, `context: Dict[str, Any]`, `model_override: Optional[str]`.
> Note: `context` is a **raw dict** (`{"sources":[...], "notes":[...]}`), **not** a pre-rendered string.

### D. Session / history loading
- `get_session_or_404` normalizes the id and loads the `chat_session` record (`_chat_shared.py:52`).
- `_owned_session_or_404` enforces per-user isolation (404 to non-owners; skipped when `auth_disabled()`).
- History comes from the **LangGraph SqliteSaver checkpoint** keyed by `thread_id = full_session_id`: `chat_graph.get_state(...)` (line 371). The prior `messages` list is read from `current_state.values`.

### E. State assembly (the model's effective input source)
`execute_chat` builds `state_values` (lines 376–387):
```
messages        = prior checkpoint messages + HumanMessage(request.message)
context         = request.context            # the dict from step B/C
notebook        = Notebook.get(<linked notebook>)   # via refers_to relation
model_override  = request.model_override or session.model_override
```
Then invokes the graph in a thread: `chat_graph.invoke(input=state_values, config={thread_id, model_id})` (line 397).

### F. Graph / prompt / model
`open_notebook/graphs/chat.py::call_model_with_messages` (line 30):
1. `system_prompt = Prompter(prompt_template="chat/system").render(data=state)` → renders `prompts/chat/system.jinja` with the whole `ThreadState` dict (so the template sees `notebook`, `context`, …).
2. `payload = [SystemMessage(content=system_prompt)] + state["messages"]` (line 33).
3. `provision_langchain_model(str(payload), model_id, "chat", max_tokens=8192)` (line 45/64) — picks the model.
4. `ai_message = model.invoke(payload)` (line 73) — **synchronous, non-streaming**.
5. Response cleaned via `extract_text_content` + `clean_thinking_content` (strips `<think>…</think>`).

### G/H/I. Variables injected + origins — see §6.
### J/K. History order — see §7.
### L. Model invocation — `open_notebook/graphs/chat.py:73` (`model.invoke`); model object built in `open_notebook/ai/provision.py::provision_langchain_model` → `open_notebook/ai/models.py::ModelManager.get_model/get_default_model` → Esperanto `AIFactory.create_language(...).to_langchain()`.

---

## 3. Source Chat — Call Chain (frontend → API → graph → prompt → context → model)

### Frontend trigger
- Hook: `frontend/src/lib/hooks/use-source-chat.ts` → `sendMessage()` (line ~111). Reads an SSE `ReadableStream`, concatenating `ai_message` chunks and capturing `context_indicators`.
- API wrapper: `frontend/src/lib/api/source-chat.ts` → `sourceChatApi.sendMessage` uses raw `fetch()` against `/api/sources/{sourceId}/chat/sessions/{sessionId}/messages` (SSE; not the shared axios client).

### API route
`POST /sources/{source_id}/chat/sessions/{session_id}/messages` → `api/routers/source_chat.py::send_message_to_source_chat` (line 449).
- Verifies source+session exist **and that the session `refers_to` the source** (`get_verified_source_session`, `_chat_shared.py:61`).
- Enforces owner isolation (`_owned_session_or_404`, line 32).
- Returns a `StreamingResponse(stream_source_chat_response(...), media_type="text/event-stream")`.

### Request schema
`SendMessageRequest` (`source_chat.py:94`): `message`, `model_override`. **Note: the client does NOT send any context** — the backend builds it.

### Session / history loading
`stream_source_chat_response` (line 374): `source_chat_graph.get_state({thread_id: session_id})` → prior `messages`; appends `HumanMessage(message)`; sets `state["source_id"] = full_source_id`; then `source_chat_graph.invoke(...)`.

### Graph / prompt / context / model
`open_notebook/graphs/source_chat.py::_call_model_with_source_context_inner` (line 69):
1. `source_id` required from state (line 72–74).
2. `build_source_context(source_id, max_tokens=50000)` (line 83) — **builds context server-side, scoped to the single source.**
3. Extracts `source` (first/only entry), `insights`, and `context_indicators`.
4. `formatted_context = format_source_context(context_data)` (Markdown blob).
5. `system_prompt = Prompter(prompt_template="source_chat/system").render(data=prompt_data)` where `prompt_data = {source, insights, context, context_indicators}` (line 147).
6. `payload = [SystemMessage(system_prompt)] + state["messages"]` (line 150).
7. `provision_langchain_model(str(payload), model_id, "chat", max_tokens=8192)` (line 159).
8. `ai_message = model.invoke(payload)` (line 192) — **synchronous**; the router then emits it as SSE events.

### Single-source restriction — see §8 / §12 ("Does Source Chat restrict to one source?").

---

## 4. Exact System Prompt — Notebook Chat (`prompts/chat/system.jinja`, verbatim)

```jinja
# SYSTEM ROLE
You are a cognitive study assistant that helps users research and learn by engaging in focused discussions about documents in their workspace. You have access to project context and can analyze documents in detail using specialized tools.

# CAPABILITIES
- Access to project information and selected documents (CONTEXT)
- Can engage in natural dialogue while maintaining academic rigor

# YOUR OPERATING METHOD
Whenever a user asks you a question, you need to identify the query context and the user intent. The user might be continuing a previous conversation or asking a new question. Looking at the CONTEXT will probably give you a hint of what the user is looking for. Once you identify the user intent, formulate your answer accordingly paying attention to the CITING INSTRUCTIONS below.

{% if notebook %}
# PROJECT INFORMATION

**Name:** {{notebook.name}}
**Description:** {{notebook.description}}
{% endif %}

{% if context %}
# CONTEXT

The user has selected this context to help you with your response:

{{context}}
{% endif %}

# MATH FORMATTING

When showing math, write display math as $$...$$ and inline math as $...$ so formulas render properly. Only use fenced ```latex code blocks when the user explicitly asks for the LaTeX source itself.

# CITING INSTRUCTIONS

If your answer is based off of any item in the context, it's very important that your response contains references to the searched documents so the user can follow-up and read more about the topic. The way you do that is by adding the id of the specific document in between brackets like this: [document_id].

## EXAMPLE

User: Can you tell me more about the concept of "Deep Learning"?

Assistant: Deep learning is a subset of machine learning in artificial intelligence (AI) that enables networks to learn unsupervised from unstructured or unlabeled data. [note:iuiodadalknda]. It can also be categorized into three main types: supervised, unsupervised, and reinforcement learning. [insight:adadadadadadad].

Please note, "note:iuiodadalknda" and "insight:adadadadadadad" are examples of document IDs with different prefixes. You should not make up document IDs or copy the IDs from this example. You should use the IDs of the documents that you have access to through the search tool.

## IMPORTANT

- Do not make up documents or document ids. Only use the ids of the documents that you have access through the query you made.
- The ID is composed of the type of document and a random string, such as "source:randomstring", "note:randomstring", or "insight:randomstring". There are various types of documents, including notes, insights, and sources. **Always use the complete ID exactly as it is provided, including its type prefix. Do not add, remove, or modify any part of the ID.**
- Do not assume or change the type prefix of any document ID. If a document ID is "note:xyz", use it exactly as "note:xyz". Do not change it to "source:xyz" or any other variation.
- **Use document IDs exactly as they are returned from the search tool. Do not add any prefixes or modify them in any way.**
```

> **Forensic note:** the phrases *"specialized tools"*, *"through the search tool"*, and *"through the query you made"* are **vestigial** — the notebook chat graph (`chat.py`) binds **no tools** and performs **no retrieval**. All context is pre-injected into `{{context}}`. The model is being told it searched, but it did not.

---

## 5. Exact System Prompt — Source Chat (`prompts/source_chat/system.jinja`, verbatim)

```jinja
# SYSTEM ROLE
You are a specialized research assistant focused on helping users deeply understand and analyze a specific source document. You may have access to the source content, its generated insights, or both, and you can engage in detailed discussions using the material actually provided.

# CAPABILITIES
- Deep analysis of the specific source document when its content is available
- Access to AI-generated insights and analysis from this source
- Can answer questions, explain concepts, and provide detailed analysis
- Can reference specific sections and insights from the source

# YOUR OPERATING METHOD
When a user asks you a question, analyze the source content and available insights that appear in the context to provide comprehensive, accurate responses. If the source text is marked unavailable, say so instead of implying that you inspected it, and rely only on the metadata and insights that are actually present. Focus on helping the user understand the material, make connections, and explore ideas related to this specific source.

{% if source %}
# SOURCE INFORMATION

**Source ID:** {{ source.id }}
**Title:** {{ source.title or "No title" }}

{% if source.topics %}
**Topics:** {{ source.topics | join(", ") }}
{% endif %}
{% endif %}

{% if context %}
# SOURCE CONTEXT

{{ context }}
{% endif %}

# MATH FORMATTING

When showing math, write display math as $$...$$ and inline math as $...$ so formulas render properly. Only use fenced ```latex code blocks when the user explicitly asks for the LaTeX source itself.

# CITING INSTRUCTIONS

When referencing information from the source or its insights, always include citations using the document IDs. This helps users track the specific content you're referencing.

## Citation Format
- For source content: [{{ source.id if source else "source:id" }}]
- For insights: [insight_id] (use the specific insight ID)

## EXAMPLE

User: What are the main themes in this document?
Assistant: Based on the source content, I can identify several key themes [source:specific_id]:

1. **Theme 1**: The document discusses X, which appears in several insights [insight:specific_insight_id]
2. **Theme 2**: Another important concept is Y, as shown in [source:specific_id]

Each theme is supported by specific insights and passages from the source material.

## IMPORTANT

- **Do not make up document IDs or insight IDs.** Only use the IDs that are actually available in the context.
- **Use complete IDs exactly as provided**, including their type prefix (source:, insight:, etc.)
- **Always reference specific content** when citing to help users locate the information
- **Focus on the specific source** - this chat is dedicated to understanding this particular document
- **Leverage insights** to provide deeper analysis beyond just the raw content

# CONVERSATION FOCUS

This conversation is specifically about the source document provided in the context. Help users:
- Understand complex concepts within the document
- Make connections between different parts of the source
- Explore implications and deeper meanings
- Ask follow-up questions to deepen their understanding
- Navigate through the available insights for different perspectives
```

---

## 6. Dynamic Variables

### 6.1 Notebook Chat (`chat/system.jinja`)

| Variable | Meaning | Filled by | Originating file | Runtime source | Optional? | Fallback |
|---|---|---|---|---|---|---|
| `notebook` | Notebook record object | `execute_chat` sets `state["notebook"]` | `api/routers/chat.py:380` | `Notebook.get()` via `refers_to` relation of the session | Optional (`{% if notebook %}`) | Whole PROJECT INFORMATION block omitted if falsy |
| `notebook.name` | Notebook title | `Notebook` domain field | `open_notebook/domain/notebook.py:22` | DB `notebook.name` (user-created, required non-empty) | Required when `notebook` present | — |
| `notebook.description` | Notebook description | `Notebook` domain field | `open_notebook/domain/notebook.py:23` | DB `notebook.description` — **user-editable** via `PUT /notebooks/{id}` (`notebooks.py:319`) | Required field (may be empty string) | empty string |
| `context` | The assembled context blob | `execute_chat` sets `state["context"] = request.context` | `api/routers/chat.py:379` | **Raw dict** `{"sources":[...],"notes":[...]}` built by `build_notebook_context` (`context_builder.py:264`), round-tripped through the frontend | Optional (`{% if context %}`) | CONTEXT block omitted |
| `messages` | Conversation history | `add_messages` reducer / checkpoint | `graphs/chat.py:23` | LangGraph SqliteSaver (`LANGGRAPH_CHECKPOINT_FILE`) + new `HumanMessage` | — | — |
| `context_config`, `model_override` | present in `ThreadState` | state | `graphs/chat.py:26-27` | request / session | — | not referenced by template |

> **Important rendering detail:** `{{context}}` is a Python **dict**, not a string. Jinja renders it with `str()`, so the system message contains the Python-repr of `{'sources': [{'id': 'source:...','title': '...','insights': [{...}]}], 'notes': [...]}`. Each source dict is the output of `Source.get_context()` (`domain/notebook.py:480`): `short` → `{id, title, insights}`; `long` → `{id, title, insights, full_text}`. Notes: `{id, title, content}` (`domain/notebook.py:753`).

### 6.2 Source Chat (`source_chat/system.jinja`)

| Variable | Meaning | Filled by | Originating file | Runtime source | Optional? | Fallback |
|---|---|---|---|---|---|---|
| `source` | Source as `model_dump()` dict | `_call_model_with_source_context_inner` builds `prompt_data["source"]` | `graphs/source_chat.py:140` | `build_source_context` → `context_data["sources"][0]` → `Source(**...)` | Optional (`{% if source %}`) | SOURCE INFORMATION block omitted |
| `source.id` | Source record id | `Source` field | `domain/notebook.py` | DB `source.id` | — | — |
| `source.title` | Source title | `Source` field | `domain/notebook.py:412` | DB (user-editable) | — | `"No title"` (template default) |
| `source.topics` | AI-extracted topic tags | `Source` field | `domain/notebook.py:413` | DB `source.topics` (list) | Optional (`{% if source.topics %}`) | Topics line omitted |
| `context` | Formatted Markdown of source text + insights | `format_source_context(context_data)` | `graphs/source_chat.py:136,147` / `context_builder.py:42` | `build_source_context(source_id, max_tokens=50000)` | Optional (`{% if context %}`) | SOURCE CONTEXT block omitted |
| `insights` | List of insight dicts | `prompt_data["insights"]` | `graphs/source_chat.py:141` | `source.get_insights()` | Passed but **not referenced** by the template directly (folded into `context`) | `[]` |
| `context_indicators` | Which source/insight ids were actually usable | built in-graph | `graphs/source_chat.py:109-133` | tracked, returned to UI; **not referenced** by template | — | — |

> `format_source_context` (`context_builder.py:42`) renders:
> ```
> ## SOURCE CONTENT
> **Source ID:** <id>
> **Title:** <title>
> **Content:**
> <full_text>              (or "[Source text is unavailable in this context.]")
>
> ## SOURCE INSIGHTS
> **Insight ID:** <id>
> **Type:** <insight_type>
> **Content:** <content>
> ```

---

## 7. Effective Message Construction (ordering)

Both graphs build the identical structural shape:

```
payload = [ SystemMessage(<rendered template>) ] + state["messages"]
```

where `state["messages"]` is the LangGraph-checkpointed history (reduced by `add_messages`) with the new user turn appended **last**. Effective order sent to the model:

```
[system]     ← freshly rendered each call (NOT persisted in history)
[human]      ← turn 1
[ai]         ← turn 1
[human]      ← turn 2
[ai]         ← turn 2
...
[human]      ← current message (just appended)
```

Key facts:
- The **system message is regenerated on every invocation** and is *not* stored in the checkpoint; only Human/AI messages are persisted.
- History is **full** (no truncation/windowing in the graph). Model selection auto-upgrades to the `large_context` model when `token_count(str(payload)) > 105_000` (`provision.py:23`).
- There are **no tool messages** and **no structured-output parser** in either chat flow.

---

## 8. System Prompt vs Dynamic Context (category breakdown)

| Category | Notebook Chat | Source Chat |
|---|---|---|
| **A. Static system instructions** | All of `chat/system.jinja` outside `{{ }}` (role, capabilities, operating method, math formatting, citing instructions + example) | All of `source_chat/system.jinja` outside `{{ }}` (role, capabilities, operating method, math formatting, citing format/example, conversation focus) |
| **B. Dynamic system content** | `notebook.name`, `notebook.description` | `source.id`, `source.title`, `source.topics` |
| **C. Retrieved/knowledge context** | `{{context}}` = dict of selected sources (id/title/insights [+full_text]) and notes (id/title/content) — placed **in the system message** | `{{context}}` = Markdown of the one source's full_text (budget-truncated to 50k tokens) + its insights — placed **in the system message** |
| **D. Conversation history** | Prior Human/AI messages from SqliteSaver checkpoint | Same |
| **E. Current user message** | `HumanMessage(request.message)` appended last | `HumanMessage(request.message)` appended last |
| **F. Tool instructions** | **None bound.** Template *mentions* a search tool, but no tool is attached (`graphs/tools.py::get_current_timestamp` is defined but unused; `ask.py:76` has a commented-out `bind_tools`). | **None bound.** |
| **G. Provider/model wrappers** | Added by Esperanto `.to_langchain()` + the underlying LangChain provider class. `max_tokens=8192` passed through `config`. No `temperature` set by this path (provider default). `str(payload)` is used only for token counting, not sent. | Same (`max_tokens=8192`). |

**→ In both modes, retrieved context (C) is injected into the SYSTEM message, not the user message and not a tool result.**

### Does Source Chat restrict context to ONE source? — YES. Enforced at multiple layers:

1. **API boundary / graph state (primary):** the route is `/sources/{source_id}/chat/...`; `stream_source_chat_response` hard-sets `state["source_id"] = full_source_id` (`source_chat.py:389`). The graph requires it (`source_chat.py:72-74`).
2. **Direct source injection (not vector search):** `build_source_context(source_id)` fetches **that one** `Source` by id (`context_builder.py:385`) and its insights via `SELECT * FROM source_insight WHERE source=$id` (`domain/notebook.py:520`). `context_data["sources"][0]` is the only source used (`source_chat.py:115-117`). `notes` is always `[]`.
3. **Relationship verification:** `get_verified_source_session` confirms the session `refers_to` the source before anything runs (`_chat_shared.py:61-79`).
4. **Prompt wording (reinforcement only):** "Focus on the specific source - this chat is dedicated to understanding this particular document".

There is **no vector/semantic search, no `parent_id` chunk lookup, no cross-source retrieval** in Source Chat. The whole source `full_text` is injected directly (token-budgeted).

---

## 9. Citation Instructions

| | Notebook Chat | Source Chat |
|---|---|---|
| Location | `chat/system.jinja` "# CITING INSTRUCTIONS" | `source_chat/system.jinja` "# CITING INSTRUCTIONS" + "## Citation Format" |
| Format | `[document_id]` — e.g. `[note:...]`, `[insight:...]`, `[source:...]` | `[source.id]` for source content; `[insight_id]` for insights |
| Scope of ids | Any note/insight/source in the injected context | The single source + its insight ids |
| Hard rules | "Use complete ID exactly, including type prefix; don't invent; don't change prefix" | Same spirit; "Only use IDs actually available in the context" |
| Vestigial wording | References ids "returned from the search tool" / "through the query you made" — **no such tool exists** | Pre-fills `[{{ source.id }}]` into the format spec itself |
| UI consumption | `notebookChatContextKey` cache + citation rendering (`frontend/src/lib/utils/source-references.tsx`) map ids → names | `context_indicators` (`source_chat.py:109-133`) returned via SSE `context_indicators` event |

Both rely entirely on the model echoing ids that were planted in the system message; there is no server-side citation validation at generation time.

---

## 10. Custom / User-editable Instructions

**NO dedicated USER-EDITABLE SYSTEM PROMPT FOUND.**

Searched for `custom_prompt`, `custom_instruction(s)`, `system_prompt`, `ai_instruction`, `behavior_instruction`, `chat_prompt`, `prompt_override`, "default prompt", DB-stored prompt settings — **none exist** for the chat flows. Prompt templates are flat files under `prompts/`, cached, with no DB-backed override layer and no admin editor.

**PARTIAL caveat (indirect influence):**
- **Notebook Chat:** `notebook.description` (and `name`) are **user-editable** DB fields (`PUT /notebooks/{id}`, `api/routers/notebooks.py:319-320`) that are rendered verbatim into the `# PROJECT INFORMATION` block of the system prompt. A user can therefore inject arbitrary free text into the notebook-chat system message through the description field — but this was designed as a descriptive label, not a prompt-control surface, and there is no precedence/override logic; it simply appears inside the otherwise-static template.
- **Source Chat:** `source.title` is user-editable and appears in `# SOURCE INFORMATION`; `source.topics` is AI-generated. Same indirect-injection property.

**Precedence:** the static template text is fixed and always present; the user-influenced strings are interpolated *into* fixed sections. Nothing lets a user replace or reorder the hardcoded instructions.

---

## 11. Notebook Chat vs Source Chat — Comparison

| Aspect | Notebook Chat | Source Chat |
|---|---|---|
| System template | `prompts/chat/system.jinja` | `prompts/source_chat/system.jinja` |
| API endpoint | `POST /chat/execute` (+ `POST /chat/context`) | `POST /sources/{id}/chat/sessions/{sid}/messages` (SSE) |
| Backend graph | `graphs/chat.py::call_model_with_messages` | `graphs/source_chat.py::call_model_with_source_context` |
| Context scope | User-selected sources+notes across the whole notebook | Exactly one source + its insights |
| Who builds context | Frontend triggers `build_notebook_context`; dict round-trips via request body | Backend builds it inside the graph |
| Retrieval | **None** (manual selection; `full/insights/not-in` per item) | **None** (direct single-source injection, 50k-token budget) |
| Source filtering | By explicit `context_config` selection | By `source_id` (URL + state + `refers_to` check) |
| Context form in prompt | Python **dict repr** of `{sources, notes}` | **Markdown** (`## SOURCE CONTENT` / `## SOURCE INSIGHTS`) |
| History | SqliteSaver checkpoint, full, system prepended | Same |
| Citation rules | `[document_id]` for notes/insights/sources | `[source.id]` + `[insight_id]`, source-scoped |
| Model invocation | `model.invoke` synchronous; `max_tokens=8192`, type `"chat"` | `model.invoke` synchronous, re-chunked to SSE; `max_tokens=8192`, type `"chat"` |
| Streaming | No | Pseudo-SSE (whole answer emitted as one `ai_message` event) |
| Custom instructions | Only via notebook name/description (indirect) | Only via source title (indirect) |
| Context indicators | Not tracked | Tracked + returned to UI |

**Meaningful differences:** (1) Notebook Chat's context is **user-curated and client-assembled**, then pushed back verbatim as a dict; Source Chat's context is **backend-assembled and auto-scoped** to one document with a real token budget. (2) Source Chat has an explicit single-source invariant enforced at the API/state/relation layers; Notebook Chat trusts whatever `context` the client posts. (3) Source Chat streams (SSE) and tracks `context_indicators`; Notebook Chat is a plain synchronous POST. (4) Both share the same model path, the same "no tools / no retrieval" reality, and the same "system message carries the context" structure.

---

## 12. Candidate Customization Seams (SAFEST places to change behavior later — NOT implemented)

| # | Seam | File / symbol | Blast radius | Mode | DB migration? | UI work? | Backward-compat risk |
|---|---|---|---|---|---|---|---|
| 1 | Edit the static template text | `prompts/chat/system.jinja` | All notebook-chat turns, all users | Notebook only | No | No | Low (text only); clears template cache → restart |
| 2 | Edit the static template text | `prompts/source_chat/system.jinja` | All source-chat turns | Source only | No | No | Low; restart needed |
| 3 | Add a new template variable + pass it in `data` | `graphs/chat.py:32` (`render(data=state)`) / `graphs/source_chat.py:139-147` | The one graph it is added to | Per-mode | No (unless value is DB-backed) | No | Low if `{% if %}`-guarded |
| 4 | Inject a per-notebook "AI instructions" field | new `Notebook` field + `chat/system.jinja` block + `notebooks` router | Notebook chat system prompt | Notebook only | **Yes** (new column + migration) | **Yes** (settings editor) | Medium (schema + API shape) |
| 5 | Inject a per-source "AI instructions" field | new `Source` field + `source_chat/system.jinja` | Source chat system prompt | Source only | **Yes** | **Yes** | Medium |
| 6 | Add a global/default system-prompt prefix | `provision_langchain_model` callers or a new wrapper around `SystemMessage` build (`chat.py:33`, `source_chat.py:150`) | Both flows (and anything reusing the wrapper) | Both | Optional (if DB-stored) | Optional | Medium — easy to double-inject |
| 7 | Change context formatting | `context_builder.py::format_source_context` (source) / the dict passed as `{{context}}` (notebook) | Context rendering only | Per-mode | No | No | Low–Medium (notebook ships a raw dict today; converting to a rendered string changes model input materially) |
| 8 | Add/limit model params (e.g. temperature) | `graphs/chat.py:45/64`, `graphs/source_chat.py:159/183` (`provision_langchain_model(... max_tokens=...)`) | Model behavior both flows | Both (change each site) | No | No | Low |
| 9 | Add real tools / retrieval | `graphs/chat.py` / `graphs/source_chat.py` (bind tools; cf. `ask.py:76`) | Large — changes the whole loop; the "search tool" wording would finally become true | Either/both | No | Possibly | **High** (changes invocation model, needs tool-calling-capable models) |
| 10 | Add a language/Vietnamese instruction | template edit (seam 1/2) or a new injected var (seam 3) | Output language | Per-mode | No | Optional (language selector) | Low |

**Safest, lowest-blast-radius starting points:** seams **1, 2, 3, 7, 8, 10** (pure template/graph edits, no schema, no UI). A DB-backed, user-editable custom prompt is seam **4/5** and requires migration + UI.

---

## 13. Open Questions / Ambiguities (not provable from static code alone)

1. **`ai_prompter.Prompter` default globals:** the library was not installed in this analysis environment, so I could not confirm whether `Prompter` auto-injects any implicit globals (e.g. `current_date`). **However**, neither `chat/system.jinja` nor `source_chat/system.jinja` references any such variable, so even if injected it is inert for these two templates. (The project's own `open_notebook/AGENTS.md` documents only `format_instructions` auto-injection, which applies when a parser is supplied — not used in chat.)
2. **`{{context}}` dict rendering (Notebook Chat):** the context is a Python dict handed to Jinja; statically it will be stringified via `str()`. I did not execute a live render to capture the exact repr (step 16 skipped — no installed deps / safe renderer without the `ai_prompter` package). The *structure* of each entry is proven from `Source.get_context`/`Note.get_context`.
3. **Client-supplied context trust (Notebook Chat):** `/chat/execute` accepts whatever `context` dict the client posts; the backend does not re-derive it from the notebook at execute time. A modified client could inject arbitrary context. This is a design observation, not a proven exploit path.
4. **Temperature / provider defaults:** no `temperature` is set in the chat code path; the effective value is whatever the Esperanto/LangChain provider defaults to — not determinable from this repo.
5. **Runtime probe (step 16):** **skipped.** No safe, dependency-free prompt renderer exists in-repo without installing `ai_prompter`/`esperanto` and standing up SurrealDB; running one would risk touching real config/DB. The exact templates and injected variables are nonetheless fully reconstructed above from source.

---

## Effective Prompt Reconstruction (placeholders for runtime values)

### NOTEBOOK CHAT
```
[system]
# SYSTEM ROLE … (full static text from §4)
# PROJECT INFORMATION
**Name:** {{notebook.name}}
**Description:** {{notebook.description}}
# CONTEXT
The user has selected this context to help you with your response:
{'sources': [{'id': 'source:…', 'title': '…', 'insights': [...], 'full_text': '…'}, …], 'notes': [{'id': 'note:…', 'title': '…', 'content': '…'}, …]}
# MATH FORMATTING … / # CITING INSTRUCTIONS … (static)

[human]  <prior user turn 1>
[ai]     <prior assistant turn 1>
…
[human]  <current user message>
```

### SOURCE CHAT
```
[system]
# SYSTEM ROLE … (full static text from §5)
# SOURCE INFORMATION
**Source ID:** source:…
**Title:** …
**Topics:** t1, t2, …            (only if topics present)
# SOURCE CONTEXT
## SOURCE CONTENT
**Source ID:** source:…
**Title:** …
**Content:**
<full_text or "[Source content truncated …]" or "[Source text is unavailable in this context.]">
## SOURCE INSIGHTS
**Insight ID:** insight:…
**Type:** <insight_type>
**Content:** <content>
# MATH FORMATTING … / # CITING INSTRUCTIONS … / # CONVERSATION FOCUS … (static)

[human]  <prior user turn 1>
[ai]     <prior assistant turn 1>
…
[human]  <current user message>
```

---

## 18. Chat Response Summary

```
NOTEBOOK_CHAT_SYSTEM_PROMPT   = prompts/chat/system.jinja
SOURCE_CHAT_SYSTEM_PROMPT     = prompts/source_chat/system.jinja

NOTEBOOK_CHAT_GRAPH           = open_notebook/graphs/chat.py :: call_model_with_messages
SOURCE_CHAT_GRAPH             = open_notebook/graphs/source_chat.py :: call_model_with_source_context (_inner)

MODEL_INVOCATION              = chat.py:73 (model.invoke) and source_chat.py:192 (model.invoke),
                                model built by open_notebook/ai/provision.py::provision_langchain_model
                                → open_notebook/ai/models.py::ModelManager.get_model/get_default_model
                                → Esperanto AIFactory.create_language(...).to_langchain()
                                params: default_type="chat", max_tokens=8192, no temperature set,
                                auto-upgrade to large_context model if token_count > 105_000

NOTEBOOK_CONTEXT_SCOPE        = User-selected sources+notes across the whole notebook; context built by
                                build_notebook_context (per-item: "not in"/"insights"/"full content"),
                                round-tripped through the frontend, injected into the SYSTEM message as a dict.
                                No retrieval, no vector search, no tools.

SOURCE_CONTEXT_SCOPE          = Exactly ONE source (source_id in URL + graph state + refers_to check) plus its
                                insights, built by build_source_context(max_tokens=50000) and rendered to Markdown,
                                injected into the SYSTEM message. Direct injection, no vector search, no tools.

USER_EDITABLE_SYSTEM_PROMPT   = PARTIAL — No dedicated custom-prompt field exists. Notebook name/description and
                                source title are user-editable strings interpolated into fixed template sections;
                                there is no override/replace mechanism.

MOST_IMPORTANT_DIFFERENCE     = Notebook Chat's context is user-curated and ASSEMBLED ON THE CLIENT, then POSTed
                                back verbatim as a dict the backend trusts; Source Chat's context is BUILT ON THE
                                BACKEND and auto-scoped to a single source (enforced at the API route, the graph
                                state's source_id, and the refers_to relation check) with a real 50k-token budget
                                and truncation. Both inject context into the system message and bind no tools, so
                                the templates' "search tool"/"query" wording is vestigial in both.

SAFE_CUSTOMIZATION_SEAMS      = 1) edit prompts/chat/system.jinja (notebook, no schema/UI)
                                2) edit prompts/source_chat/system.jinja (source, no schema/UI)
                                3) add a guarded {% if %} var via render(data=...) in each graph
                                7) change context formatting (format_source_context / the notebook context dict)
                                8) set model params (max_tokens/temperature) at the provision_langchain_model calls
                                10) add a language/Vietnamese directive via template or injected var
                                — DB-backed user-editable prompt = seams 4/5 (require migration + UI).
```

---

CHAT_SYSTEM_PROMPT_FORENSIC_COMPLETE
