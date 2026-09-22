import os
import json
import base64
import re
from datetime import datetime, date, timedelta
from typing import Optional

import httpx
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


class WorkoutLog(Base):
    """Sesión de pesas completada en un día real del calendario (distinto del
    contador de rotación interno, que no tiene fecha)."""
    __tablename__ = "workout_log"
    day = Column(Date, primary_key=True)
    day_id = Column(String, nullable=False)     # ej. "dia3"
    day_name = Column(String, nullable=False)   # ej. "Pierna A"
    week_n = Column(Integer)                    # ej. 5
    week_label = Column(String)                 # ej. "Descarga"
    created_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DailyLog(Base):
    """Datos sueltos del día que no tienen tabla propia: pasos y una mini
    valoración subjetiva, para armar un registro diario completo."""
    __tablename__ = "daily_log"
    day = Column(Date, primary_key=True)
    steps = Column(Integer)
    mood = Column(Integer)          # 1 (mal) a 5 (excelente)
    note = Column(Text)
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
    "breve y directo, sin moralizar. Respondé únicamente con el JSON pedido.\n\n" + USER_PROFILE
)

# Esquema de respuesta (formato OpenAPI que acepta Gemini en responseSchema)
ANALYZE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "name": {"type": "STRING", "description": "Nombre corto de la comida, ej. 'Pollo con arroz y ensalada'"},
        "items": {"type": "ARRAY", "items": {"type": "STRING"},
                  "description": "Componentes detectados con porción estimada, ej. '150 g pechuga de pollo'"},
        "kcal": {"type": "NUMBER"},
        "protein_g": {"type": "NUMBER"},
        "carbs_g": {"type": "NUMBER"},
        "fat_g": {"type": "NUMBER"},
        "confidence": {"type": "STRING", "enum": ["alta", "media", "baja"]},
        "notes": {"type": "STRING", "description": "Una o dos frases: supuestos de porción y un consejo concreto según los macros objetivo del día."},
    },
    "required": ["name", "items", "kcal", "protein_g", "carbs_g", "fat_g", "confidence", "notes"],
}

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

# ---- Motor 1: Gemini (plan gratuito de Google AI Studio) ----
# Se prueban en orden; si uno da 404 (retirado) o 503 (saturado) se pasa al siguiente.
# flash-lite primero: responde en 2-3 s en el plan gratuito; los grandes tardan 10-30 s.
GEMINI_MODELS = [m.strip() for m in os.environ.get(
    "GEMINI_MODELS", "gemini-3.5-flash-lite,gemini-3.8-flash,gemini-3.5-flash"
).split(",") if m.strip()]
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


