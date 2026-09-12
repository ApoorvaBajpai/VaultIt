from fastapi import APIRouter, Depends
from app.services.embed import get_embedding
from app.database import get_db
from app.routers.auth import get_current_user
import psycopg2.extras

router = APIRouter(prefix="/search", tags=["search"])

@router.get("/")
def semantic_search(query: str, case_id: int | None = None, db=Depends(get_db), user=Depends(get_current_user)):
    query_embedding = get_embedding(query)

    sql = """
        SELECT id, title, doc_type, case_id,
               1 - (embedding <=> %s::vector) AS similarity
        FROM documents
        WHERE embedding IS NOT NULL
    """
    params = [query_embedding]

    if case_id:
        sql += " AND case_id = %s"
        params.append(case_id)

    sql += " ORDER BY embedding <=> %s::vector LIMIT 10"
    params.append(query_embedding)

    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute(sql, tuple(params))
        results = cursor.fetchall()
        # threshold depends on model, 0.2 is reasonable for all-MiniLM-L6-v2 since distances are scaled differently
        return [dict(r) for r in results if r["similarity"] > 0.2]
    finally:
        cursor.close()
