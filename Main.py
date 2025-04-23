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

    # Etapas de perfil
    if aluno["etapa"] == "inicio":
        aluno["etapa"] = "perfil_nome"
        aluno_db.etapa = aluno["etapa"]
        session.commit()
        return PlainTextResponse(
            "Olá! Sou o Pjotinha, seu instrutor no curso Meu Primeiro CNPJ! Qual o seu nome?"
        )

    elif aluno["etapa"] == "perfil_nome":
        # Usar IA para extrair o nome
        try:
            prompt_nome = f"Extraia apenas o primeiro nome da seguinte frase: '{incoming_msg}'. Responda apenas com o nome, sem mais nada."
            resposta_nome = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt_nome}],
                temperature=0,
            )
            nome_extraido = resposta_nome.choices[0].message["content"].strip()
            aluno["profile"]["nome"] = nome_extraido
        except Exception as e:
            print(f"Erro ao extrair nome: {e}")
            aluno["profile"]["nome"] = incoming_msg  # fallback

        aluno["etapa"] = "perfil_curso"
        aluno_db.etapa = aluno["etapa"]
        aluno_db.perfil = aluno["profile"]
        session.commit()
        return PlainTextResponse(
            f"Prazer em te conhecer, {aluno['profile']['nome']}! Qual o seu curso?"
        )

    elif aluno["etapa"] == "perfil_curso":
        aluno["profile"]["curso"] = incoming_msg
        aluno["etapa"] = "perfil_semestre"
        aluno_db.etapa = aluno["etapa"]
        aluno_db.perfil = aluno["profile"]
        session.commit()
        return PlainTextResponse("Qual semestre você está atualmente?")

    elif aluno["etapa"] == "perfil_semestre":
        aluno["profile"]["semestre"] = incoming_msg
        aluno["etapa"] = "perfil_interesses"
        aluno_db.etapa = aluno["etapa"]
        aluno_db.perfil = aluno["profile"]
        session.commit()
        return PlainTextResponse("Quais são seus interesses no empreendedorismo?")

    elif aluno["etapa"] == "perfil_interesses":
        aluno["profile"]["interesses"] = incoming_msg
        aluno["etapa"] = "pronto"
        aluno_db.etapa = aluno["etapa"]
        aluno_db.perfil = aluno["profile"]
        session.commit()
        return PlainTextResponse(
            "Perfil concluído! Está pronto para começar? Digite *continuar* para iniciar!"
        )

    # Avanço no módulo com subetapas (modulo_pdf_1_1, modulo_pdf_1_2, ...)
    elif aluno["etapa"].startswith("modulo_pdf_1"):
        partes_modulo = {
            "modulo_pdf_1_1": "Parte 1: O que é empreendedorismo? 🚀",
            "modulo_pdf_1_2": "Parte 2: Características de um empreendedor de sucesso.",
            "modulo_pdf_1_3": "Parte 3: Importância do empreendedorismo para a sociedade.",
            "modulo_pdf_1_4": "Final do módulo 1! Pronto para o quiz? Digite *quiz* para começar!",
        }
        proxima_etapa = {
            "modulo_pdf_1_1": "modulo_pdf_1_2",
            "modulo_pdf_1_2": "modulo_pdf_1_3",
            "modulo_pdf_1_3": "modulo_pdf_1_4",
            "modulo_pdf_1_4": "quiz_modulo_1",
        }
        conteudo = partes_modulo.get(aluno["etapa"], "Conteúdo não encontrado.")
        aluno["etapa"] = proxima_etapa.get(aluno["etapa"], "quiz_modulo_1")
        aluno_db.etapa = aluno["etapa"]
        session.commit()
        return PlainTextResponse(f"{conteudo}\n\nDigite *continuar* para avançar.")

    elif aluno["etapa"] == "pronto" and "continuar" in incoming_msg.lower():
        aluno["etapa"] = "modulo_pdf_1_1"
        aluno_db.etapa = aluno["etapa"]
        session.commit()
        return PlainTextResponse(
            "Ótimo! Vamos começar com o primeiro módulo. Digite *continuar* para receber o conteúdo."
        )

    # Fallback com IA + histórico
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
