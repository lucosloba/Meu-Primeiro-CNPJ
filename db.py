from sqlalchemy import Column, Integer, String, JSON, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///alunos.db"

Base = declarative_base()

class Aluno(Base):
    __tablename__ = "alunos"
    id = Column(Integer, primary_key=True, index=True)
    numero_whatsapp = Column(String, unique=True, index=True)
    nome = Column(String)
    curso = Column(String)
    semestre = Column(String)
    interesses = Column(String)
    etapa = Column(String)
    perfil = Column(JSON)
    pontuacao = Column(Integer, default=0)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class HistoricoConversa(Base):
    __tablename__ = "historico_conversas"
    id = Column(Integer, primary_key=True, index=True)
    aluno_id = Column(Integer)
    remetente = Column(String)  # 'aluno' ou 'IA'
    mensagem = Column(String)
    timestamp = Column(String)

Base.metadata.create_all(bind=engine)