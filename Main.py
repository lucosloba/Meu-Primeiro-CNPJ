from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
import openai
import os

# Carrega variáveis de ambiente do .env
load_dotenv()

# 🔐 Configuração da OpenRouter
openai.api_key = os.getenv("OPENROUTER_API_KEY")
openai.api_base = "https://openrouter.ai/api/v1"

app = FastAPI()

# Armazena informações básicas por aluno (em memória para testes)
students = {}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/webhook", response_class=PlainTextResponse)
async def webhook(request: Request):
    form = await request.form()
    incoming_msg = form.get("Body", "").strip()
    sender = form.get("From", "")

    if not incoming_msg or not sender:
        return "Mensagem inválida."

    # Inicializa histórico se aluno for novo
    if sender not in students:
        students[sender] = {"history": []}

    students[sender]["history"].append(f"Aluno: {incoming_msg}")

    # Prompt que será enviado ao modelo
    prompt = f"""
Você é um assistente virtual de um curso de empreendedorismo voltado para estudantes universitários brasileiros.
Seja claro, didático, empolgado, e utilize emojis de forma leve para manter o engajamento.
Mensagem do aluno: {incoming_msg}
"""

    try:
        response = openai.ChatCompletion.create(
            model="openai/gpt-3.5-turbo",  # Modelo gratuito via OpenRouter
            messages=[
                {"role": "system", "content": "Você é um assistente educacional especialista em empreendedorismo."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        reply = response.choices[0].message["content"].strip()

    except Exception as e:
        print(f"Erro ao chamar a API da OpenRouter: {e}")
        reply = f"Ocorreu um erro ao processar sua pergunta. Erro técnico: {e}"

    students[sender]["history"].append(f"IA: {reply}")
    return reply
