"""Quan Ly Yeu Cau Khach Hang: customer requirement management, admin-only.

Tracks, per (customer, product) pair: hien trang/yeu cau entries, versioned
memo/de an documents (RAG-searchable via pgvector, same approach as rag.py),
and de xuat (proposal) records with an explicit "chot" (finalize) step -- the
finalized proposal is the one treated as authoritative for implementation.
Each proposal can carry multiple docx/pptx/xlsx/pdf attachments, extracted and
RAG-indexed the same way, and can be marked inactive once superseded/stale.
"""
import json

import llm_tools
import rag

DEFAULT_SYSTEM_PROMPT_TEMPLATE = (
    "Bạn là trợ lý tư vấn nghiệp vụ nội bộ, phân tích hiện trạng và yêu cầu của khách hàng "
    "\"{customer}\" cho sản phẩm \"{product}\", dựa trên dữ liệu đã lưu (yêu cầu, tài liệu/memo, file đính kèm trong các đề xuất). "
    "CHỈ dùng thông tin lấy được từ công cụ (tool) hoặc phần ngữ cảnh được cung cấp, tuyệt đối không bịa đặt chi tiết không có trong tài liệu đã upload. "
    "search_documents chỉ tìm trong nội dung các file đã upload (memo/tài liệu và file đính kèm docx/pptx/xlsx/pdf của các đề xuất đang active) -- nếu không tìm thấy thông tin liên quan, hãy nói rõ là chưa có tài liệu đề cập, đừng suy đoán. "
    "Khi được yêu cầu tư vấn/đề xuất giải pháp: phân tích hiện trạng và yêu cầu, dùng search_documents để tra thêm tài liệu liên quan nếu cần, "
    "rồi đưa ra đề xuất rõ ràng, có cấu trúc (gạch đầu dòng khi phù hợp). "
    "Nếu người dùng đồng ý và muốn lưu đề xuất, dùng tool save_draft_proposal để lưu thành bản NHÁP. "
    "Luôn nhắc rõ: bản nháp chỉ trở thành đề xuất chính thức để triển khai khi người dùng bấm \"chốt\" trên giao diện, không phải qua chat. "
    "Đề xuất cũ/không còn phù hợp sẽ được người dùng đánh dấu \"inactive\" trên giao diện -- các đề xuất đó không còn được tính vào kết quả tìm kiếm. "
    "Trả lời bằng tiếng Việt, chuyên nghiệp, ngắn gọn."
)


def system_prompt(customer_name, product_name):
    return DEFAULT_SYSTEM_PROMPT_TEMPLATE.format(customer=customer_name, product=product_name)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_requirements",
            "description": "Liệt kê các mục hiện trạng/yêu cầu đã ghi nhận cho khách hàng và sản phẩm đang tư vấn.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "Tìm kiếm ngữ nghĩa trong nội dung memo/tài liệu đã upload VÀ file đính kèm (docx/pptx/xlsx/pdf) của các đề xuất đang active, cho khách hàng và sản phẩm đang tư vấn. Chỉ trả về nội dung có thật trong file đã upload.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Nội dung cần tìm."},
                    "top_k": {"type": "integer", "description": "Số đoạn kết quả tối đa, mặc định 4."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_documents",
            "description": "Liệt kê danh sách tài liệu (memo/đề án) hiện có, không kèm nội dung chi tiết.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_proposals",
            "description": "Liệt kê các đề xuất (nháp/đã chốt/đã thay thế, active/inactive) đã có cho khách hàng và sản phẩm đang tư vấn, kèm số lượng file đính kèm.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_draft_proposal",
            "description": "Lưu một đề xuất mới ở dạng NHÁP. Không tự động chốt/triển khai.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string", "description": "Nội dung đề xuất, nên có cấu trúc rõ ràng."},
                },
                "required": ["title", "content"],
            },
        },
    },
]


# --- Customers ---


def _customer_dict(row):
    return {"id": row[0], "name": row[1], "notes": row[2], "created_at": row[3].isoformat()}


