import os
import json
import base64
from datetime import datetime, date
from typing import Optional

import anthropic
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer, Float, Date
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


class Meal(Base):
    __tablename__ = "meals"
    id = Column(Integer, primary_key=True, autoincrement=True)
    day = Column(Date, index=True, nullable=False)
    name = Column(String, nullable=False)
    items = Column(Text)            # JSON list of strings
    kcal = Column(Float, default=0)
    protein_g = Column(Float, default=0)
    carbs_g = Column(Float, default=0)
    fat_g = Column(Float, default=0)
    source = Column(String, default="manual")  # "photo" | "text" | "manual"
    created_at = Column(DateTime, default=datetime.utcnow)


class Weight(Base):
    __tablename__ = "weights"
    day = Column(Date, primary_key=True)
    kg = Column(Float, nullable=False)
    note = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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


# ---------- Nutrition config ----------
# Fase de definición: 16 semanas, 87.5 kg → 80 kg
NUTRITION_TARGETS = {"kcal": 2000, "protein_g": 190, "carbs_g": 155, "fat_g": 60}
WEIGHT_GOAL = {"start_kg": 87.5, "goal_kg": 80.0, "weeks": 16, "start_date": "2026-09-21"}

USER_PROFILE = (
    "Perfil: hombre de 52 años, 87.5 kg, 1.78 m, ~29% grasa corporal, grasa visceral alta. "
    "Fase de definición de 16 semanas con objetivo 80 kg. "
    "Macros diarios objetivo: 2000 kcal / 190 g proteína / 155 g carbohidratos / 60 g grasas. "
    "Come principalmente pollo, huevos, arroz, papa y yogur; algunos días hace ayuno intermitente 16 h. "
    "Contexto argentino: porciones y nombres de comidas locales (milanesa, tarta, empanadas, etc.)."
)

ANALYZE_SYSTEM = (
    "Sos un nutricionista deportivo. Analizás comidas a partir de una foto y/o descripción en texto "
    "y estimás calorías y macronutrientes de la porción completa que se ve o se describe. "
    "Si la porción es ambigua, asumí una porción estándar de adulto y decilo en las notas. "
    "Redondeá kcal a múltiplos de 5 y gramos a enteros. Respondé siempre en español rioplatense, "
    "breve y directo, sin moralizar.\n\n" + USER_PROFILE
)

ANALYZE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Nombre corto de la comida, ej. 'Pollo con arroz y ensalada'"},
        "items": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Componentes detectados con porción estimada, ej. '150 g pechuga de pollo'",
        },
        "kcal": {"type": "number"},
        "protein_g": {"type": "number"},
        "carbs_g": {"type": "number"},
        "fat_g": {"type": "number"},
        "confidence": {"type": "string", "enum": ["alta", "media", "baja"]},
        "notes": {"type": "string", "description": "Una o dos frases: supuestos de porción y un consejo concreto según los macros objetivo del día."},
    },
    "required": ["name", "items", "kcal", "protein_g", "carbs_g", "fat_g", "confidence", "notes"],
    "additionalProperties": False,
}

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_anthropic_client: Optional[anthropic.Anthropic] = None


def get_anthropic() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY no configurada")
        # Si la key es de organización (no de un workspace), Anthropic exige
        # indicar el workspace por header. Se configura con ANTHROPIC_WORKSPACE_ID.
        ws = os.environ.get("ANTHROPIC_WORKSPACE_ID")
        headers = {"anthropic-workspace-id": ws} if ws else None
        _anthropic_client = anthropic.Anthropic(default_headers=headers)
    return _anthropic_client


def parse_day(value: Optional[str]) -> date:
    if not value:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="fecha inválida, usar YYYY-MM-DD")


