from fastapi import APIRouter, Depends
from app.services.embed import get_embedding
from app.database import get_db
from app.routers.auth import get_current_user
import psycopg2.extras

router = APIRouter(prefix="/search", tags=["search"])

@router.get("/")
def semantic_search(query: str, case_id: int | None = None, db=Depends(get_db), user=Depends(get_current_user)):
    query = (query or "").strip()
    if not query:
        return []

    query_embedding = get_embedding(query)
    q_words = [w.strip().lower() for w in query.split() if len(w.strip()) >= 3]

    sql = """
        SELECT id, title, doc_type, case_id, raw_text,
               1 - (embedding <=> %s::vector) AS semantic_sim
        FROM documents
        WHERE embedding IS NOT NULL
    """
    params = [query_embedding]

    if case_id:
        sql += " AND case_id = %s"
        params.append(case_id)

    sql += " ORDER BY embedding <=> %s::vector LIMIT 20"
    params.append(query_embedding)

    cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cursor.execute(sql, tuple(params))
        results = cursor.fetchall()

        scored = []
        for r in results:
            sem_sim = float(r["semantic_sim"])
            text_l = (r["raw_text"] or "").lower()
            title_l = (r["title"] or "").lower()

            # Hybrid keyword matching boost
            kw_hits = sum(1 for w in q_words if w in text_l or w in title_l)
            kw_bonus = 0.0
            if q_words:
                kw_ratio = kw_hits / len(q_words)
                kw_bonus = kw_ratio * 0.35

            final_sim = max(0.0, min(1.0, sem_sim + kw_bonus))

            # Include if keyword matched or semantic similarity is positive
            if kw_hits > 0 or sem_sim > 0.05 or final_sim > 0.15:
                scored.append({
                    "id": r["id"],
                    "title": r["title"],
                    "doc_type": r["doc_type"],
                    "case_id": r["case_id"],
                    "similarity": round(final_sim, 4),
                })

        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:10]
    finally:
        cursor.close()