def create_customer(pool, user_id, name, notes=""):
    name = (name or "").strip()
    if not name:
        return {"error": "name is required"}
    with pool.connection() as conn:
        row = conn.execute(
            "INSERT INTO crm_customers (user_id, name, notes) VALUES (%s, %s, %s) RETURNING id, name, notes, created_at",
            (user_id, name, (notes or "").strip()),
        ).fetchone()
    return _customer_dict(row)


def list_customers(pool):
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT id, name, notes, created_at FROM crm_customers ORDER BY name ASC"
        ).fetchall()
    return [_customer_dict(row) for row in rows]


def update_customer(pool, customer_id, name, notes):
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE crm_customers SET name = %s, notes = %s WHERE id = %s "
            "RETURNING id, name, notes, created_at",
            ((name or "").strip(), (notes or "").strip(), customer_id),
        ).fetchone()
    if not row:
        return {"error": "customer not found"}
    return _customer_dict(row)


def get_customer(pool, customer_id):
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT id, name, notes, created_at FROM crm_customers WHERE id = %s", (customer_id,)
        ).fetchone()
    return _customer_dict(row) if row else None


def delete_customer(pool, customer_id):
    with pool.connection() as conn:
        row = conn.execute("DELETE FROM crm_customers WHERE id = %s RETURNING id", (customer_id,)).fetchone()
    return {"deleted": bool(row), "id": customer_id}


# --- Products ---


def _product_dict(row):
    return {"id": row[0], "name": row[1], "description": row[2], "created_at": row[3].isoformat()}


def create_product(pool, user_id, name, description=""):
    name = (name or "").strip()
    if not name:
        return {"error": "name is required"}
    with pool.connection() as conn:
        row = conn.execute(
            "INSERT INTO crm_products (user_id, name, description) VALUES (%s, %s, %s) "
            "ON CONFLICT (name) DO NOTHING RETURNING id, name, description, created_at",
            (user_id, name, (description or "").strip()),
        ).fetchone()
    if not row:
        return {"error": "a product with this name already exists"}
    return _product_dict(row)


def list_products(pool):
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT id, name, description, created_at FROM crm_products ORDER BY name ASC"
        ).fetchall()
    return [_product_dict(row) for row in rows]


def get_product(pool, product_id):
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT id, name, description, created_at FROM crm_products WHERE id = %s", (product_id,)
        ).fetchone()
    return _product_dict(row) if row else None


def delete_product(pool, product_id):
    with pool.connection() as conn:
        row = conn.execute("DELETE FROM crm_products WHERE id = %s RETURNING id", (product_id,)).fetchone()
    return {"deleted": bool(row), "id": product_id}


# --- Requirements (hien trang / yeu cau) ---


def _requirement_dict(row):
    return {
        "id": row[0],
        "customer_id": row[1],
        "product_id": row[2],
        "current_state": row[3],
        "requirement": row[4],
        "created_at": row[5].isoformat(),
        "updated_at": row[6].isoformat(),
    }


def add_requirement(pool, customer_id, product_id, current_state, requirement, user_id):
    current_state = (current_state or "").strip()
    requirement = (requirement or "").strip()
    if not current_state and not requirement:
        return {"error": "current_state or requirement is required"}
    with pool.connection() as conn:
        row = conn.execute(
            "INSERT INTO crm_requirements (customer_id, product_id, current_state, requirement, created_by) "
            "VALUES (%s, %s, %s, %s, %s) "
            "RETURNING id, customer_id, product_id, current_state, requirement, created_at, updated_at",
            (customer_id, product_id, current_state, requirement, user_id),
        ).fetchone()
    return _requirement_dict(row)


def list_requirements(pool, customer_id, product_id, limit=50):
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT id, customer_id, product_id, current_state, requirement, created_at, updated_at "
            "FROM crm_requirements WHERE customer_id = %s AND product_id = %s "
            "ORDER BY created_at DESC LIMIT %s",
            (customer_id, product_id, limit),
        ).fetchall()
    return [_requirement_dict(row) for row in rows]


