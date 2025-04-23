from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.responses import PlainTextResponse
from db import Aluno as AlunoDB, HistoricoConversa, SessionLocal
from datetime import datetime
import openai
import os
import logging
import glob
import PyPDF2
from contextlib import contextmanager
from sqlalchemy.exc import SQLAlchemyError

# Configuração de logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Configuração da API OpenAI
client = openai.OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"), base_url="https://openrouter.ai/api/v1"
)
app = FastAPI()

# Caminho para a pasta de módulos PDF
PDF_MODULES_PATH = "modulos_pdf/"


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


def extract_text_from_pdf(pdf_path):
    """Extrai texto de um arquivo PDF"""
    try:
        text = ""
        with open(pdf_path, "rb") as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                text += page.extract_text()
        return text
    except Exception as e:
        logger.error(f"Erro ao extrair texto do PDF {pdf_path}: {e}")
        return ""


def get_module_content(module_number):
    """Busca o conteúdo do módulo em PDF"""
    # Procura o arquivo PDF correspondente
    pdf_pattern = f"{PDF_MODULES_PATH}modulo_{module_number}*.pdf"
    pdf_files = glob.glob(pdf_pattern)

    if not pdf_files:
        logger.warning(f"Arquivo PDF para módulo {module_number} não encontrado")
        return "Conteúdo do módulo não encontrado."

    # Extrai texto do primeiro PDF encontrado
    pdf_text = extract_text_from_pdf(pdf_files[0])
    if not pdf_text:
        return "Não foi possível extrair o conteúdo do módulo."

    return pdf_text


def create_lesson_content(module_text, part_number):
    """Cria conteúdo para uma aula específica com base no texto do módulo"""
    try:
        prompt = f"""
        Com base no texto do módulo abaixo, crie o conteúdo para a parte {part_number} da aula.
        O conteúdo deve ser adequado para mensagens de WhatsApp (curto e direto).
        Use emoji ocasionalmente para tornar mais engajador.
        
        TEXTO DO MÓDULO:
        {module_text[:4000]}  # Limitando para não exceder tokens
        
        FORMATO DESEJADO:
        - Título da parte {part_number}
        - 3-4 parágrafos curtos com o conteúdo principal
        - 1 exemplo prático
        - 1 pergunta reflexiva no final
        """

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=500,
        )

        return response.choices[0].message["content"].strip()
    except Exception as e:
        logger.error(f"Erro ao gerar conteúdo da aula: {e}")
        return f"Parte {part_number}: Conteúdo sobre empreendedorismo.\n\nDigite *continuar* para avançar."


def generate_enade_question(module_text, question_number):
    """Gera uma questão de nível ENADE com base no conteúdo do módulo"""
    try:
        prompt = f"""
        Com base no texto do módulo abaixo, crie UMA questão de múltipla escolha de nível ENADE (alta complexidade, exigindo análise crítica).
        A questão deve avaliar compreensão profunda e aplicação do conhecimento, não apenas memorização.
        
        TEXTO DO MÓDULO:
        {module_text[:4000]}  # Limitando para não exceder tokens
        
        FORMATO DESEJADO:
        Questão {question_number}: [texto da questão com um cenário ou caso prático]
        
        A) [alternativa incorreta mas plausível]
        B) [alternativa incorreta mas plausível]
        C) [alternativa correta - não indique que é a correta]
        D) [alternativa incorreta mas plausível]
        E) [alternativa incorreta mas plausível]
        
        A resposta correta é a letra C. [Esta linha é para seu conhecimento, não inclua no resultado final]
        """

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=600,
        )

        # Extraindo a resposta e salvando a correta
        full_response = response.choices[0].message["content"].strip()

        # Extrair apenas a questão sem a linha da resposta
        lines = full_response.split("\n")
        question_only = "\n".join(
            [line for line in lines if not line.startswith("A resposta correta")]
        )

        # Extrair a letra correta
        correct_answer = None
        for line in lines:
            if line.startswith("A resposta correta"):
                parts = line.split("letra ")
                if len(parts) > 1:
                    correct_answer = parts[1][0]  # Pegar a primeira letra após "letra "

        return {"question_text": question_only, "correct_answer": correct_answer}
    except Exception as e:
        logger.error(f"Erro ao gerar questão ENADE: {e}")
        return {
            "question_text": f"Questão {question_number}: O que é empreendedorismo?\n\nA) Processo de abrir empresas\nB) Estudo de mercados\nC) Identificação e exploração de oportunidades\nD) Gestão financeira\nE) Nenhuma das anteriores",
            "correct_answer": "C",
        }


