from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import PlainTextResponse
from db import Aluno as AlunoDB, HistoricoConversa, SessionLocal
from datetime import datetime
import openai
import os
import logging
from contextlib import contextmanager
from sqlalchemy.exc import SQLAlchemyError

# Configuração de logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuração da API OpenAI
openai.api_key = os.environ.get("OPENAI_API_KEY", "sua_api_key_aqui")

app = FastAPI()


@contextmanager
def get_db_session():
    """Context manager para sessões do banco de dados"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def extract_name(text):
    """Extrai o primeiro nome de um texto usando a API OpenAI"""
    try:
        prompt_nome = f"Extraia apenas o primeiro nome da seguinte frase: '{text}'. Responda apenas com o nome, sem pontuação ou informações adicionais."
        resposta_nome = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt_nome}],
            temperature=0,
            max_tokens=50,
        )
        nome_extraido = resposta_nome.choices[0].message["content"].strip()
        return nome_extraido
    except Exception as e:
        logger.error(f"Erro ao extrair nome: {e}")
        # Tenta extrair o nome usando lógica simples
        words = text.split()
        if len(words) >= 1:
            # Tenta remover prefixos comuns
            if words[0].lower() in ["meu", "eu", "sou", "o", "a"]:
                return words[1] if len(words) > 1 else text
            return words[0]
        return text


def save_message(session, aluno_id, remetente, mensagem):
    """Salva uma mensagem no histórico de conversas"""
    try:
        historico = HistoricoConversa(
            aluno_id=aluno_id,
            remetente=remetente,
            mensagem=mensagem,
            timestamp=datetime.now().isoformat(),
        )
        session.add(historico)
        session.commit()
        return True
    except SQLAlchemyError as e:
        logger.error(f"Erro ao salvar mensagem: {e}")
        session.rollback()
        return False


def get_course_content(etapa):
    """Retorna o conteúdo do curso para a etapa atual"""
    conteudos = {
        "modulo_pdf_1_1": {
            "texto": "Parte 1: O que é empreendedorismo? 🚀\n\nEmpreendedorismo é o processo de identificar oportunidades e transformá-las em negócios viáveis. Um empreendedor é alguém que cria algo novo, assume riscos calculados e busca inovação.",
            "proxima": "modulo_pdf_1_2",
        },
        "modulo_pdf_1_2": {
            "texto": "Parte 2: Características de um empreendedor de sucesso.\n\nUm empreendedor de sucesso geralmente apresenta: visão de futuro, capacidade de assumir riscos, criatividade, persistência, liderança e adaptabilidade.",
            "proxima": "modulo_pdf_1_3",
        },
        "modulo_pdf_1_3": {
            "texto": "Parte 3: Importância do empreendedorismo para a sociedade.\n\nO empreendedorismo impulsiona a economia, gera empregos, promove inovação e contribui para o desenvolvimento social e econômico.",
            "proxima": "modulo_pdf_1_4",
        },
        "modulo_pdf_1_4": {
            "texto": "Final do módulo 1! Pronto para o quiz? Digite *quiz* para começar!",
            "proxima": "quiz_modulo_1",
        },
        "quiz_modulo_1": {
            "texto": "Pergunta 1: Qual é a principal característica de um empreendedor?\nA) Medo de riscos\nB) Aversão a mudanças\nC) Visão de oportunidade\nD) Preferência por estabilidade",
            "proxima": "quiz_modulo_1_2",
        },
    }
    return conteudos.get(
        etapa, {"texto": "Conteúdo não encontrado", "proxima": "pronto"}
    )


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        form = await request.form()
        incoming_msg = form.get("Body", "").strip()
        sender = form.get("From", "")

        if not sender or not incoming_msg:
            logger.warning("Mensagem ou remetente vazios")
            return PlainTextResponse("Não foi possível processar a mensagem.")

        logger.info(f"Mensagem recebida de {sender}: {incoming_msg}")

        with get_db_session() as session:
            # Buscar ou criar aluno
            aluno_db = session.query(AlunoDB).filter_by(numero_whatsapp=sender).first()
            if not aluno_db:
                logger.info(f"Criando novo aluno para {sender}")
                aluno_db = AlunoDB(
                    numero_whatsapp=sender, etapa="inicio", perfil={}, pontuacao=0
                )
                session.add(aluno_db)
                session.commit()

            # Estrutura do aluno
            aluno = {
                "etapa": aluno_db.etapa,
                "profile": aluno_db.perfil or {},
                "pontuacao": aluno_db.pontuacao or 0,
            }

            # Salvar mensagem do aluno
            save_message(session, aluno_db.id, "aluno", incoming_msg)

            # Lógica de processamento por etapa
            resposta = ""

            # Início do curso e coleta de perfil
            if aluno["etapa"] == "inicio":
                aluno["etapa"] = "perfil_nome"
                resposta = "Olá! Sou o Pjotinha, seu instrutor no curso Meu Primeiro CNPJ! Qual o seu nome?"

            elif aluno["etapa"] == "perfil_nome":
                nome_extraido = extract_name(incoming_msg)
                aluno["profile"]["nome"] = nome_extraido
                aluno["etapa"] = "perfil_curso"
                resposta = f"Prazer em te conhecer, {nome_extraido}! Qual o seu curso?"

            elif aluno["etapa"] == "perfil_curso":
                aluno["profile"]["curso"] = incoming_msg
                aluno["etapa"] = "perfil_semestre"
                resposta = "Qual semestre você está atualmente?"

            elif aluno["etapa"] == "perfil_semestre":
                aluno["profile"]["semestre"] = incoming_msg
                aluno["etapa"] = "perfil_interesses"
                resposta = "Quais são seus interesses no empreendedorismo?"

            elif aluno["etapa"] == "perfil_interesses":
                aluno["profile"]["interesses"] = incoming_msg
                aluno["etapa"] = "pronto"
                resposta = f"Prazer em te conhecer, {aluno['profile'].get('nome', 'aluno')}! Está pronto para começar? Digite *continuar* para iniciar!"

            # Lógica do curso
            elif aluno["etapa"] == "pronto" and "continuar" in incoming_msg.lower():
                aluno["etapa"] = "modulo_pdf_1_1"
                resposta = "Ótimo! Vamos começar com o primeiro módulo. Digite *continuar* para receber o conteúdo."

            # Módulos e quizzes
            elif (
                aluno["etapa"].startswith(("modulo_", "quiz_"))
                and "continuar" in incoming_msg.lower()
            ):
                conteudo = get_course_content(aluno["etapa"])
                resposta = conteudo["texto"] + "\n\nDigite *continuar* para avançar."
                aluno["etapa"] = conteudo["proxima"]

            # Fallback para IA
            else:
                # Verificar se o usuário quer avançar independente da etapa
                if "continuar" in incoming_msg.lower() and aluno["etapa"].startswith(
                    ("modulo_", "quiz_", "pronto")
                ):
                    conteudo = get_course_content(aluno["etapa"])
                    resposta = (
                        conteudo["texto"] + "\n\nDigite *continuar* para avançar."
                    )
                    aluno["etapa"] = conteudo["proxima"]
                else:
                    # Usar IA para responder
                    try:
                        historico_conversas = (
                            session.query(HistoricoConversa)
                            .filter_by(aluno_id=aluno_db.id)
                            .order_by(HistoricoConversa.timestamp)
                            .limit(
                                10
                            )  # Limitar histórico para evitar tokens excessivos
                            .all()
                        )

                        # Preparar contexto para a IA
                        perfil_info = f"Perfil do aluno: Nome: {aluno['profile'].get('nome', 'desconhecido')}, Curso: {aluno['profile'].get('curso', 'desconhecido')}, Semestre: {aluno['profile'].get('semestre', 'desconhecido')}, Interesses: {aluno['profile'].get('interesses', 'desconhecidos')}"

                        messages = [
                            {
                                "role": "system",
                                "content": f"Você é o Pjotinha, um assistente educacional especialista em empreendedorismo que está ministrando o curso 'Meu Primeiro CNPJ'. {perfil_info}. Etapa atual: {aluno['etapa']}. Mantenha respostas curtas e objetivas, adequadas para WhatsApp.",
                            }
                        ]

                        # Adicionar histórico à conversa
                        for conversa in historico_conversas:
                            role = (
                                "user" if conversa.remetente == "aluno" else "assistant"
                            )
                            messages.append(
                                {"role": role, "content": conversa.mensagem}
                            )

                        # Adicionar mensagem atual
                        messages.append({"role": "user", "content": incoming_msg})

                        # Chamar API
                        ai_response = openai.ChatCompletion.create(
                            model="gpt-3.5-turbo",
                            messages=messages,
                            temperature=0.7,
                            max_tokens=500,
                        )

                        resposta = ai_response.choices[0].message["content"].strip()

                    except Exception as e:
                        logger.error(f"Erro na resposta da IA: {e}")
                        resposta = "Desculpe, tive um problema técnico. Pode perguntar novamente?"

            # Atualizar banco de dados
            try:
                aluno_db.etapa = aluno["etapa"]
                aluno_db.perfil = aluno["profile"]
                aluno_db.pontuacao = aluno["pontuacao"]
                session.commit()
                logger.info(f"Aluno atualizado: {aluno_db.id}, etapa: {aluno_db.etapa}")
            except SQLAlchemyError as e:
                logger.error(f"Erro ao atualizar aluno: {e}")
                session.rollback()

            # Salvar resposta no histórico
            background_tasks.add_task(
                save_message, session, aluno_db.id, "IA", resposta
            )

            return PlainTextResponse(resposta)

    except Exception as e:
        logger.error(f"Erro não tratado: {e}", exc_info=True)
        return PlainTextResponse(
            "Desculpe, ocorreu um erro inesperado. Por favor, tente novamente mais tarde."
        )