def update_requirement(pool, requirement_id, current_state, requirement):
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE crm_requirements SET current_state = %s, requirement = %s, updated_at = now() "
            "WHERE id = %s "
            "RETURNING id, customer_id, product_id, current_state, requirement, created_at, updated_at",
            ((current_state or "").strip(), (requirement or "").strip(), requirement_id),
        ).fetchone()
    if not row:
        return {"error": "requirement not found"}
    return _requirement_dict(row)


def delete_requirement(pool, requirement_id):
    with pool.connection() as conn:
        row = conn.execute(
            "DELETE FROM crm_requirements WHERE id = %s RETURNING id", (requirement_id,)
        ).fetchone()
    return {"deleted": bool(row), "id": requirement_id}


# --- Documents (memo / de an, versioned + RAG-chunked) ---


def _document_dict(row):
    return {
        "id": row[0],
        "customer_id": row[1],
        "product_id": row[2],
        "doc_type": row[3],
        "title": row[4],
        "filename": row[5],
        "content_type": row[6],
        "version": row[7],
        "is_current": row[8],
        "created_at": row[9].isoformat(),
    }


def ingest_document(pool, customer_id, product_id, doc_type, title, filename, content_type, raw_bytes, uploaded_by):
    title = (title or filename or "Untitled").strip()
    text = rag.extract_text(filename, raw_bytes)
    chunks = rag.chunk_text(text)
    with pool.connection() as conn:
        previous = conn.execute(
            "SELECT version FROM crm_documents WHERE customer_id = %s AND product_id = %s "
            "AND title = %s AND is_current = TRUE",
            (customer_id, product_id, title),
        ).fetchone()
        next_version = (previous[0] + 1) if previous else 1
        if previous:
            conn.execute(
                "UPDATE crm_documents SET is_current = FALSE WHERE customer_id = %s AND product_id = %s "
                "AND title = %s AND is_current = TRUE",
                (customer_id, product_id, title),
            )
        document_id = conn.execute(
            "INSERT INTO crm_documents "
            "(customer_id, product_id, doc_type, title, filename, content_type, version, is_current, uploaded_by) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, %s) RETURNING id",
            (customer_id, product_id, doc_type, title, filename, content_type, next_version, uploaded_by),
        ).fetchone()[0]
        for index, chunk in enumerate(chunks):
            vector = rag.embed(chunk)
            conn.execute(
                "INSERT INTO crm_document_chunks (document_id, chunk_index, content, embedding) "
                "VALUES (%s, %s, %s, %s)",
                (document_id, index, chunk, rag.vector_literal(vector)),
            )
    return {"id": document_id, "title": title, "version": next_version, "chunks": len(chunks)}


def list_documents(pool, customer_id, product_id, include_all_versions=False):
    query = (
        "SELECT id, customer_id, product_id, doc_type, title, filename, content_type, version, is_current, created_at "
        "FROM crm_documents WHERE customer_id = %s AND product_id = %s "
        + ("" if include_all_versions else "AND is_current = TRUE ")
        + "ORDER BY title ASC, version DESC"
    )
    with pool.connection() as conn:
        rows = conn.execute(query, (customer_id, product_id)).fetchall()
    return [_document_dict(row) for row in rows]


def delete_document(pool, document_id):
    with pool.connection() as conn:
        doc = conn.execute(
            "SELECT customer_id, product_id, title, is_current FROM crm_documents WHERE id = %s",
            (document_id,),
        ).fetchone()
        if not doc:
            return {"deleted": False, "id": document_id}
        conn.execute("DELETE FROM crm_documents WHERE id = %s", (document_id,))
        if doc[3]:
            promoted = conn.execute(
                "SELECT id FROM crm_documents WHERE customer_id = %s AND product_id = %s AND title = %s "
                "ORDER BY version DESC LIMIT 1",
                (doc[0], doc[1], doc[2]),
            ).fetchone()
            if promoted:
                conn.execute("UPDATE crm_documents SET is_current = TRUE WHERE id = %s", (promoted[0],))
    return {"deleted": True, "id": document_id}


