import os
import datetime
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import DBUser

SECRET_KEY = os.getenv("SECRET_KEY", "CLAVE_DESARROLLO_LOCAL_SUPER_SECRETA_2026")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def hash_password(password: str) -> str:
    # Bcrypt requiere truncar o manejar cadenas cortas para evitar el límite de 72 bytes
    clean_password = password[:72] if len(password.encode('utf-8')) > 72 else password
    return pwd_context.hash(clean_password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    clean_password = plain_password[:72] if len(plain_password.encode('utf-8')) > 72 else plain_password
    return pwd_context.verify(clean_password, hashed_password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=480)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> DBUser:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Token inválido")
    except JWTError:
        raise HTTPException(status_code=401, detail="Sesión expirada")
    
    user = db.query(DBUser).filter(DBUser.email == email).first()
    if user is None or not user.activo:
        raise HTTPException(status_code=401, detail="Usuario no autorizado")
    return user

def require_admin(current_user: DBUser = Depends(get_current_user)):
    if current_user.rol != "ADMIN":
        raise HTTPException(status_code=403, detail="Requiere perfil Administrador")
    return current_user