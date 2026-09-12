from fastapi import APIRouter, Depends, HTTPException
from app.database import get_db
from app.routers.auth import get_current_user

router = APIRouter(prefix="/cases", tags=["cases"])

@router.post("/")
def create_case(case_number: str, title: str, db=Depends(get_db), user=Depends(get_current_user)):
    try:
        query = "INSERT INTO cases (case_number, title, created_by) VALUES (%s, %s, %s) RETURNING id"
        case_id = db.execute(query, (case_number, title, user["id"])).fetchone()[0]
        db.commit()
        return {"id": case_id, "case_number": case_number, "title": title}
    except Exception as e:
        db.rollback()
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=409, detail=f"Case number '{case_number}' already exists")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/")
def list_cases(db=Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute("SELECT id, case_number, title, status FROM cases ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]

@router.get("/{case_id}")
def get_case(case_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    case = db.execute("SELECT * FROM cases WHERE id = %s", (case_id,)).fetchone()
    docs = db.execute("SELECT id, title, doc_type, created_at FROM documents WHERE case_id = %s", (case_id,)).fetchall()
    return {"case": dict(case) if case else None, "documents": [dict(d) for d in docs]}

@router.get("/{case_id}/entities")
def get_case_entities(case_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    entities = db.execute(
        "SELECT id, name, role FROM entities WHERE case_id = %s", (case_id,)
    ).fetchall()

    result = []
    for e in entities:
        # Convert to dict in case it's a tuple from psycopg2
        try:
            e_dict = dict(e)
            e_id = e_dict["id"]
        except TypeError:
            e_dict = {"id": e[0], "name": e[1], "role": e[2]}
            e_id = e[0]

        docs = db.execute(
            """SELECT d.id, d.title FROM documents d
               JOIN document_entities de ON de.document_id = d.id
               WHERE de.entity_id = %s""",
            (e_id,)
        ).fetchall()
        
        linked_docs = []
        for d in docs:
            try:
                linked_docs.append(dict(d))
            except TypeError:
                linked_docs.append({"id": d[0], "title": d[1]})
                
        result.append({**e_dict, "linked_documents": linked_docs})

    return result

@router.get("/{case_id}/dashboard")
def case_dashboard(case_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    case = db.execute("SELECT * FROM cases WHERE id = %s", (case_id,)).fetchone()
    if not case:
        return {"error": "Case not found"}
    case = dict(case) if hasattr(case, 'keys') else {"id": case[0], "case_number": case[1], "title": case[2], "status": case[3]}

    documents = db.execute(
        "SELECT id, title, doc_type, created_at, merkle_root IS NOT NULL AS is_sealed FROM documents WHERE case_id = %s ORDER BY created_at",
        (case_id,)
    ).fetchall()
    
    entities = db.execute(
        "SELECT id, name, role FROM entities WHERE case_id = %s", (case_id,)
    ).fetchall()
    
    flag_status_filter = "unreviewed" if user["role"] in ("officer", "admin") else "confirmed"
    
    open_flags = db.execute(
        "SELECT id, summary FROM contradiction_flags WHERE case_id = %s AND status = %s",
        (case_id, flag_status_filter)
    ).fetchall()

    # Manual dict conversion in case real dict cursor is not used
    def to_dict_list(rows, cols):
        out = []
        for r in rows:
            try:
                out.append(dict(r))
            except TypeError:
                out.append(dict(zip(cols, r)))
        return out

    return {
        "case": case,
        "documents": to_dict_list(documents, ["id", "title", "doc_type", "created_at", "is_sealed"]),
        "entities": to_dict_list(entities, ["id", "name", "role"]),
        "open_contradiction_flags": to_dict_list(open_flags, ["id", "summary"]),
    }
