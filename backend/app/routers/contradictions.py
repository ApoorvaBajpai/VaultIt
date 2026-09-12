from fastapi import APIRouter, Depends
from app.database import get_db
from app.routers.auth import get_current_user
from app.services.contradictions import detect_contradictions

router = APIRouter(tags=["contradictions"])

@router.post("/cases/{case_id}/check-contradictions")
def run_contradiction_check(case_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    flags = detect_contradictions(db, case_id)
    for flag in flags:
        db.execute(
            "INSERT INTO contradiction_flags (case_id, document_ids, summary) VALUES (%s, %s, %s)",
            (case_id, flag["documents"], flag["summary"])
        )
    db.commit()
    return {"flags_found": len(flags), "flags": flags}

@router.patch("/contradiction-flags/{flag_id}")
def review_flag(flag_id: int, status: str, db=Depends(get_db), user=Depends(get_current_user)):
    assert status in ("dismissed", "confirmed")
    db.execute("UPDATE contradiction_flags SET status = %s WHERE id = %s", (status, flag_id))
    db.commit()
    return {"id": flag_id, "status": status}
