from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
import openai
import os

# Carrega variáveis de ambiente
load_dotenv()

# Cliente OpenAI com base na OpenRouter
client = openai.OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

app = FastAPI()
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

    # Inicia estrutura do aluno se ainda não estiver salva
    if sender not in students:
        students[sender] = {
            "profile": {
                "nome": None,
                "curso": None,
                "semestre": None,
                "interesses": None
            },
            "etapa": "perfil_nome",
            "history": []
        }

    aluno = students[sender]

    # Coleta do perfil por etapas
    etapa = aluno["etapa"]

    if etapa == "perfil_nome":
        aluno["profile"]["nome"] = incoming_msg
        aluno["etapa"] = "perfil_curso"
        return "Legal, {0}! Qual o seu curso ou área de estudo? 🎓".format(incoming_msg)

    elif etapa == "perfil_curso":
        aluno["profile"]["curso"] = incoming_msg
        aluno["etapa"] = "perfil_semestre"
        return "Show! Em qual semestre ou período você está? 📚"

    elif etapa == "perfil_semestre":
        aluno["profile"]["semestre"] = incoming_msg
        aluno["etapa"] = "perfil_interesses"
        return "Perfeito! E quais são seus interesses em empreender? 💡"

    elif etapa == "perfil_interesses":
        aluno["profile"]["interesses"] = incoming_msg
        aluno["etapa"] = "pronto"
        return "Perfil completo! 🎉 Agora vamos começar nosso curso de empreendedorismo 🚀"

    # Geração de resposta da IA após coleta do perfil
    profile = aluno["profile"]
    prompt = f"""
Você é um assistente virtual de um curso de empreendedorismo para universitários.
O aluno se chama {profile['nome']}, cursa {profile['curso']}, está no {profile['semestre']} semestre
e tem interesse em {profile['interesses']}.
Com base nessas informações, responda a seguinte mensagem de forma didática, com energia e usando emojis quando fizer sentido.

Mensagem do aluno: {incoming_msg}
"""

    try:
        response = client.chat.completions.create(
            model="openai/gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Você é um assistente educacional especialista em empreendedorismo."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        reply = response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Erro ao chamar a API da OpenRouter: {e}")
        reply = f"Ocorreu um erro ao processar sua pergunta. Erro técnico: {e}"

    aluno["history"].append(f"Aluno: {incoming_msg}")
    aluno["history"].append(f"IA: {reply}")
    return reply