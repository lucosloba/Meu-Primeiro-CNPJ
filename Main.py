from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from db import Aluno as AlunoDB, HistoricoConversa, SessionLocal
from datetime import datetime
import openai
import os

app = FastAPI()


@app.post("/webhook")
async def webhook(request: Request):
    form = await request.form()
    incoming_msg = form.get("Body")
    sender = form.get("From")

    # Conectar ao banco de dados
    session = SessionLocal()
    aluno_db = session.query(AlunoDB).filter_by(numero_whatsapp=sender).first()
    if not aluno_db:
        aluno_db = AlunoDB(numero_whatsapp=sender, etapa="inicio", perfil={})
        session.add(aluno_db)
        session.commit()

    aluno = {
        "etapa": aluno_db.etapa,
        "profile": aluno_db.perfil or {},
        "pontuacao": aluno_db.pontuacao,
    }

    # Salvar mensagem do aluno no histórico
    historico = HistoricoConversa(
        aluno_id=aluno_db.id,
        remetente="aluno",
        mensagem=incoming_msg,
        timestamp=datetime.now().isoformat(),
    )
    session.add(historico)
    session.commit()

    # Etapas do fluxo
    if aluno["etapa"] == "inicio":
        aluno["etapa"] = "perfil_nome"
        aluno_db.etapa = aluno["etapa"]
        session.commit()
        return PlainTextResponse(
            "Olá! Sou o Pjotinha, seu instrutor no curso Meu Primeiro CNPJ! Qual o seu nome?"
        )

    elif aluno["etapa"].startswith("perfil_"):
        campo = aluno["etapa"].replace("perfil_", "")
        aluno["profile"][campo] = incoming_msg
        # Próxima etapa
        proximas_etapas = {
            "nome": "perfil_curso",
            "curso": "perfil_semestre",
            "semestre": "perfil_interesses",
            "interesses": "pronto",
        }
        aluno["etapa"] = proximas_etapas.get(campo, "pronto")
        aluno_db.etapa = aluno["etapa"]
        aluno_db.perfil = aluno["profile"]
        session.commit()
        if aluno["etapa"] == "perfil_curso":
            return PlainTextResponse(
                f"Prazer em te conhecer, {aluno['profile']['nome']}! Qual o seu curso?"
            )
        elif aluno["etapa"] == "perfil_semestre":
            return PlainTextResponse("Qual semestre você está atualmente?")
        elif aluno["etapa"] == "perfil_interesses":
            return PlainTextResponse("Quais são seus interesses no empreendedorismo?")
        elif aluno["etapa"] == "pronto":
            return PlainTextResponse(
                "Perfil concluído! Está pronto para começar? Digite *continuar* para iniciar!"
            )

    elif aluno["etapa"] == "pronto" and "continuar" in incoming_msg.lower():
        aluno["etapa"] = "modulo_pdf_1"
        aluno_db.etapa = aluno["etapa"]
        session.commit()
        return PlainTextResponse(
            "Ótimo! Vamos começar com o primeiro módulo. Digite *continuar* para receber o conteúdo."
        )

    elif aluno["etapa"] == "modulo_pdf_1" and "continuar" in incoming_msg.lower():
        # Conteúdo do módulo
        conteudo = "Este é o início do módulo sobre empreendedorismo. 🚀"
        return PlainTextResponse(f"{conteudo}\n\nDigite *continuar* para avançar.")

    # Se não cair em nenhuma etapa, responder com IA usando histórico
    try:
        historico_conversas = (
            session.query(HistoricoConversa)
            .filter_by(aluno_id=aluno_db.id)
            .order_by(HistoricoConversa.timestamp)
            .all()
        )
        messages = [
            {
                "role": "system",
                "content": "Você é um assistente educacional especialista em empreendedorismo, chamado Pjotinha.",
            }
        ]
        for conversa in historico_conversas:
            role = "user" if conversa.remetente == "aluno" else "assistant"
            messages.append({"role": role, "content": conversa.mensagem})
        messages.append({"role": "user", "content": incoming_msg})

        resposta = openai.ChatCompletion.create(
            model="gpt-3.5-turbo", messages=messages, temperature=0.7, max_tokens=1000
        )

        reply = resposta.choices[0].message["content"].strip()
        historico_ia = HistoricoConversa(
            aluno_id=aluno_db.id,
            remetente="IA",
            mensagem=reply,
            timestamp=datetime.now().isoformat(),
        )
        session.add(historico_ia)
        session.commit()
        return PlainTextResponse(reply)

    except Exception as e:
        print(f"Erro na resposta da IA: {e}")
        return PlainTextResponse(
            "Desculpe, tive um problema técnico. Pode perguntar novamente?"
        )
