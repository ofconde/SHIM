import os
import json
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Text, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# ---------- Database ----------
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data.db")
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


# ---------- Default routine data ----------
DEFAULT_ROUTINE = [
  { "id":"dia1", "num":"Día 1", "name":"Torso A", "exercises":[
    { "name":"Press inclinado con barra", "note":"Smith o barra libre 20/25 x lado", "standard":True, "sets":[{"reps":"12","w":30},{"reps":"10","w":30},{"reps":"8","w":40},{"reps":"8","w":40}] },
    { "name":"Jalón al frente agarre abierto", "standard":True, "sets":[{"reps":"12","w":45},{"reps":"10","w":50},{"reps":"8","w":55},{"reps":"8","w":60}] },
    { "name":"Apertura mancuernas banco plano", "standard":True, "sets":[{"reps":"12","w":11.5},{"reps":"10","w":11.5},{"reps":"8","w":13},{"reps":"8","w":13}] },
    { "name":"Remo bajo en polea prono abierto", "standard":True, "sets":[{"reps":"12","w":45},{"reps":"10","w":50},{"reps":"8","w":56},{"reps":"8","w":60}] },
    { "name":"Vuelo lateral con mancuernas", "standard":True, "sets":[{"reps":"12","w":9},{"reps":"10","w":11.5},{"reps":"8","w":11.5},{"reps":"8","w":13}] },
    { "name":"Jalón en polea con soga (tríceps)", "standard":True, "sets":[{"reps":"12","w":40},{"reps":"10","w":40},{"reps":"8","w":40},{"reps":"8","w":45}] },
    { "name":"Curl con barra EZ (bíceps)", "standard":True, "sets":[{"reps":"12","w":10},{"reps":"10","w":15},{"reps":"8","w":20},{"reps":"8","w":20}] },
  ]},
  { "id":"dia2", "num":"Día 2", "name":"Torso B", "exercises":[
    { "name":"Press militar con barra", "standard":True, "sets":[{"reps":"12","w":20},{"reps":"10","w":20},{"reps":"8","w":25},{"reps":"8","w":25}] },
    { "name":"Remo con barra EZ supino", "note":"peso x lado", "standard":True, "sets":[{"reps":"12","w":7.5},{"reps":"10","w":10},{"reps":"8","w":12.5},{"reps":"8","w":15}] },
    { "name":"Press plano con mancuernas", "standard":True, "sets":[{"reps":"12","w":13},{"reps":"10","w":16},{"reps":"8","w":16},{"reps":"8","w":16}] },
    { "name":"Jalón al frente agarre neutro cerrado", "standard":True, "sets":[{"reps":"12","w":50},{"reps":"10","w":50},{"reps":"8","w":55},{"reps":"8","w":55}] },
    { "name":"Vuelo posterior banco inclinado", "standard":True, "sets":[{"reps":"12","w":9},{"reps":"10","w":12.5},{"reps":"8","w":12.5},{"reps":"8","w":16}] },
    { "name":"Press francés barra EZ inclinado", "standard":True, "sets":[{"reps":"12","w":10},{"reps":"10","w":15},{"reps":"8","w":15},{"reps":"8","w":20}] },
    { "name":"Curl martillo con mancuernas", "standard":True, "sets":[{"reps":"12","w":11.5},{"reps":"10","w":13},{"reps":"8","w":13},{"reps":"8","w":16}] },
  ]},
  { "id":"dia3", "num":"Día 3", "name":"Pierna A", "exercises":[
    { "name":"Sentadilla", "standard":True, "sets":[{"reps":"12","w":40},{"reps":"10","w":50},{"reps":"8","w":55},{"reps":"8","w":60}] },
    { "name":"Prensa 45°", "standard":True, "sets":[{"reps":"12","w":60},{"reps":"10","w":65},{"reps":"8","w":70},{"reps":"8","w":80}] },
    { "name":"Sentadilla hack", "note":"liviano, ajustar en sesión", "standard":True, "sets":[{"reps":"12","w":None},{"reps":"10","w":None},{"reps":"8","w":None},{"reps":"8","w":None}] },
    { "name":"Femoral de pie en máquina", "note":"liviano, ajustar en sesión", "standard":False, "sets":[{"reps":"12","w":None},{"reps":"12","w":None},{"reps":"12","w":None}] },
    { "name":"Gemelos de pie en máquina", "standard":False, "sets":[{"reps":"20","w":90},{"reps":"20","w":90},{"reps":"20","w":90}] },
  ]},
  { "id":"dia4", "num":"Día 4", "name":"Pierna B", "exercises":[
    { "name":"Hip thrust con barra", "note":"arrancar conservador y subir", "standard":True, "sets":[{"reps":"12","w":20},{"reps":"10","w":20},{"reps":"8","w":20},{"reps":"8","w":20}] },
    { "name":"Camilla femoral", "standard":True, "sets":[{"reps":"12","w":35},{"reps":"10","w":40},{"reps":"8","w":45},{"reps":"8","w":45}] },
    { "name":"Zancadas con mancuernas", "note":"por pierna", "standard":False, "sets":[{"reps":"10-12","w":8},{"reps":"10-12","w":8},{"reps":"10-12","w":10}] },
    { "name":"Prensa 45° pies arriba", "standard":False, "sets":[{"reps":"12","w":50},{"reps":"12","w":55},{"reps":"12","w":60}] },
    { "name":"Gemelos sentado en máquina", "note":"ajustar en sesión", "standard":False, "sets":[{"reps":"15-20","w":None},{"reps":"15-20","w":None},{"reps":"15-20","w":None}] },
  ]},
]

