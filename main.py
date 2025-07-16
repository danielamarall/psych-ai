from fastapi import FastAPI, Request, Form, Cookie
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
import os
import uuid
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Novo chat
@app.get("/new")
async def new_chat():
    session_id = str(uuid.uuid4())
    response = RedirectResponse("/")
    response.set_cookie("session_id", session_id)
    return response

# DB
Base = declarative_base()
engine = create_engine("sqlite:///db.sqlite3")
SessionLocal = sessionmaker(bind=engine)

class LogMensagem(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True)
    session_id = Column(String)
    role = Column(String)
    mensagem = Column(String)
    timestamp = Column(String)

Base.metadata.create_all(bind=engine)

# Prompt
PROMPT_BASE = """
Você é um assistente virtual treinado para atuar como um psicólogo ...
Mensagem do usuário:
{mensagem}
Responda em até 4 frases:
"""

def detectar_crise(m: str) -> bool:
    crit = ["suicídio","me matar","tirar a vida","matar","não aguento mais"]
    return any(p in m.lower() for p in crit)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, session_id: str = Cookie(None)):
    if not session_id:
        sid = str(uuid.uuid4())
        resp = RedirectResponse("/")
        resp.set_cookie("session_id", sid)
        return resp
    db = SessionLocal()
    hist = db.query(LogMensagem).filter_by(session_id=session_id).all()
    db.close()
    return templates.TemplateResponse("index.html", {"request": request, "historico": hist})

@app.post("/api/chat", response_class=JSONResponse)
async def api_chat(mensagem: str = Form(...), session_id: str = Cookie(...)):
    db = SessionLocal()
    ts_user = datetime.now().strftime("%H:%M")
    db.add(LogMensagem(session_id=session_id, role="user", mensagem=mensagem, timestamp=ts_user))
    db.commit()

    if detectar_crise(mensagem):
        resposta = ("Percebo que você está em situação difícil. ..."
                    "Procure ajuda médica ou CVV 188.")
    else:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        prompt = PROMPT_BASE.format(mensagem=mensagem)
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role":"system","content":prompt}]
        )
        resposta = res.choices[0].message.content.strip()

    ts_bot = datetime.now().strftime("%H:%M")
    db.add(LogMensagem(session_id=session_id, role="bot", mensagem=resposta, timestamp=ts_bot))
    db.commit()
    db.close()

    return {"mensagem": resposta, "timestamp": ts_bot}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)