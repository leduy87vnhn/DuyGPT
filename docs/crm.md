# Customer Requirement Management (CRM)

An admin-only module inside DuyGPT for tracking customer requirements across multiple products (e.g. Production Auto Planning, Smart Warehouse Management System, MES). One customer can use several products; every record is scoped to a `(customer, product)` pair. It reuses the same LLM, Postgres, and RAG embedding setup already configured for DuyGPT — no extra service.

## Access

```text
http://<duygpt-host>:8383/crm
```

Requires an `admin_user` session (same login as the rest of DuyGPT). Non-admin accounts get a 403 from every `/api/crm/*` endpoint and see a "not admin" notice on the page.

## Data model

- **Customers** and **Products** are independent catalogs. Pick one of each in the sidebar to open a workspace for that pair.
- **Hiện trạng & Yêu cầu (requirements)** — a running log of current-state/requirement entries per customer+product. Not versioned; just an append-only log you can delete individual entries from.
- **Tài liệu (documents)** — memos and đề án files (`.txt`, `.md`, `.pdf`, `.docx`, `.pptx`, `.xlsx`), uploaded the same way as DuyGPT's existing RAG document upload (JSON + base64, `MAX_UPLOAD_MB` limit). Extraction is shared with `rag.py` (`extract_text`/`guess_content_type`), so this list stays in sync with whatever the main chat's admin document upload supports. Each document has a **title**: uploading a new file with the same title for the same customer+product creates a new **version** and marks the old one non-current (it isn't deleted, just hidden from the default list — toggle "Hiện tất cả phiên bản" to see history). This is the "khi update sẽ upload bản mới" behavior. Deleting the current version promotes the next-newest version back to current automatically.
- **Đề xuất (proposals)** — drafted separately from raw requirements. A proposal starts as `draft`, is editable while a draft, and only becomes the one used for implementation when explicitly **chốt** (finalized) via the UI. Finalizing a proposal automatically marks any previously finalized proposal for that same customer+product as `superseded` — there is at most one finalized/authoritative proposal per customer+product at a time. A customer+product can have any number of proposals over time.
  - **Active / inactive**: independent of `draft`/`finalized`/`superseded`, every proposal has an `is_active` flag (default active), toggled from the UI. Marking an old proposal inactive removes it (and its attachments) from search/consult results without deleting it — history stays intact.
  - **Attachments**: each proposal can have multiple file attachments, **`.docx`, `.pptx`, `.xlsx`, and `.pdf` only** (rejected otherwise). Content is extracted (paragraphs + tables for docx; slide text + tables for pptx; every sheet's rows for xlsx; page text for pdf), chunked, embedded, and stored in Postgres the same way as the memo/đề án library, so it's searchable. Adding/removing an attachment bumps the proposal's `updated_at`. Every proposal record tracks `created_at` and `updated_at`.

## Tra cứu / tư vấn (search and consult)

The "Tư vấn AI" panel is a chat scoped to the selected customer+product. It has read access to that pair's data plus one write action, via tool-calling:

| Tool | Purpose |
| --- | --- |
| `list_requirements` | Recent hiện trạng/yêu cầu entries. |
| `search_documents` | Semantic (pgvector) search over the **current** version of every memo/đề án document, plus every attachment file of every **active** proposal, for this customer+product. Nothing outside uploaded files is used — if nothing matches, the agent is instructed to say so rather than guess. |
| `list_documents` | Document titles/types (metadata only). |
| `list_proposals` | Existing proposals — status, active/inactive, attachment count. |
| `save_draft_proposal` | Saves the assistant's suggestion as a new **draft** proposal. |

The agent is deliberately not given a "finalize" or "set active" tool — chốt and inactive/active toggling are always manual clicks in the UI, never autonomous chat actions, so an implementation-authoritative proposal always has an explicit human decision behind it.

Chat history for this module is stored the same way as the family assistant (`conversations.kind = 'crm'`), but the UI does not currently browse old CRM conversations — each time you (re)select a customer+product the chat starts fresh. The durable output of a conversation is whatever gets saved into requirements/documents/proposals, not the chat transcript itself.

## API

All endpoints require an admin session.

```http
GET/POST   /api/crm/customers
PUT/DELETE /api/crm/customers/<id>

GET/POST   /api/crm/products
DELETE     /api/crm/products/<id>

GET/POST   /api/crm/requirements?customer_id=&product_id=
PUT/DELETE /api/crm/requirements/<id>

GET/POST   /api/crm/documents?customer_id=&product_id=[&all=1]
DELETE     /api/crm/documents/<id>
```

Document upload body:

```json
{
  "customer_id": 1,
  "product_id": 1,
  "doc_type": "memo",
  "title": "Memo khảo sát hiện trạng kho",
  "filename": "memo.txt",
  "content_base64": "..."
}
```

```http
GET/POST      /api/crm/proposals?customer_id=&product_id=
PUT/DELETE    /api/crm/proposals/<id>                    (edit, draft only)
PUT           /api/crm/proposals/<id>/finalize
PUT           /api/crm/proposals/<id>/active             body: {"active": true|false}

GET/POST      /api/crm/proposals/<id>/attachments        (.docx/.pptx/.xlsx/.pdf only)
DELETE        /api/crm/proposals/<id>/attachments/<attachment_id>

POST          /api/crm/chat
```

Attachment upload body (same base64 shape as document upload, filename must end in `.docx`, `.pptx`, `.xlsx`, or `.pdf`):

```json
{"filename": "de-xuat-giai-doan-1.docx", "content_base64": "..."}
```

Chat body/response follow the same shape as `/api/home/chat`, plus `customer_id`/`product_id`:

```json
{"customer_id": 1, "product_id": 1, "message": "...", "conversation_id": null}
```

## Configuration

```env
CRM_MODEL=
CRM_MAX_TOOL_ITERATIONS=6
CRM_CONTEXT_MESSAGES=20
```

`CRM_MODEL` lets this module use a different model than the main chat (leave empty to reuse `MODEL`, same pattern as `HOME_ASSISTANT_MODEL`). Tool calling requires a model that supports it (Qwen2.5/Qwen3-Instruct via Ollama do).

Document search reuses `EMBEDDING_MODEL`/`EMBEDDING_DIM` — the same Ollama embedding model already required for the main RAG document feature.

## Lịch làm việc (personal work schedule)

A separate small feature living in the same `/crm` page (top panel, always visible — not gated behind picking a customer+product): a personal work calendar with **time + location + customer + nội dung công việc**. It belongs to the admin account (there is one business owner using this module) and is built for a future voice assistant / Raspberry Pi display to query "where am I right now."

```http
GET/POST   /api/schedule?from=&to=      (admin session; from/to optional ISO 8601 filters)
PUT/DELETE /api/schedule/<id>           (admin session)

GET /api/schedule/location?at=2026-08-23T15:00:00   (session OR X-Device-Key, like /api/chat)
```

`POST /api/schedule` body:

```json
{
  "customer_id": 1,
  "title": "Khảo sát hiện trạng kho",
  "location": "Nhà máy Công ty ABC, Bình Dương",
  "start_at": "2026-08-23T14:00:00",
  "end_at": "2026-08-23T16:00:00"
}
```

`customer_id` is optional (internal work with no customer visit). `GET /api/schedule/location` returns the schedule entry whose `[start_at, end_at]` covers `at` (default: now), e.g.:

```json
{"found": true, "id": 1, "title": "...", "location": "...", "customer_name": "...", "start_at": "...", "end_at": "...", "at": "..."}
```

or `{"found": false, "at": "..."}` if nothing is scheduled at that moment. This endpoint accepts the same `X-Device-Key` header used by the existing voice/speaker API, so a future Raspberry Pi display or voice assistant can call it without a browser session — see [Speaker Device API](speaker-api.md).

Editing an existing entry isn't in the UI yet — delete and re-add if a time/location changes. The API (`PUT /api/schedule/<id>`) already supports it if you want to script it or add the UI control later.

## Scoping note

Customers and products are global catalogs, not owned by a particular DuyGPT user account — any admin can see and edit all of them. If you need per-admin isolation later (e.g. multiple consultants each with their own customer books), that would need an `owner_id` added to `crm_customers` — ask if you want that.
