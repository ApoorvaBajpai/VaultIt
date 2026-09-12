import hashlib
import os
import uuid
import numpy as np
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from PIL import Image
import pytesseract
from app.database import get_db
from app.routers.auth import get_current_user
from app.services.classify import classify_document
from app.services.redact import redact_pii
from app.services.anchor_service import contract, anchor_pending_documents
from app.services.embed import get_embedding
from app.services.case_linking import suggest_related_case
from app.services.entities import process_entities

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

router = APIRouter(prefix="/documents", tags=["documents"])
UPLOAD_DIR = "storage/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def is_blurry(image: Image.Image, threshold: float = 100.0) -> bool:
    gray = image.convert("L")
    arr = np.array(gray, dtype=np.float64)
    # Laplacian variance — low variance means blurry
    laplacian = np.abs(np.gradient(np.gradient(arr, axis=0), axis=0)) + np.abs(np.gradient(np.gradient(arr, axis=1), axis=1))
    return bool(laplacian.var() < threshold)

def extract_text_from_pdf(filepath: str) -> str:
    if not pdfplumber:
        return ""
    text = ""
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
    return text

@router.post("/upload")
async def upload_document(
    case_id: int = Form(...),
    title: str = Form(...),
    file: UploadFile = File(...),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    ext = file.filename.split(".")[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    contents = await file.read()
    with open(filepath, "wb") as f:
        f.write(contents)

    sha256_hash = hashlib.sha256(contents).hexdigest()

    raw_text = ""
    if ext.lower() in ("png", "jpg", "jpeg", "tiff"):
        image = Image.open(filepath)
        if is_blurry(image):
            os.remove(filepath)
            raise HTTPException(status_code=422, detail="Image is too blurry. Please re-scan.")
        try:
            raw_text = pytesseract.image_to_string(image)
        except Exception:
            raw_text = ""
    elif ext.lower() == "pdf":
        raw_text = extract_text_from_pdf(filepath)

    try:
        query = """
            INSERT INTO documents (case_id, uploaded_by, title, file_path, raw_text, sha256_hash)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        """
        doc_id = db.execute(query, (case_id, user["id"], title, filepath, raw_text, sha256_hash)).fetchone()[0]
        db.commit()
    except Exception as e:
        db.rollback()
        if "foreign key" in str(e).lower():
            raise HTTPException(status_code=400, detail=f"Case ID {case_id} does not exist. Create the case first.")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    doc_type = classify_document(raw_text)
    redacted_text = redact_pii(raw_text)
    
    try:
        db.execute(
            "UPDATE documents SET raw_text = %s, redacted_text = %s, doc_type = %s WHERE id = %s",
            (raw_text, redacted_text, doc_type, doc_id),
        )
        db.commit()
    except Exception:
        db.rollback()

    # Phase 5: Embeddings
    embedding = None
    related_cases = []
    if raw_text:
        try:
            embedding = get_embedding(raw_text)
            db.execute(
                "UPDATE documents SET embedding = %s WHERE id = %s",
                (str(embedding), doc_id)
            )
            db.commit()
            related_cases = suggest_related_case(db, embedding, case_id)
        except Exception:
            db.rollback()

    # Phase 6: Entities
    if raw_text:
        try:
            process_entities(db, doc_id, case_id, raw_text)
        except Exception:
            db.rollback()

    try:
        db.execute(
            "INSERT INTO audit_logs (document_id, user_id, action) VALUES (%s, %s, 'upload')",
            (doc_id, user["id"]),
        )
        db.commit()
    except Exception:
        db.rollback()

    return {
        "id": doc_id, 
        "sha256_hash": sha256_hash, 
        "doc_type": doc_type, 
        "raw_text": raw_text[:200],
        "related_cases": related_cases
    }

@router.get("/{doc_id}/audit-trail")
def get_audit_trail(doc_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    logs = db.execute(
        """SELECT a.action, a."timestamp", u.name AS user_name, u.role
           FROM audit_logs a JOIN users u ON u.id = a.user_id
           WHERE a.document_id = %s ORDER BY a."timestamp" ASC""",
        (doc_id,)
    ).fetchall()
    # Handle dict row depending on psycopg2 row factory
    results = []
    for l in logs:
        try:
            results.append(dict(l))
        except TypeError:
            results.append({
                "action": l[0],
                "timestamp": l[1],
                "user_name": l[2],
                "role": l[3]
            })
    return results

@router.post("/anchor")
def push_pending_documents_to_blockchain(db=Depends(get_db)):
    result = anchor_pending_documents(db)
    return result

@router.get("/{doc_id}")
def get_document(doc_id: int, db=Depends(get_db), user=Depends(get_current_user)):
    doc = db.execute("SELECT * FROM documents WHERE id = %s", (doc_id,)).fetchone()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    doc = dict(doc)

    db.execute(
        "INSERT INTO audit_logs (document_id, user_id, action) VALUES (%s, %s, 'view')",
        (doc_id, user["id"]),
    )
    db.commit()

    if user["role"] not in ("officer", "admin"):
        doc["raw_text"] = doc.get("redacted_text")

    return doc

@router.get("/{doc_id}/verify")
def verify_document(doc_id: int, db=Depends(get_db)):
    doc = db.execute("SELECT * FROM documents WHERE id = %s", (doc_id,)).fetchone()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    doc = dict(doc)

    if not os.path.exists(doc["file_path"]):
        return {"verified": False, "reason": "File missing from disk"}

    with open(doc["file_path"], "rb") as f:
        current_hash = hashlib.sha256(f.read()).hexdigest()

    if current_hash != doc["sha256_hash"]:
        return {"verified": False, "reason": "File contents have changed since upload"}

    if not doc["merkle_root"]:
        return {"verified": False, "reason": "Document not yet anchored to blockchain"}

    # Confirm the stored root is actually anchored on-chain
    is_anchored = contract.functions.isAnchored(bytes.fromhex(doc["merkle_root"])).call()

    return {
        "verified": is_anchored,
        "sha256_hash": doc["sha256_hash"],
        "merkle_root": doc["merkle_root"],
        "blockchain_tx_hash": doc["blockchain_tx_hash"],
    }