def retrieve_document_context(pool, customer_id, product_id, query, top_k=4):
    try:
        vector = rag.embed(query)
    except Exception:
        return []
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT d.title, c.content, c.embedding <=> %s AS distance "
            "FROM crm_document_chunks c JOIN crm_documents d ON d.id = c.document_id "
            "WHERE d.customer_id = %s AND d.product_id = %s AND d.is_current = TRUE "
            "ORDER BY distance ASC LIMIT %s",
            (rag.vector_literal(vector), customer_id, product_id, top_k),
        ).fetchall()
    return [{"source": "document", "title": row[0], "content": row[1]} for row in rows]


def retrieve_proposal_attachment_context(pool, customer_id, product_id, query, top_k=4):
    try:
        vector = rag.embed(query)
    except Exception:
        return []
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT p.title, a.filename, c.content, c.embedding <=> %s AS distance "
            "FROM crm_proposal_attachment_chunks c "
            "JOIN crm_proposal_attachments a ON a.id = c.attachment_id "
            "JOIN crm_proposals p ON p.id = a.proposal_id "
            "WHERE p.customer_id = %s AND p.product_id = %s AND p.is_active = TRUE "
            "ORDER BY distance ASC LIMIT %s",
            (rag.vector_literal(vector), customer_id, product_id, top_k),
        ).fetchall()
    return [
        {"source": "proposal", "title": f"{row[0]} ({row[1]})", "content": row[2]} for row in rows
    ]


def retrieve_context(pool, customer_id, product_id, query, top_k=4):
    """Combined semantic search over both the memo/de an library and active proposal attachments."""
    combined = retrieve_document_context(pool, customer_id, product_id, query, top_k) + \
        retrieve_proposal_attachment_context(pool, customer_id, product_id, query, top_k)
    return combined[:top_k] if len(combined) > top_k else combined


# --- Proposal attachments (docx / pptx / xlsx / pdf only, RAG-chunked) ---

# Proposal attachments intentionally only accept office + PDF formats (not
# txt/md, unlike the general memo/de an document library below) -- extraction
# itself is shared with rag.py so both paths stay in sync.
ALLOWED_ATTACHMENT_EXTENSIONS = (".docx", ".pptx", ".xlsx", ".pdf")
ATTACHMENT_ERROR = "only .docx, .pptx, .xlsx, and .pdf attachments are supported"


def _attachment_extension(filename):
    lower = filename.lower()
    for ext in ALLOWED_ATTACHMENT_EXTENSIONS:
        if lower.endswith(ext):
            return ext
    return None


def _attachment_dict(row):
    return {
        "id": row[0],
        "proposal_id": row[1],
        "filename": row[2],
        "content_type": row[3],
        "created_at": row[4].isoformat(),
    }


def ingest_proposal_attachment(pool, proposal_id, filename, raw_bytes, uploaded_by):
    filename = (filename or "").strip()
    if not _attachment_extension(filename):
        return {"error": ATTACHMENT_ERROR}
    text = rag.extract_text(filename, raw_bytes)
    chunks = rag.chunk_text(text)
    content_type = rag.guess_content_type(filename)
    with pool.connection() as conn:
        proposal = conn.execute("SELECT id FROM crm_proposals WHERE id = %s", (proposal_id,)).fetchone()
        if not proposal:
            return {"error": "proposal not found"}
        attachment_id = conn.execute(
            "INSERT INTO crm_proposal_attachments (proposal_id, filename, content_type, uploaded_by) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (proposal_id, filename, content_type, uploaded_by),
        ).fetchone()[0]
        for index, chunk in enumerate(chunks):
            vector = rag.embed(chunk)
            conn.execute(
                "INSERT INTO crm_proposal_attachment_chunks (attachment_id, chunk_index, content, embedding) "
                "VALUES (%s, %s, %s, %s)",
                (attachment_id, index, chunk, rag.vector_literal(vector)),
            )
        conn.execute("UPDATE crm_proposals SET updated_at = now() WHERE id = %s", (proposal_id,))
    return {"id": attachment_id, "filename": filename, "chunks": len(chunks)}


