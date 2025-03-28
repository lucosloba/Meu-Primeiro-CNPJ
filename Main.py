from fastapi import FastAPI, Request
from pydantic import BaseModel
from fastapi.responses import PlainTextResponse
import os
import openai
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

openai.api_key = os.getenv("OPENAI_API_KEY")

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
        return "Mensagem inválida"

    if sender not in students:
        students[sender] = {"history": []}

    students[sender]["history"].append(f"Aluno: {incoming_msg}")

    prompt = f"""
Você é um assistente virtual de um curso de empreendedorismo para universitários.
Responda com uma linguagem clara, motivadora, usando emojis quando fizer sentido.
Mensagem do aluno: {incoming_msg}
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Você é um assistente educacional especialista em empreendedorismo."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000,
        )
        reply = response.choices[0].message["content"]
    except Exception as e:
        reply = "Desculpe, houve um erro ao processar sua mensagem."

    students[sender]["history"].append(f"IA: {reply}")
    return reply