async def analyze_with_gemini(parts: list, api_key: str) -> dict:
    body = {
        "systemInstruction": {"parts": [{"text": ANALYZE_SYSTEM}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": ANALYZE_SCHEMA,
            "temperature": 0.2,
            # Sin razonamiento largo: para estimar macros no aporta y multiplica la latencia.
            "thinkingConfig": {"thinkingLevel": "minimal"},
        },
    }
    last_err = "sin modelos configurados"
    async with httpx.AsyncClient(timeout=60) as client:
        for model in GEMINI_MODELS:
            r = await client.post(GEMINI_URL.format(model=model), json=body,
                                  headers={"x-goog-api-key": api_key})
            if r.status_code == 200:
                break
            try:
                msg = r.json().get("error", {}).get("message", r.text)
            except Exception:
                msg = r.text
            last_err = f"Gemini {model} {r.status_code}: {msg[:200]}"
            print(f"[nutrition/analyze] {last_err}", flush=True)
            if r.status_code not in (404, 429, 503):
                break
        else:
            raise RuntimeError(last_err)
    if r.status_code != 200:
        raise RuntimeError(last_err)
    data = r.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise RuntimeError("respuesta vacía de Gemini")
    return json.loads(text)


# ---- Motor 2: tabla local (sin internet, sin key) ----
# Valores por 100 g (o por unidad si "unit_g" define el peso de una unidad).
# kcal, prot, carb, grasa
FOOD_DB = {
    "pollo":        {"alias": ["pechuga", "pollo", "muslo"],                "per100": (165, 31, 0, 3.6), "unit_g": None},
    "huevo":        {"alias": ["huevo", "huevos"],                          "per100": (143, 12.6, 0.7, 9.5), "unit_g": 55},
    "clara":        {"alias": ["clara", "claras"],                          "per100": (52, 11, 0.7, 0.2), "unit_g": 33},
    "arroz":        {"alias": ["arroz"],                                    "per100": (130, 2.7, 28, 0.3), "unit_g": None},
    "papa":         {"alias": ["papa", "papas", "pure", "puré"],            "per100": (87, 1.9, 20, 0.1), "unit_g": 150},
    "batata":       {"alias": ["batata", "batatas"],                        "per100": (90, 2, 21, 0.1), "unit_g": 150},
    "yogur":        {"alias": ["yogur", "yogurt", "yoghurt"],               "per100": (60, 4, 6, 2), "unit_g": 180},
    "yogur griego": {"alias": ["griego"],                                   "per100": (97, 9, 4, 5), "unit_g": 150},
    "avena":        {"alias": ["avena"],                                    "per100": (380, 13, 66, 7), "unit_g": None},
    "pan":          {"alias": ["pan", "tostada", "tostadas", "rebanada", "rodaja"], "per100": (265, 9, 49, 3.2), "unit_g": 30},
    "pan integral": {"alias": ["integral"],                                 "per100": (250, 12, 43, 3.5), "unit_g": 30},
    "queso untable":{"alias": ["untable", "casancrem", "finlandia"],        "per100": (250, 7, 4, 23), "unit_g": 20},
    "queso":        {"alias": ["queso", "muzzarella", "mozzarella", "cremoso"], "per100": (300, 22, 2, 23), "unit_g": 30},
    "carne":        {"alias": ["carne", "bife", "nalga", "lomo", "cuadril", "vacio", "vacío", "asado", "churrasco"], "per100": (200, 26, 0, 10), "unit_g": None},
    "carne picada": {"alias": ["picada", "hamburguesa"],                    "per100": (250, 26, 0, 17), "unit_g": 120},
    "cerdo":        {"alias": ["cerdo", "bondiola", "matambre"],            "per100": (240, 27, 0, 14), "unit_g": None},
    "pescado":      {"alias": ["pescado", "merluza", "salmon", "salmón", "atun", "atún"], "per100": (120, 24, 0, 2.5), "unit_g": None},
    "milanesa":     {"alias": ["milanesa", "milanesas", "milas"],           "per100": (250, 18, 18, 12), "unit_g": 150},
    "empanada":     {"alias": ["empanada", "empanadas"],                    "per100": (270, 10, 28, 13), "unit_g": 90},
    "pizza":        {"alias": ["pizza", "porcion de pizza"],                "per100": (265, 11, 33, 10), "unit_g": 120},
    "fideos":       {"alias": ["fideos", "pasta", "tallarines", "ñoquis", "noquis", "ravioles"], "per100": (155, 5.5, 30, 1), "unit_g": None},
    "lentejas":     {"alias": ["lentejas", "garbanzos", "porotos"],         "per100": (115, 9, 20, 0.4), "unit_g": None},
    "ensalada":     {"alias": ["ensalada", "lechuga", "tomate", "verduras", "vegetales", "brocoli", "brócoli", "zanahoria", "zapallito", "espinaca"], "per100": (25, 1.5, 4, 0.2), "unit_g": 100},
    "palta":        {"alias": ["palta", "aguacate"],                        "per100": (160, 2, 9, 15), "unit_g": 100},
    "banana":       {"alias": ["banana", "bananas"],                        "per100": (89, 1.1, 23, 0.3), "unit_g": 120},
    "manzana":      {"alias": ["manzana", "manzanas", "pera", "naranja", "mandarina", "durazno", "fruta"], "per100": (52, 0.3, 14, 0.2), "unit_g": 150},
    "leche":        {"alias": ["leche"],                                    "per100": (50, 3.3, 4.8, 1.6), "unit_g": None},
    "whey":         {"alias": ["whey", "proteina", "proteína", "scoop"],    "per100": (380, 75, 8, 5), "unit_g": 30},
    "aceite":       {"alias": ["aceite", "manteca"],                        "per100": (880, 0, 0, 100), "unit_g": 10},
    "mani":         {"alias": ["mani", "maní", "almendras", "nueces", "frutos secos"], "per100": (600, 22, 16, 50), "unit_g": 30},
    "medialuna":    {"alias": ["medialuna", "medialunas", "factura", "facturas"], "per100": (400, 7, 50, 19), "unit_g": 45},
    "galletitas":   {"alias": ["galletita", "galletitas", "galletas"],      "per100": (450, 7, 68, 16), "unit_g": 8},
    "cerveza":      {"alias": ["cerveza", "birra"],                         "per100": (43, 0.5, 3.5, 0), "unit_g": None},
    "vino":         {"alias": ["vino"],                                     "per100": (85, 0, 2.5, 0), "unit_g": None},
    "gaseosa":      {"alias": ["gaseosa", "coca", "jugo"],                  "per100": (42, 0, 10.5, 0), "unit_g": None},
    "chocolate":    {"alias": ["chocolate", "alfajor", "alfajores"],        "per100": (500, 6, 55, 28), "unit_g": 50},
    "mate":         {"alias": ["mate", "cafe", "café", "te", "té", "agua"], "per100": (2, 0, 0.5, 0), "unit_g": 200},
}
# Índice alias → clave, con los alias más largos primero para que "pan integral" gane sobre "pan"
_FOOD_INDEX = sorted(((a, k) for k, v in FOOD_DB.items() for a in v["alias"]), key=lambda t: -len(t[0]))

_NUM = r"(\d+(?:[.,]\d+)?)"
_QTY_RE = re.compile(
    rf"(?:{_NUM}\s*(kg|kilo|g|gr|grs|gramos|ml|cc|taza|tazas|cda|cdas|cucharada|cucharadas|scoop|scoops|unidad|unidades|u)?\b)"
    r"|(?:\b(un|una|uno|dos|tres|cuatro|cinco|seis|medio|media|1/2)\b)",
    re.IGNORECASE,
)
_WORD_NUM = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "medio": 0.5, "media": 0.5, "1/2": 0.5}
_UNIT_ML = {"ml", "cc"}
_UNIT_G = {"g", "gr", "grs", "gramos"}
_CUP_G = 150      # taza de arroz/fideos/leche cocidos aprox
_SPOON_G = 12     # cucharada


