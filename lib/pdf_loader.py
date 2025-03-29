import fitz  # PyMuPDF

def carregar_pdf_completo(caminho_pdf: str) -> str:
    """Lê o conteúdo completo de um arquivo PDF e retorna como string única"""
    texto = ""
    with fitz.open(caminho_pdf) as doc:
        for pagina in doc:
            texto += pagina.get_text()
    return texto.strip()