from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
import openai
import os
import re

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

def eh_pergunta(texto: str) -> bool:
    texto = texto.lower().strip()
    return texto.endswith("?") or any(texto.startswith(p) for p in ["qual", "quais", "como", "quando", "o que", "por que"])

def responder_e_avancar(etapa_atual, perfil, resposta_aluno):
    prompts = {
        "perfil_nome": {
            "prompt": (
                "Você é um instrutor chamado Pjotinha, responsável pelo curso 'Meu Primeiro CNPJ'. "
                "Você já conhece o aluno e agora quer perguntar o nome dele de forma simpática e clara. "
                "Peça apenas o nome e não faça outras perguntas."
            )
        },
        "perfil_curso": {
            "prompt": (
                f"O aluno se chama {perfil['nome']}. Agora pergunte de forma simpática e clara qual curso ou área de formação o aluno está cursando atualmente. "
                "Evite perguntar onde estuda ou se está interessado. Pergunte apenas o que ele cursa na universidade."
                "Evite falar olá novamente pois você já disse na mensagem de apresentação"
            )
        },
        "perfil_semestre": {
            "prompt": (
                f"O aluno cursa {perfil['curso']}. Agora mostre empolgação com o curso que o aluno faz e pergunte em qual semestre ele está. "
                "Seja direto, simpático e não pergunte mais de uma coisa."
                "Evite falar olá novamente pois você já disse na mensagem de apresentação"
            )
        },
        "perfil_interesses": {
            "prompt": (
                f"O aluno está no {perfil['semestre']} semestre. Agora pergunte apenas sobre os interesses dele em empreender. "
                "Não inclua outras perguntas. Use tom empolgado e próximo."
            )
        },
        "pronto": {
            "prompt": (
                f"Você é o instrutor Pjotinha. O aluno {perfil['nome']} completou o perfil (curso: {perfil['curso']}, semestre: {perfil['semestre']}, interesses: {perfil['interesses']}). "
                "Agradeça de forma simpática por compartilhar essas informações, diga que foi um prazer conhecer ele melhor e finalize com a pergunta: "
                "'Você está pronto para dar o primeiro passo no mundo do empreendedorismo?' Não use a palavra 'perfil'."
            )
        }
    }

    try:
        mensagem = client.chat.completions.create(
            model="openai/gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Você é o instrutor Pjotinha, simpático, direto e focado no curso de empreendedorismo. Nunca faça mais de uma pergunta por vez."},
                {"role": "user", "content": prompts[etapa_atual]["prompt"]}
            ],
            temperature=0.7,
            max_tokens=200
        ).choices[0].message.content.strip()
    except Exception as e:
        print(f"Erro ao gerar resposta da etapa {etapa_atual}: {e}")
        mensagem = "Desculpe, houve um erro. Poderia repetir?"

    return mensagem

def extrair_dado(etapa, entrada):
    instrucoes = {
        "perfil_nome": "Extraia apenas o primeiro nome da mensagem abaixo. Responda só com o nome.",
        "perfil_curso": "Extraia apenas o nome do curso ou área que o aluno está cursando na universidade.",
        "perfil_semestre": "Extraia apenas o número do semestre da universidade em que o aluno está, como 1, 2, 3...",
        "perfil_interesses": "Resuma os interesses empreendedores do aluno com poucas palavras."
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
        print(f"Erro ao extrair dado de {etapa}: {e}")
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
            "etapa": "inicio",
            "history": []
        }

    aluno = students[sender]
    etapa = aluno["etapa"]
    perfil = aluno["profile"]

    if etapa == "inicio":
        aluno["etapa"] = "perfil_nome"
        return (
            "Olá! 👋 Me chamo *Pjotinha*, serei seu instrutor no curso *Meu Primeiro CNPJ*.\n"
            "Posso te conhecer melhor? Como você se chama?"
        )

    if etapa != "pronto":
        if eh_pergunta(incoming_msg):
            # Ignora coleta e responde como assistente livre
            prompt = f"O aluno fez a seguinte pergunta: {incoming_msg}. Responda como o instrutor Pjotinha, de forma clara e empolgada."
            try:
                resposta = client.chat.completions.create(
                    model="openai/gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "Você é o Pjotinha, um instrutor simpático e direto em um curso de empreendedorismo para universitários."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.7,
                    max_tokens=400
                )
                return resposta.choices[0].message.content.strip()
            except Exception as e:
                print(f"Erro ao responder pergunta do aluno: {e}")
                return "Desculpe, tive um problema ao responder. Pode repetir?"

        valor_extraido = extrair_dado(etapa, incoming_msg)
        campo = etapa.replace("perfil_", "")
        aluno["profile"][campo] = valor_extraido

        etapas = ["perfil_nome", "perfil_curso", "perfil_semestre", "perfil_interesses", "pronto"]
        proxima_etapa = etapas[etapas.index(etapa) + 1]
        aluno["etapa"] = proxima_etapa

        return responder_e_avancar(proxima_etapa, aluno["profile"], incoming_msg)

    prompt = f"""
Você é o Pjotinha, assistente virtual do curso de empreendedorismo. O aluno se chama {perfil['nome']}, faz {perfil['curso']}, está no {perfil['semestre']} semestre e tem interesse em {perfil['interesses']}.
Responda a seguinte mensagem com base nesse perfil: "{incoming_msg}"
Seja simpático, informativo e direto.
"""

    try:
        resposta = client.chat.completions.create(
            model="openai/gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Você é um assistente educacional especialista em empreendedorismo, chamado Pjotinha."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        reply = resposta.choices[0].message.content.strip()

    except Exception as e:
        print(f"Erro na resposta livre: {e}")
        reply = "Desculpe, tive um problema técnico. Pode perguntar novamente?"

    aluno["history"].append(f"Aluno: {incoming_msg}")
    aluno["history"].append(f"IA: {reply}")
    return reply