def _grams_for(qty: float, unit: Optional[str], food: dict) -> float:
    unit = (unit or "").lower()
    if unit in _UNIT_G or unit in _UNIT_ML:
        return qty
    if unit in ("kg", "kilo"):
        return qty * 1000
    if unit in ("taza", "tazas"):
        return qty * _CUP_G
    if unit in ("cda", "cdas", "cucharada", "cucharadas"):
        return qty * _SPOON_G
    # unidades (o sin unidad): usa el peso por unidad si existe, si no asume porción de 100 g
    return qty * (food["unit_g"] or 100)


def analyze_locally(text: str) -> dict:
    segments = [seg.strip() for seg in re.split(r"[,;\n]|\by\b|\bcon\b|\+", text, flags=re.IGNORECASE) if seg.strip()]
    items, unknown = [], []
    tot = [0.0, 0.0, 0.0, 0.0]
    for seg in segments:
        low = seg.lower()
        key = next((k for a, k in _FOOD_INDEX if re.search(rf"\b{re.escape(a)}\b", low)), None)
        if not key:
            unknown.append(seg)
            continue
        food = FOOD_DB[key]
        qty, unit = 1.0, None
        m = _QTY_RE.search(low)
        if m:
            if m.group(1):
                qty = float(m.group(1).replace(",", "."))
                unit = m.group(2)
            elif m.group(3):
                qty = _WORD_NUM[m.group(3).lower()]
        grams = _grams_for(qty, unit, food)
        k, pr, cb, ft = food["per100"]
        f = grams / 100
        tot[0] += k * f; tot[1] += pr * f; tot[2] += cb * f; tot[3] += ft * f
        items.append(f"{round(grams)} g {key}")
    if not items:
        raise ValueError("no reconocí ningún alimento; probá con 'cantidad + alimento', ej. '150g pollo, 2 huevos'")
    name = " + ".join(i.split(" g ", 1)[1] for i in items[:3]).capitalize()
    notes = "Estimado con tabla local (sin foto)."
    if unknown:
        notes += " No reconocí: " + ", ".join(unknown[:3]) + "."
    return {
        "name": name, "items": items,
        "kcal": round(tot[0] / 5) * 5, "protein_g": round(tot[1]),
        "carbs_g": round(tot[2]), "fat_g": round(tot[3]),
        "confidence": "baja" if unknown else "media", "notes": notes,
    }


# El servidor corre en UTC (Railway), pero el corte de "día" tiene que ser el
# de Argentina, no el de Londres. Argentina está fija en UTC-3 desde 2009
# (sin horario de verano), así que un offset fijo es exacto y no depende de
# que el contenedor tenga datos de huso horario (tzdata) instalados.
AR_OFFSET = timedelta(hours=-3)


def today_ar() -> date:
    return (datetime.utcnow() + AR_OFFSET).date()


def parse_day(value: Optional[str]) -> date:
    if not value:
        return today_ar()
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


