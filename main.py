from fastapi import FastAPI, Request, Form, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
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

# Gera nova sessão
@app.get("/new")
async def new_chat():
    session_id = str(uuid.uuid4())
    response = RedirectResponse("/")
    response.set_cookie(key="session_id", value=session_id)
    return response

# Banco de dados
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

PROMPT_BASE = """
Você é um assistente virtual treinado para atuar como um psicólogo ou terapeuta de apoio emocional.
Seu papel é acolher o usuário, escutar ativamente, validar sentimentos, fazer perguntas abertas para reflexão e sugerir técnicas de autocuidado, sempre de forma ética, cuidadosa e sem dar diagnósticos ou substituir profissionais de saúde.
Nunca dê diagnósticos clínicos ou recomendações médicas específicas.
Em caso de menção a crise grave (suicídio, autoagressão, violência), oriente a entrar em contato com profissionais de emergência ou CVV (188 no Brasil).
Use linguagem simples e humana, evitando jargões técnicos.

Mensagem do usuário:
{mensagem}

Responda agora, em até 4 frases:
"""

def detectar_crise(mensagem: str) -> bool:
    palavras_criticas = ["suicídio", "me matar", "tirar a vida", "matar", "não aguento mais"]
    return any(p in mensagem.lower() for p in palavras_criticas)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, session_id: str = Cookie(default=None)):
    if not session_id:
        session_id = str(uuid.uuid4())
        resp = RedirectResponse("/")
        resp.set_cookie("session_id", session_id)
        return resp

    db = SessionLocal()
    historico = db.query(LogMensagem).filter_by(session_id=session_id).all()
    db.close()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "historico": historico
    })

@app.post("/", response_class=HTMLResponse)
async def conversar(request: Request, mensagem: str = Form(...), session_id: str = Cookie(...)):
    db = SessionLocal()
    agora = datetime.now().strftime("%H:%M")
    db.add(LogMensagem(session_id=session_id, role="user", mensagem=mensagem, timestamp=agora))
    db.commit()

    if detectar_crise(mensagem):
        resposta = (
            "Percebo que você está em uma situação muito difícil. "
            "Por favor, entre em contato com o CVV pelo telefone 188 ou procure ajuda médica imediatamente. "
            "Você não está sozinho."
        )
    else:
        prompt = PROMPT_BASE.format(mensagem=mensagem)
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": prompt}]
        )
        resposta = completion.choices[0].message.content.strip()

    db.add(LogMensagem(session_id=session_id, role="bot", mensagem=resposta, timestamp=datetime.now().strftime("%H:%M")))
    db.commit()
    historico = db.query(LogMensagem).filter_by(session_id=session_id).all()
    db.close()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "historico": historico
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)