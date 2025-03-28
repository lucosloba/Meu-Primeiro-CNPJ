from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
import openai
import os

load_dotenv()

# Nova forma de instanciar o cliente da OpenAI
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()

# Simples armazenamento em memória (para testes)
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

    if sender not in students:
        students[sender] = {"history": []}

    students[sender]["history"].append(f"Aluno: {incoming_msg}")

    prompt = f"""
Você é um assistente virtual especialista em empreendedorismo para estudantes universitários.
Responda com clareza, linguagem acessível, emojis quando fizer sentido, e mostre entusiasmo!
Mensagem do aluno: {incoming_msg}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Você é um assistente educacional especialista em empreendedorismo."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000,
        )
        reply = response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Erro ao chamar a API da OpenAI: {e}")
        reply = f"Ocorreu um erro com a IA: {e}"

    students[sender]["history"].append(f"IA: {reply}")
    return reply
