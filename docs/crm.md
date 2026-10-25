# Customer Requirement Management (CRM)

A permission-controlled module inside DuyGPT for tracking customer requirements across multiple products (e.g. Production Auto Planning, Smart Warehouse Management System, MES). One customer can use several products; every record is scoped to a `(customer, product)` pair. It reuses the same LLM, Postgres, and RAG embedding setup already configured for DuyGPT — no extra service.

## Access

```text
http://<duygpt-host>:8383/crm
```

Requires a logged-in account with CRM access (`crm_access` or `admin_user`). Module access does not grant access to other users' customers, including for admins.

Customers are private to their creator. In **Khách hàng**, the owner can click **Share**, tick specific users, and save. Recipients can read the customer's requirements, original documents and versions, proposals, and consult the AI. Only the owner can upload, edit, delete, mark requirements complete, or change sharing. Unticking a user revokes their access on subsequent requests. The chooser lists accounts with CRM module access; it does not grant that module permission itself.

Existing customers retain their recorded creator as owner; historical rows without an owner use the existing migration's admin assignment. No automatic shares are created. The product catalog remains common, but only the creator can delete an unused product; products referenced by customer data cannot be deleted.

## Data model

- **Customers** and **Products** are independent catalogs. Pick one of each in the sidebar to open a workspace for that pair.
- **Hiện trạng & Yêu cầu (requirements)** — a running log of current-state/requirement entries per customer+product. Manual entries remain independent. The list also includes AI requirements from the latest version of each uploaded document; older snapshots remain available under Documents.
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

Chat history is bound to the authenticated user, customer and product. Unscoped historical CRM conversations are retained in the database but hidden and never reused; revoked shares also block history retrieval. Chat history for this module is stored the same way as the family assistant (`conversations.kind = 'crm'`), but the UI does not currently browse old CRM conversations — each time you (re)select a customer+product the chat starts fresh. The durable output of a conversation is whatever gets saved into requirements/documents/proposals, not the chat transcript itself.

## API

All endpoints require a CRM-enabled session. Customer-scoped reads require ownership or an explicit share; writes require ownership.

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


## Memo versions and requirement checklists

- Uploading the same filename within a customer/product creates a new version, even if the display title changes. Matching titles still group files with different filenames for compatibility.
- New uploads retain the original bytes and extracted text. **Xem nội dung raw** shows the extracted text; **Tải file gốc** downloads the exact uploaded file. Historical uploads only have RAG chunks, so their preview is reconstructed text (possibly overlapping), not the original file.
- Each upload automatically calls the configured CRM AI model and creates a complete requirement snapshot for that file version. The latest file is treated as the complete replacement for its previous version, not an incremental amendment. Requirements absent from the replacement no longer appear in the latest list; historical snapshots are retained.
- **Danh sách requirement** opens a particular version's checklist and source quotations. **Hiện tất cả phiên bản** includes historical files. **Hiện trạng & Yêu cầu** combines the latest snapshot of each document with manual entries.
- Each requirement has a **To Do / Progress / Done / Rejected** select. Status edits affect only that file version. On migration, old checked items become Done and unchecked items become To Do. An unchanged requirement inherits its previous version's status unless the new source explicitly marks it completed (Done) or unfinished (To Do). New/reworded items default to To Do. The legacy `completed` API boolean remains synchronized with Done for older clients.
- Requirement extraction allows up to 1,800 seconds (30 minutes) for each AI request, for both new uploads and manual analysis of older files. Long files may require several requests. Other chat requests retain their existing timeout.
- Ollama requirement extraction uses a JSON response schema, smaller source chunks, and bounded automatic retries. The model selects numbered source lines; the server reconstructs quotations from the original text to preserve spelling and avoid model-rewritten quotations. Malformed or truncated output is retried; repeatedly failing chunks are split further. A partial JSON response is never saved as a complete requirement snapshot.
- AI errors do not discard the uploaded file. Open its checklist and click **Tạo danh sách Requirement** directly on an uploaded file (or inside its checklist) to analyze a historical file or retry a failed analysis. The button is available to the customer owner for versions without a successfully generated snapshot. Successful snapshots are not regenerated by retries. A warning on the latest requirement list identifies documents not yet analyzed; failed versions do not silently fall back to an older snapshot.
- Analysis covers all extracted text in overlapping chunks, checks that each returned requirement cites source text, and removes exact duplicate requirement descriptions. Semantic duplicates or mistakes still require human review. Scanned PDFs without text need OCR before upload.
- Restart DuyGPT to apply the additive schema migration automatically. Existing CRM access permissions apply to previews, downloads, analysis, status updates and deletion.

Verification: `DUYGPT_RUN_DB_TESTS=1 .venv/bin/python -m unittest discover -s tests -v` uses a temporary PostgreSQL schema and mocked AI/embedding responses, leaving live tables untouched.


### Customer sharing API

- `GET /api/crm/customers/:id/shares`: owner-only list of eligible user IDs, usernames and selected sharing checkboxes.
- `PUT /api/crm/customers/:id/shares` with `{"user_ids": [2, 3]}`: replace the owner's explicit reader list. An empty list revokes all shares.
- `GET /api/crm/customers` only returns owned/shared customers with `is_owner` to drive editing controls.
- Unauthorized or nonexistent customer objects both return 404; IDs in download, checklist and attachment URLs are checked against their actual parent customer. CRM agent tools enforce the same permissions and do not expose write tools to shared readers.
- Restart DuyGPT to apply the additive sharing/history migration. Tests cover independent users (including an unrelated admin), sharing/revocation, direct URL access, read-only restrictions, conversation isolation and schedule customer-name access.


### Requirement editing and source context

- Owners can delete one generated requirement or use the trash icon **Xóa tất cả requirement** on a file/version or its requirement panel. Both actions ask for confirmation. Only the selected version's requirements are removed; original files, manual entries and other versions remain unchanged. Deleting all requirements leaves an intentionally empty analyzed snapshot; retrying analysis does not silently recreate deleted items.
- Requirement cards display the source passage with two lines of surrounding text on each side and line numbers where available. **Xem toàn bộ nội dung file** expands the full extracted source for that version. If an old quotation cannot be located, the saved quotation is displayed without invented context or line numbers.
- Shared readers can see status and context but cannot edit status or delete requirements.
- `PUT /api/crm/document-requirements/:id` accepts `{"status":"todo|progress|done|rejected"}` (choose one value).
- `DELETE /api/crm/document-requirements/:id` removes one item; `DELETE /api/crm/documents/:id/requirements` removes the selected version's entire generated list.


### Application context extracted by AI

During requirement extraction, the model identifies the **target file**, **screen**, and **module** for each requirement. These are the application objects affected by the requirement, not the Memo filename or surrounding quotation. Names must be copied from cited source lines; unknown fields remain empty and the UI shows **Chưa xác định**. Source quotations remain separately available under **Trích dẫn tài liệu**.

The extractor supplies earlier section/heading cues and nearby text to help retain context across chunk boundaries, while only extracting requirements from the current chunk. It stores `target_file`, `target_screen`, `target_module`, and `target_evidence` with each versioned requirement. Duplicate detection and status inheritance compare both requirement text and target context, so identical requests for different screens remain separate.

The additive migration preserves existing requirements, statuses and deletions. Historical requirements receive empty context fields; they are not relabeled by guessing or automatically regenerated. Context identification applies to new extraction runs (new uploads and files that have not yet been successfully analyzed). Restart the server to apply the migration and extraction changes.
