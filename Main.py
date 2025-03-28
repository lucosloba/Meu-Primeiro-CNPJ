from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
import openai
import os

load_dotenv()

client = openai.OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

app = FastAPI()
students = {}

@app.get("/health")
def health():
    return {"status": "ok"}

def responder_e_avancar(etapa_atual, perfil, resposta_aluno):
    prompts = {
        "perfil_nome": {
            "pergunta": "Qual o seu nome?",
            "prompt": "Você está conhecendo um aluno novo e quer saber o nome dele. Responda com simpatia e pergunte o nome."
        },
        "perfil_curso": {
            "pergunta": "Qual o seu curso ou área de estudo?",
            "prompt": f"O aluno respondeu: '{resposta_aluno}'. Você já sabe que o nome dele é {perfil['nome']}. Comente de forma simpática e pergunte o curso."
        },
        "perfil_semestre": {
            "pergunta": "Qual semestre ou período você está?",
            "prompt": f"O aluno disse que faz {perfil['curso']}. Agora comente e pergunte o semestre atual."
        },
        "perfil_interesses": {
            "pergunta": "Quais são seus interesses em empreender?",
            "prompt": f"O aluno está no {perfil['semestre']} semestre. Comente e pergunte o que motiva ele a empreender."
        },
        "pronto": {
            "pergunta": "",
            "prompt": f"O aluno {perfil['nome']} já informou todo o perfil. Diga algo empolgado sobre começar o curso agora."
        }
    }

    etapa = etapa_atual
    dados = prompts[etapa]

    try:
        resposta = client.chat.completions.create(
            model="openai/gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Você é um mentor educacional simpático, empático e que conversa com universitários sobre empreendedorismo."},
                {"role": "user", "content": dados["prompt"]}
            ],
            temperature=0.7,
            max_tokens=200
        )
        mensagem = resposta.choices[0].message.content.strip()
    except Exception as e:
        print(f"Erro ao gerar resposta na etapa {etapa}: {e}")
        mensagem = dados["pergunta"]

    return mensagem

def extrair_dado(etapa, entrada):
    instrucoes = {
        "perfil_nome": "Extraia apenas o primeiro nome da mensagem abaixo. Responda só com o nome.",
        "perfil_curso": "Extraia apenas o nome do curso ou área de estudo da mensagem abaixo. Responda só com o curso.",
        "perfil_semestre": "Extraia apenas o número do semestre ou período da mensagem abaixo. Ex: 1, 2, 3, etc.",
        "perfil_interesses": "Resuma os principais interesses empreendedores da mensagem abaixo em poucas palavras."
    }

    try:
        resultado = client.chat.completions.create(
            model="openai/gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": instrucoes[etapa]},
                {"role": "user", "content": entrada}
            ],
            temperature=0.3,
            max_tokens=30
        )
        return resultado.choices[0].message.content.strip()
    except Exception as e:
        print(f"Erro ao extrair dado da etapa {etapa}: {e}")
        return entrada

@app.post("/webhook", response_class=PlainTextResponse)
async def webhook(request: Request):
    form = await request.form()
    incoming_msg = form.get("Body", "").strip()
    sender = form.get("From", "")

    if not incoming_msg or not sender:
        return "Mensagem inválida."

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
    etapa = aluno["etapa"]
    perfil = aluno["profile"]

    if etapa != "pronto":
        valor_extraido = extrair_dado(etapa, incoming_msg)
        campo = etapa.replace("perfil_", "")
        aluno["profile"][campo] = valor_extraido

        # Avança para a próxima etapa
        etapas = ["perfil_nome", "perfil_curso", "perfil_semestre", "perfil_interesses", "pronto"]
        proxima_etapa = etapas[etapas.index(etapa) + 1]
        aluno["etapa"] = proxima_etapa

        return responder_e_avancar(proxima_etapa, aluno["profile"], incoming_msg)

    # Se perfil já foi coletado
    prompt = f"""
Você é um assistente virtual de um curso de empreendedorismo para universitários.
O aluno se chama {perfil['nome']}, cursa {perfil['curso']}, está no {perfil['semestre']} semestre
e tem interesse em {perfil['interesses']}.
Com base nessas informações, responda a seguinte mensagem de forma didática, com energia e usando emojis quando fizer sentido.

Mensagem do aluno: {incoming_msg}
"""

    try:
        resposta = client.chat.completions.create(
            model="openai/gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Você é um assistente educacional especialista em empreendedorismo."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        reply = resposta.choices[0].message.content.strip()

    except Exception as e:
        print(f"Erro ao responder o aluno: {e}")
        reply = f"Ocorreu um erro ao processar sua pergunta. Erro técnico: {e}"

    aluno["history"].append(f"Aluno: {incoming_msg}")
    aluno["history"].append(f"IA: {reply}")
    return reply