# ---- Nutrition: analyze (Gemini gratis, con fallback a tabla local) ----
@app.post("/api/nutrition/analyze")
async def analyze_meal(
    image: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    consumed: Optional[str] = Form(None),  # JSON con lo ya comido hoy, para el consejo
):
    """Estima kcal y macros de una comida a partir de foto y/o texto. No guarda nada."""
    text = (text or "").strip()
    if image is None and not text:
        raise HTTPException(status_code=400, detail="mandá una foto o una descripción")

    parts = []
    if image is not None:
        media_type = image.content_type or "image/jpeg"
        if media_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail=f"formato de imagen no soportado: {media_type}")
        raw = await image.read()
        if len(raw) > 8 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="imagen muy grande (máx 8 MB)")
        parts.append({"inline_data": {"mime_type": media_type, "data": base64.standard_b64encode(raw).decode("utf-8")}})

    prompt = "Analizá esta comida y estimá kcal y macros de la porción completa."
    if text:
        prompt += f"\n\nDescripción del usuario: {text}"
    if consumed:
        prompt += f"\n\nYa consumido hoy (para el consejo en notas): {consumed}"
    parts.append({"text": prompt})

    source = "photo" if image is not None else "text"
    gemini_key = os.environ.get("GEMINI_API_KEY")
    gemini_error = None
    if gemini_key:
        try:
            data = await analyze_with_gemini(parts, gemini_key)
            data.update(source=source, engine="gemini")
            return data
        except (RuntimeError, httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
            gemini_error = str(e)

    # Fallback local: solo sirve con texto
    if not text:
        detail = "para analizar fotos hace falta GEMINI_API_KEY" if not gemini_key else f"no pude analizar la foto ({gemini_error})"
        raise HTTPException(status_code=503, detail=detail)
    try:
        data = analyze_locally(text)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if gemini_error:
        data["notes"] += f" (Gemini falló: {gemini_error[:80]})"
    data.update(source=source, engine="local")
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


@app.get("/api/nutrition/recent")
def recent_meals(limit: int = 12, db: Session = Depends(get_db)):
    """Comidas ya cargadas, para agregarlas de nuevo con un toque (ej. el
    batido de proteína de siempre). Deduplicadas por nombre, ordenadas por
    cuántas veces se repitieron y luego por la más reciente."""
    limit = max(1, min(limit, 30))
    rows = db.query(Meal).order_by(Meal.created_at.desc()).limit(500).all()
    agg: dict[str, dict] = {}
    for m in rows:
        key = m.name.strip().lower()
        if key not in agg:
            agg[key] = {
                "name": m.name, "items": json.loads(m.items) if m.items else [],
                "kcal": m.kcal, "protein_g": m.protein_g, "carbs_g": m.carbs_g, "fat_g": m.fat_g,
                "count": 0, "last_used": m.created_at,
            }
        agg[key]["count"] += 1
    ordered = sorted(agg.values(), key=lambda x: x["last_used"], reverse=True)
    ordered.sort(key=lambda x: x["count"], reverse=True)  # sort estable: desempata por recencia
    ordered = ordered[:limit]
    for e in ordered:
        e["last_used"] = e["last_used"].isoformat()
    return {"meals": ordered}


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


# ---- Registro diario (entrenamiento + pasos + valoración) ----
# Pensado para poder mostrarle el día completo a una nutricionista: qué se
# entrenó, cuántos pasos, qué se comió y una mini autoevaluación.
class WorkoutLogPayload(BaseModel):
    date: Optional[str] = None
    day_id: str
    day_name: str
    week_n: Optional[int] = None
    week_label: Optional[str] = None


@app.post("/api/workout-log")
def log_workout(payload: WorkoutLogPayload, db: Session = Depends(get_db)):
    day = parse_day(payload.date)
    w = db.query(WorkoutLog).filter(WorkoutLog.day == day).first()
    if w:
        w.day_id = payload.day_id
        w.day_name = payload.day_name
        w.week_n = payload.week_n
        w.week_label = payload.week_label
    else:
        w = WorkoutLog(day=day, day_id=payload.day_id, day_name=payload.day_name,
                        week_n=payload.week_n, week_label=payload.week_label)
        db.add(w)
    db.commit()
    return {"date": day.isoformat(), "day_name": payload.day_name, "ok": True}


class DailyLogPayload(BaseModel):
    date: Optional[str] = None
    steps: Optional[int] = None
    mood: Optional[int] = None   # 1-5
    note: Optional[str] = None


@app.post("/api/log/day")
def save_daily_log(payload: DailyLogPayload, db: Session = Depends(get_db)):
    if payload.mood is not None and not (1 <= payload.mood <= 5):
        raise HTTPException(status_code=400, detail="mood debe ser 1-5")
    day = parse_day(payload.date)
    d = db.query(DailyLog).filter(DailyLog.day == day).first()
    if d:
        if payload.steps is not None: d.steps = payload.steps
        if payload.mood is not None: d.mood = payload.mood
        if payload.note is not None: d.note = payload.note
    else:
        d = DailyLog(day=day, steps=payload.steps, mood=payload.mood, note=payload.note)
        db.add(d)
    db.commit()
    return {"date": day.isoformat(), "ok": True}


def _build_day_log(db: Session, day: date) -> dict:
    meals = db.query(Meal).filter(Meal.day == day).order_by(Meal.created_at.asc()).all()
    meal_dicts = [meal_to_dict(m) for m in meals]
    totals = {
        "kcal": round(sum(m["kcal"] for m in meal_dicts)),
        "protein_g": round(sum(m["protein_g"] for m in meal_dicts)),
        "carbs_g": round(sum(m["carbs_g"] for m in meal_dicts)),
        "fat_g": round(sum(m["fat_g"] for m in meal_dicts)),
    }
    weight = db.query(Weight).filter(Weight.day == day).first()
    workout = db.query(WorkoutLog).filter(WorkoutLog.day == day).first()
    daily = db.query(DailyLog).filter(DailyLog.day == day).first()
    return {
        "date": day.isoformat(),
        "meals": meal_dicts,
        "totals": totals,
        "targets": NUTRITION_TARGETS,
        "weight_kg": weight.kg if weight else None,
        "workout": ({"day_name": workout.day_name, "week_n": workout.week_n,
                      "week_label": workout.week_label} if workout else None),
        "steps": daily.steps if daily else None,
        "mood": daily.mood if daily else None,
        "note": daily.note if daily else None,
    }


@app.get("/api/log/day")
def get_day_log(date: Optional[str] = None, db: Session = Depends(get_db)):
    return _build_day_log(db, parse_day(date))


@app.get("/api/log/history")
def get_log_history(days: int = 14, db: Session = Depends(get_db)):
    days = max(1, min(days, 90))
    today = today_ar()
    out = []
    for i in range(days - 1, -1, -1):
        d = date.fromordinal(today.toordinal() - i)
        entry = _build_day_log(db, d)
        # Solo días con algo cargado, para no llenar el historial de vacíos
        if entry["meals"] or entry["weight_kg"] or entry["workout"] or entry["steps"] or entry["mood"] or entry["note"]:
            out.append(entry)
    return {"days": out}


@app.get("/api/log/export")
def export_day_log(days: int = 14, db: Session = Depends(get_db)):
    """Texto plano listo para copiar y mandarle a una nutricionista."""
    days = max(1, min(days, 90))
    today = today_ar()
    lines = [f"Registro SHIM — últimos {days} días", ""]
    any_data = False
    for i in range(days - 1, -1, -1):
        d = date.fromordinal(today.toordinal() - i)
        e = _build_day_log(db, d)
        if not (e["meals"] or e["weight_kg"] or e["workout"] or e["steps"] or e["mood"] or e["note"]):
            continue
        any_data = True
        lines.append(f"## {d.isoformat()}")
        if e["weight_kg"] is not None:
            lines.append(f"Peso: {e['weight_kg']} kg")
        if e["workout"]:
            w = e["workout"]
            wk = f" (semana {w['week_n']} · {w['week_label']})" if w.get("week_n") else ""
            lines.append(f"Entrenamiento: {w['day_name']}{wk}")
        else:
            lines.append("Entrenamiento: descanso")
        if e["meals"]:
            t = e["totals"]
            lines.append(f"Comidas ({t['kcal']} kcal · P{t['protein_g']} C{t['carbs_g']} G{t['fat_g']}):")
            for m in e["meals"]:
                lines.append(f"  - {m['name']} — {round(m['kcal'])} kcal (P{round(m['protein_g'])} C{round(m['carbs_g'])} G{round(m['fat_g'])})")
        if e["steps"] is not None:
            lines.append(f"Pasos: {e['steps']}")
        if e["mood"] is not None:
            lines.append(f"Valoración del día: {e['mood']}/5" + (f" — {e['note']}" if e["note"] else ""))
        elif e["note"]:
            lines.append(f"Nota: {e['note']}")
        lines.append("")
    if not any_data:
        lines.append("(sin datos en el rango)")
    return {"text": "\n".join(lines)}


# ---------- Static (last) ----------
app.mount("/", StaticFiles(directory="static", html=True), name="static")