DEFAULT_WEEKS = [
  {"n":1,"label":"Acumulación","rir":"2–3"},
  {"n":2,"label":"Acumulación","rir":"2"},
  {"n":3,"label":"Intensificación","rir":"1–2"},
  {"n":4,"label":"Intensificación","rir":"1"},
  {"n":5,"label":"Descarga","rir":"4–5"},
]

DEFAULT_ROTATION = ["dia1","dia2","dia3","dia1","dia2","dia4"]

ROUTINE_KEY = "shim:routine"
WEEKS_KEY   = "shim:weeks"
ROTATION_KEY = "shim:rotation"


def get_or_seed(db: Session, key: str, default) -> dict:
    row = db.query(KVStore).filter(KVStore.key == key).first()
    if not row:
        row = KVStore(key=key, value=json.dumps(default))
        db.add(row)
        db.commit()
    return json.loads(row.value)


# ---------- App ----------
app = FastAPI(title="SHIM API")


class ValuePayload(BaseModel):
    value: str


# ---- KV storage (progress) ----
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


# ---- Routine (served from DB, seeded on first request) ----
@app.get("/api/routine")
def get_routine(db: Session = Depends(get_db)):
    routine  = get_or_seed(db, ROUTINE_KEY,  DEFAULT_ROUTINE)
    weeks    = get_or_seed(db, WEEKS_KEY,    DEFAULT_WEEKS)
    rotation = get_or_seed(db, ROTATION_KEY, DEFAULT_ROTATION)
    return {"routine": routine, "weeks": weeks, "rotation": rotation}


@app.post("/api/routine")
def update_routine(payload: ValuePayload, db: Session = Depends(get_db)):
    """Update full routine config (routine + weeks + rotation as JSON string)"""
    data = json.loads(payload.value)
    for key, field in [(ROUTINE_KEY,"routine"),(WEEKS_KEY,"weeks"),(ROTATION_KEY,"rotation")]:
        if field in data:
            row = db.query(KVStore).filter(KVStore.key == key).first()
            if row:
                row.value = json.dumps(data[field])
            else:
                row = KVStore(key=key, value=json.dumps(data[field]))
                db.add(row)
    db.commit()
    return {"ok": True}


# ---------- Static (last) ----------
app.mount("/", StaticFiles(directory="static", html=True), name="static")