def list_proposal_attachments(pool, proposal_id):
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT id, proposal_id, filename, content_type, created_at "
            "FROM crm_proposal_attachments WHERE proposal_id = %s ORDER BY created_at ASC",
            (proposal_id,),
        ).fetchall()
    return [_attachment_dict(row) for row in rows]


def delete_proposal_attachment(pool, attachment_id):
    with pool.connection() as conn:
        row = conn.execute(
            "DELETE FROM crm_proposal_attachments WHERE id = %s RETURNING proposal_id", (attachment_id,)
        ).fetchone()
        if row:
            conn.execute("UPDATE crm_proposals SET updated_at = now() WHERE id = %s", (row[0],))
    return {"deleted": bool(row), "id": attachment_id}


# --- Proposals (de xuat) ---


def _proposal_dict(row, attachments=None):
    return {
        "id": row[0],
        "customer_id": row[1],
        "product_id": row[2],
        "title": row[3],
        "content": row[4],
        "status": row[5],
        "is_active": row[6],
        "version": row[7],
        "created_at": row[8].isoformat(),
        "updated_at": row[9].isoformat(),
        "finalized_at": row[10].isoformat() if row[10] else None,
        "attachments": attachments if attachments is not None else [],
    }


_PROPOSAL_COLUMNS = (
    "id, customer_id, product_id, title, content, status, is_active, version, created_at, updated_at, finalized_at"
)


def create_proposal(pool, customer_id, product_id, title, content, user_id):
    content = (content or "").strip()
    if not content:
        return {"error": "content is required"}
    with pool.connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM crm_proposals WHERE customer_id = %s AND product_id = %s",
            (customer_id, product_id),
        ).fetchone()[0]
        row = conn.execute(
            "INSERT INTO crm_proposals (customer_id, product_id, title, content, version, created_by) "
            f"VALUES (%s, %s, %s, %s, %s, %s) RETURNING {_PROPOSAL_COLUMNS}",
            (customer_id, product_id, (title or "").strip(), content, count + 1, user_id),
        ).fetchone()
    return _proposal_dict(row)


def list_proposals(pool, customer_id, product_id):
    with pool.connection() as conn:
        rows = conn.execute(
            f"SELECT {_PROPOSAL_COLUMNS} FROM crm_proposals WHERE customer_id = %s AND product_id = %s "
            "ORDER BY created_at DESC",
            (customer_id, product_id),
        ).fetchall()
    return [_proposal_dict(row, list_proposal_attachments(pool, row[0])) for row in rows]


def update_proposal(pool, proposal_id, title, content):
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE crm_proposals SET title = %s, content = %s, updated_at = now() "
            f"WHERE id = %s AND status = 'draft' RETURNING {_PROPOSAL_COLUMNS}",
            ((title or "").strip(), (content or "").strip(), proposal_id),
        ).fetchone()
    if not row:
        return {"error": "proposal not found or is not a draft"}
    return _proposal_dict(row, list_proposal_attachments(pool, proposal_id))


def set_proposal_active(pool, proposal_id, active):
    with pool.connection() as conn:
        row = conn.execute(
            "UPDATE crm_proposals SET is_active = %s, updated_at = now() WHERE id = %s "
            f"RETURNING {_PROPOSAL_COLUMNS}",
            (bool(active), proposal_id),
        ).fetchone()
    if not row:
        return {"error": "proposal not found"}
    return _proposal_dict(row, list_proposal_attachments(pool, proposal_id))


def finalize_proposal(pool, proposal_id):
    with pool.connection() as conn:
        target = conn.execute(
            "SELECT customer_id, product_id FROM crm_proposals WHERE id = %s", (proposal_id,)
        ).fetchone()
        if not target:
            return {"error": "proposal not found"}
        conn.execute(
            "UPDATE crm_proposals SET status = 'superseded' "
            "WHERE customer_id = %s AND product_id = %s AND status = 'finalized' AND id != %s",
            (target[0], target[1], proposal_id),
        )
        row = conn.execute(
            "UPDATE crm_proposals SET status = 'finalized', finalized_at = now() WHERE id = %s "
            f"RETURNING {_PROPOSAL_COLUMNS}",
            (proposal_id,),
        ).fetchone()
    return _proposal_dict(row, list_proposal_attachments(pool, proposal_id))