def get_course_content(etapa, aluno_profile=None):
    """Retorna o conteúdo do curso para a etapa atual"""
    # Extrair informações da etapa
    parts = etapa.split("_")

    # Processando etapas de módulo
    if len(parts) >= 3 and parts[0] == "modulo" and parts[1] == "pdf":
        module_number = parts[2]
        part_number = int(parts[3]) if len(parts) > 3 else 1

        # Obter conteúdo do módulo
        module_text = get_module_content(module_number)

        # Criar conteúdo específico para a parte
        content = create_lesson_content(module_text, part_number)

        # Determinar próxima etapa
        if part_number < 4:  # Supondo 4 partes por módulo
            next_stage = f"modulo_pdf_{module_number}_{part_number + 1}"
        else:
            next_stage = f"quiz_modulo_{module_number}_1"  # Ir para o quiz

        return {
            "texto": content,
            "proxima": next_stage,
            "modulo_texto": module_text,  # Passar o texto completo para uso posterior
        }

    # Processando etapas de quiz
    elif len(parts) >= 3 and parts[0] == "quiz" and parts[1] == "modulo":
        module_number = parts[2]
        question_number = int(parts[3]) if len(parts) > 3 else 1

        # Obter conteúdo do módulo para o quiz
        module_text = get_module_content(module_number)

        # Gerar questão
        question_data = generate_enade_question(module_text, question_number)

        # Determinar próxima etapa
        if question_number < 5:  # Supondo 5 questões por quiz
            next_stage = f"quiz_modulo_{module_number}_{question_number + 1}"
        else:
            next_module = int(module_number) + 1
            next_stage = f"modulo_pdf_{next_module}_1"  # Ir para o próximo módulo

        return {
            "texto": question_data["question_text"],
            "proxima": next_stage,
            "resposta_correta": question_data["correct_answer"],
        }

    # Fallback para etapas não reconhecidas
    return {
        "texto": "Conteúdo não encontrado. Digite *menu* para ver as opções disponíveis.",
        "proxima": "menu",
    }


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
            elif aluno["etapa"].startswith(("modulo_", "quiz_")) and (
                "continuar" in incoming_msg.lower() or "quiz" in incoming_msg.lower()
            ):

                conteudo = get_course_content(aluno["etapa"], aluno["profile"])

                # Verificar se é uma etapa de quiz e processar resposta
                if aluno["etapa"].startswith("quiz_") and incoming_msg.lower() not in [
                    "continuar",
                    "quiz",
                ]:
                    # Verificar resposta da questão anterior (se não for a primeira)
                    parts = aluno["etapa"].split("_")
                    if len(parts) > 3 and int(parts[3]) > 1:
                        previous_question = f"quiz_modulo_{parts[2]}_{int(parts[3])-1}"
                        # Carregar questão anterior para verificar resposta
                        previous_content = get_course_content(previous_question)

                        # Verificar se a resposta está correta
                        user_answer = incoming_msg.strip().upper()
                        if len(user_answer) == 1 and user_answer in "ABCDE":
                            if user_answer == previous_content.get(
                                "resposta_correta", ""
                            ):
                                aluno["pontuacao"] += 10
                                resposta = "✓ Correto! +10 pontos\n\n"
                            else:
                                resposta = f"✗ Incorreto. A resposta correta era {previous_content.get('resposta_correta', '')}.\n\n"
                        else:
                            resposta = "Não entendi sua resposta. Por favor, responda com a letra (A, B, C, D ou E).\n\n"

                # Adicionar o conteúdo atual da etapa
                resposta += conteudo["texto"]

                # Instruções para continuar
                if aluno["etapa"].startswith("modulo_"):
                    resposta += "\n\nDigite *continuar* para avançar."
                elif aluno["etapa"].startswith("quiz_"):
                    resposta += "\n\nResponda com a letra da alternativa correta (A, B, C, D ou E)."

                # Atualizar etapa
                aluno["etapa"] = conteudo["proxima"]

            # Verificar resposta do quiz
            elif aluno["etapa"].startswith("quiz_") and incoming_msg.upper() in "ABCDE":
                # Verificar se a resposta está correta
                conteudo = get_course_content(
                    aluno["etapa"].rsplit("_", 1)[0]
                    + "_"
                    + str(int(aluno["etapa"].split("_")[-1]) - 1)
                )

                # Verificar se a resposta está correta
                user_answer = incoming_msg.strip().upper()
                if user_answer == conteudo.get("resposta_correta", ""):
                    aluno["pontuacao"] += 10
                    resposta = "✓ Correto! +10 pontos\n\n"
                else:
                    resposta = f"✗ Incorreto. A resposta correta era {conteudo.get('resposta_correta', '')}.\n\n"

                # Avançar para a próxima questão ou módulo
                next_conteudo = get_course_content(aluno["etapa"])
                resposta += next_conteudo["texto"]

                if aluno["etapa"].startswith("quiz_"):
                    resposta += "\n\nResponda com a letra da alternativa correta (A, B, C, D ou E)."
                else:
                    resposta += "\n\nDigite *continuar* para avançar."

                aluno["etapa"] = next_conteudo["proxima"]

            # Menu de opções
            elif "menu" in incoming_msg.lower():
                resposta = f"""
                🔹 MENU DO CURSO 🔹
                
                Olá {aluno['profile'].get('nome', 'aluno')}!
                
                Pontuação atual: {aluno['pontuacao']} pontos
                
                Digite uma opção:
                1️⃣ *continuar* - Continuar de onde parou
                2️⃣ *modulos* - Ver lista de módulos
                3️⃣ *perfil* - Ver seu perfil
                4️⃣ *ajuda* - Obter ajuda
                """

            # Fallback para IA
            else:
                # Usar IA para responder
                try:
                    historico_conversas = (
                        session.query(HistoricoConversa)
                        .filter_by(aluno_id=aluno_db.id)
                        .order_by(HistoricoConversa.timestamp)
                        .limit(10)  # Limitar histórico para evitar tokens excessivos
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
                        role = "user" if conversa.remetente == "aluno" else "assistant"
                        messages.append({"role": role, "content": conversa.mensagem})

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
                    resposta = (
                        "Desculpe, tive um problema técnico. Pode perguntar novamente?"
                    )

            # Atualizar banco de dados
            try:
                aluno_db.etapa = aluno["etapa"]
                aluno_db.perfil = aluno["profile"]
                aluno_db.pontuacao = aluno["pontuacao"]
                session.commit()
                logger.info(
                    f"Aluno atualizado: {aluno_db.id}, etapa: {aluno_db.etapa}, pontos: {aluno_db.pontuacao}"
                )
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