def meal_to_dict(m: Meal) -> dict:
    return {
        "id": m.id,
        "date": m.day.isoformat(),
        "name": m.name,
        "items": json.loads(m.items) if m.items else [],
        "kcal": m.kcal or 0,
        "protein_g": m.protein_g or 0,
        "carbs_g": m.carbs_g or 0,
        "fat_g": m.fat_g or 0,
        "source": m.source,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


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


# ---- Nutrition: analyze (Claude vision) ----
@app.post("/api/nutrition/analyze")
async def analyze_meal(
    image: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    consumed: Optional[str] = Form(None),  # JSON con lo ya comido hoy, para el consejo
):
    """Estima kcal y macros de una comida a partir de foto y/o texto. No guarda nada."""
    if image is None and not (text and text.strip()):
        raise HTTPException(status_code=400, detail="mandá una foto o una descripción")

    content = []
    if image is not None:
        media_type = image.content_type or "image/jpeg"
        if media_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail=f"formato de imagen no soportado: {media_type}")
        raw = await image.read()
        if len(raw) > 8 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="imagen muy grande (máx 8 MB)")
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type,
                       "data": base64.standard_b64encode(raw).decode("utf-8")},
        })

    prompt = "Analizá esta comida y estimá kcal y macros de la porción completa."
    if text and text.strip():
        prompt += f"\n\nDescripción del usuario: {text.strip()}"
    if consumed:
        prompt += f"\n\nYa consumido hoy (para el consejo en notas): {consumed}"
    content.append({"type": "text", "text": prompt})

    client = get_anthropic()
    try:
        response = client.messages.create(
            model="claude-opus-5",
            max_tokens=2048,
            system=ANALYZE_SYSTEM,
            messages=[{"role": "user", "content": content}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": ANALYZE_SCHEMA}},
        )
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY inválida")
    except anthropic.RateLimitError:
        raise HTTPException(status_code=429, detail="límite de uso de la API, probá en un minuto")
    except anthropic.APIStatusError as e:
        print(f"[nutrition/analyze] Anthropic {e.status_code}: {e.message}", flush=True)
        raise HTTPException(status_code=502, detail=f"error de la API ({e.status_code}): {e.message[:300]}")
    except anthropic.APIConnectionError:
        raise HTTPException(status_code=502, detail="no se pudo conectar con la API")

    if response.stop_reason == "refusal":
        raise HTTPException(status_code=422, detail="no pude analizar esa imagen")

    text_block = next((b.text for b in response.content if b.type == "text"), None)
    if not text_block:
        raise HTTPException(status_code=502, detail="respuesta vacía del modelo")
    data = json.loads(text_block)
    data["source"] = "photo" if image is not None else "text"
    return data


# ---- Nutrition: meals ----
class MealPayload(BaseModel):
    date: Optional[str] = None
    name: str
    items: list[str] = []
    kcal: float = 0
    protein_g: float = 0
    carbs_g: float = 0
    fat_g: float = 0
    source: str = "manual"


@app.get("/api/nutrition/meals")
def list_meals(date: Optional[str] = None, db: Session = Depends(get_db)):
    day = parse_day(date)
    rows = db.query(Meal).filter(Meal.day == day).order_by(Meal.created_at.asc()).all()
    meals = [meal_to_dict(m) for m in rows]
    totals = {
        "kcal": round(sum(m["kcal"] for m in meals)),
        "protein_g": round(sum(m["protein_g"] for m in meals)),
        "carbs_g": round(sum(m["carbs_g"] for m in meals)),
        "fat_g": round(sum(m["fat_g"] for m in meals)),
    }
    return {"date": day.isoformat(), "meals": meals, "totals": totals, "targets": NUTRITION_TARGETS}


@app.post("/api/nutrition/meals")
def create_meal(payload: MealPayload, db: Session = Depends(get_db)):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="la comida necesita un nombre")
    m = Meal(
        day=parse_day(payload.date),
        name=payload.name.strip(),
        items=json.dumps(payload.items, ensure_ascii=False),
        kcal=payload.kcal, protein_g=payload.protein_g,
        carbs_g=payload.carbs_g, fat_g=payload.fat_g,
        source=payload.source,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return meal_to_dict(m)


@app.delete("/api/nutrition/meals/{meal_id}")
def delete_meal(meal_id: int, db: Session = Depends(get_db)):
    m = db.query(Meal).filter(Meal.id == meal_id).first()
    if m:
        db.delete(m)
        db.commit()
    return {"id": meal_id, "deleted": True}


@app.get("/api/nutrition/history")
def nutrition_history(days: int = 14, db: Session = Depends(get_db)):
    """Totales diarios de los últimos N días (para la pantalla de progreso)."""
    days = max(1, min(days, 90))
    rows = db.query(Meal).order_by(Meal.day.desc()).all()
    by_day: dict[str, dict] = {}
    for m in rows:
        k = m.day.isoformat()
        d = by_day.setdefault(k, {"date": k, "kcal": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "meals": 0})
        d["kcal"] += m.kcal or 0; d["protein_g"] += m.protein_g or 0
        d["carbs_g"] += m.carbs_g or 0; d["fat_g"] += m.fat_g or 0; d["meals"] += 1
        if len(by_day) > days:
            break
    out = sorted(by_day.values(), key=lambda d: d["date"])[-days:]
    for d in out:
        for k in ("kcal", "protein_g", "carbs_g", "fat_g"):
            d[k] = round(d[k])
    return {"days": out, "targets": NUTRITION_TARGETS}


# ---- Weight ----
class WeightPayload(BaseModel):
    date: Optional[str] = None
    kg: float
    note: Optional[str] = None


@app.get("/api/weight")
def list_weights(db: Session = Depends(get_db)):
    rows = db.query(Weight).order_by(Weight.day.asc()).all()
    entries = [{"date": w.day.isoformat(), "kg": w.kg, "note": w.note} for w in rows]
    return {"entries": entries, "goal": WEIGHT_GOAL}


@app.post("/api/weight")
def upsert_weight(payload: WeightPayload, db: Session = Depends(get_db)):
    if not (30 <= payload.kg <= 250):
        raise HTTPException(status_code=400, detail="peso fuera de rango")
    day = parse_day(payload.date)
    w = db.query(Weight).filter(Weight.day == day).first()
    if w:
        w.kg = payload.kg
        w.note = payload.note
    else:
        w = Weight(day=day, kg=payload.kg, note=payload.note)
        db.add(w)
    db.commit()
    return {"date": day.isoformat(), "kg": w.kg, "note": w.note, "ok": True}


@app.delete("/api/weight/{day}")
def delete_weight(day: str, db: Session = Depends(get_db)):
    d = parse_day(day)
    w = db.query(Weight).filter(Weight.day == d).first()
    if w:
        db.delete(w)
        db.commit()
    return {"date": d.isoformat(), "deleted": True}


# ---------- Static (last) ----------
app.mount("/", StaticFiles(directory="static", html=True), name="static")
