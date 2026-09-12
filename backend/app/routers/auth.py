from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from app.auth import decode_token, verify_password, hash_password, create_access_token
from app.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    try:
        payload = decode_token(token)
        return {"id": payload["sub"], "role": payload["role"]}
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def require_role(*allowed_roles):
    def checker(user: dict = Depends(get_current_user)):
        if user["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker

@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db=Depends(get_db)):
    if not db:
        raise HTTPException(status_code=500, detail="Database connection error")
        
    user = db.execute("SELECT * FROM users WHERE email = %s", (form_data.username,)).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    
    if not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
        
    token_data = {"sub": str(user["id"]), "role": user["role"]}
    access_token = create_access_token(token_data)
    
    return {"access_token": access_token, "token_type": "bearer"}

class RegisterRequest(BaseModel):
    name: str = "Officer"
    email: str
    password: str
    role: str = "officer"
    department: str = "Investigation"

@router.post("/register")
def register(req: RegisterRequest, db=Depends(get_db)):
    if not db:
        raise HTTPException(status_code=500, detail="Database connection error")
        
    user = db.execute("SELECT id FROM users WHERE email = %s", (req.email,)).fetchone()
    if user:
        pwd_hash = hash_password(req.password)
        db.execute("UPDATE users SET password_hash = %s, name = %s, role = %s WHERE email = %s", 
                   (pwd_hash, req.name, req.role, req.email))
        db.commit()
        return {"message": "User credentials updated successfully", "email": req.email}

    pwd_hash = hash_password(req.password)
    db.execute(
        "INSERT INTO users (name, email, password_hash, role, department) VALUES (%s, %s, %s, %s, %s)",
        (req.name, req.email, pwd_hash, req.role, req.department)
    )
    db.commit()
    return {"message": "User registered successfully", "email": req.email}