def delete_proposal(pool, proposal_id):
    with pool.connection() as conn:
        row = conn.execute("DELETE FROM crm_proposals WHERE id = %s RETURNING id", (proposal_id,)).fetchone()
    return {"deleted": bool(row), "id": proposal_id}


# --- Consultation agent ---


def _tool_list_requirements(pool, customer_id, product_id, arguments):
    return {"requirements": list_requirements(pool, customer_id, product_id)}


def _tool_search_documents(pool, customer_id, product_id, arguments):
    query = (arguments.get("query") or "").strip()
    if not query:
        return {"error": "query is required"}
    top_k = int(arguments.get("top_k") or 4)
    return {"results": retrieve_context(pool, customer_id, product_id, query, top_k)}


def _tool_list_documents(pool, customer_id, product_id, arguments):
    return {
        "documents": [
            {"id": d["id"], "title": d["title"], "doc_type": d["doc_type"], "version": d["version"]}
            for d in list_documents(pool, customer_id, product_id)
        ]
    }


def _tool_list_proposals(pool, customer_id, product_id, arguments):
    return {
        "proposals": [
            {
                "id": p["id"],
                "title": p["title"],
                "status": p["status"],
                "is_active": p["is_active"],
                "content": p["content"],
                "attachment_count": len(p["attachments"]),
            }
            for p in list_proposals(pool, customer_id, product_id)
        ]
    }


def _tool_save_draft_proposal(pool, customer_id, product_id, user_id, arguments):
    title = (arguments.get("title") or "").strip()
    content = (arguments.get("content") or "").strip()
    if not content:
        return {"error": "content is required"}
    return create_proposal(pool, customer_id, product_id, title, content, user_id)


def _state_system_message(pool, customer, product):
    requirements = list_requirements(pool, customer["id"], product["id"], limit=10)
    proposals = list_proposals(pool, customer["id"], product["id"])
    current_proposal = next((p for p in proposals if p["status"] == "finalized"), None)
    documents = [
        {"title": d["title"], "doc_type": d["doc_type"]} for d in list_documents(pool, customer["id"], product["id"])
    ]
    state = {
        "customer": {"name": customer["name"], "notes": customer["notes"]},
        "product": {"name": product["name"], "description": product["description"]},
        "recent_requirements": requirements,
        "current_finalized_proposal": current_proposal,
        "documents_available": documents,
    }
    lines = [
        "Ngữ cảnh hiện tại cho khách hàng/sản phẩm đang tư vấn (JSON), dùng làm nền tảng trả lời, đừng đọc nguyên JSON cho người dùng:",
        json.dumps(state, ensure_ascii=False),
    ]
    return {"role": "system", "content": "\n".join(lines)}


def run_agent(cfg, pool, customer, product, user_id, messages, max_iterations=None):
    """Run the consult agent loop scoped to one (customer, product) pair.

    customer/product are dicts as returned by list_customers()/list_products().
    Returns (reply_text, tool_events).
    """
    max_iterations = max_iterations or int(cfg.get("crm_max_tool_iterations", 6))
    model = cfg.get("crm_model") or cfg["model"]
    customer_id, product_id = customer["id"], product["id"]

    working_messages = [
        {"role": "system", "content": system_prompt(customer["name"], product["name"])},
        _state_system_message(pool, customer, product),
    ] + list(messages)

    handlers = {
        "list_requirements": lambda arguments: _tool_list_requirements(pool, customer_id, product_id, arguments),
        "search_documents": lambda arguments: _tool_search_documents(pool, customer_id, product_id, arguments),
        "list_documents": lambda arguments: _tool_list_documents(pool, customer_id, product_id, arguments),
        "list_proposals": lambda arguments: _tool_list_proposals(pool, customer_id, product_id, arguments),
        "save_draft_proposal": lambda arguments: _tool_save_draft_proposal(
            pool, customer_id, product_id, user_id, arguments
        ),
    }
    return llm_tools.run_tool_loop(cfg, model, working_messages, TOOLS, handlers, max_iterations)
