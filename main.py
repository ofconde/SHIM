import os
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Text, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# ---------- Database setup ----------
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data.db")
# Railway (and Heroku-style) Postgres URLs sometimes use "postgres://", which
# modern SQLAlchemy needs as "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class KVStore(Base):
    __tablename__ = "kv_store"
    key = Column(String, primary_key=True, index=True)
    value = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- App ----------
app = FastAPI(title="Bitacora de Fuerza API")


class ValuePayload(BaseModel):
    value: str


@app.get("/api/storage/{key}")
def get_value(key: str, db: Session = Depends(get_db)):
    row = db.query(KVStore).filter(KVStore.key == key).first()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    return {"key": row.key, "value": row.value}


@app.post("/api/storage/{key}")
def set_value(key: str, payload: ValuePayload, db: Session = Depends(get_db)):
    row = db.query(KVStore).filter(KVStore.key == key).first()
    if row:
        row.value = payload.value
    else:
        row = KVStore(key=key, value=payload.value)
        db.add(row)
    db.commit()
    return {"key": key, "value": payload.value, "ok": True}


@app.delete("/api/storage/{key}")
def delete_value(key: str, db: Session = Depends(get_db)):
    row = db.query(KVStore).filter(KVStore.key == key).first()
    if row:
        db.delete(row)
        db.commit()
    return {"key": key, "deleted": True}


# ---------- Static frontend (must be mounted last, after API routes) ----------
app.mount("/", StaticFiles(directory="static", html=True), name="static")
