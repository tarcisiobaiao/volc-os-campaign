"""Regras puras dos anexos: o que entra, quanto entra, e como se reconhece pelos bytes.

O tipo é decidido pela ASSINATURA dos bytes, conferida contra a extensão e o
Content-Type declarados. Divergência é recusa, não correção: um `.png` que é
ZIP, um `.pdf` que é HTML ou um `.txt` com bytes nulos não entram.

Nunca aceitos por padrão: executável, HTML, SVG, script, ZIP genérico, arquivo
aninhado. DOCX é ZIP, e por isso passa por conferência própria (estrutura OOXML
mínima, sem macro, sem objeto embutido, tamanho descompactado limitado).
"""
from __future__ import annotations

import re
import unicodedata
import zipfile
from dataclasses import dataclass
from io import BytesIO
from typing import Dict, FrozenSet, Optional


class AnexoRecusado(ValueError):
    """`codigo` estável para a interface; `mensagem` em português, sem detalhe interno."""

    def __init__(self, codigo: str, mensagem: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo
        self.mensagem = mensagem


@dataclass(frozen=True)
class TipoAceito:
    chave: str          # png | jpeg | webp | pdf | txt | csv | docx
    mime: str
    extensoes: FrozenSet[str]
    familia: str        # imagem | documento
    max_bytes: int


MB = 1024 * 1024

TIPOS: Dict[str, TipoAceito] = {
    "png": TipoAceito("png", "image/png", frozenset({".png"}), "imagem", 3 * MB),
    "jpeg": TipoAceito("jpeg", "image/jpeg", frozenset({".jpg", ".jpeg"}), "imagem", 3 * MB),
    "webp": TipoAceito("webp", "image/webp", frozenset({".webp"}), "imagem", 3 * MB),
    "pdf": TipoAceito("pdf", "application/pdf", frozenset({".pdf"}), "documento", 10 * MB),
    "txt": TipoAceito("txt", "text/plain", frozenset({".txt", ".md"}), "documento", 2 * MB),
    "csv": TipoAceito("csv", "text/csv", frozenset({".csv"}), "documento", 2 * MB),
    "docx": TipoAceito(
        "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        frozenset({".docx"}), "documento", 10 * MB),
}

#: Limites por mensagem e por usuário. A soma de imagens em base64 precisa caber
#: nos 10 MB do corpo aceito pelo API Server do Hermes (MAX_REQUEST_BYTES).
MAX_ANEXOS_POR_MENSAGEM = 4
MAX_IMAGENS_POR_MENSAGEM = 3
MAX_BYTES_IMAGENS_POR_MENSAGEM = 6 * MB
MAX_CARACTERES_POR_DOCUMENTO = 20_000
MAX_CARACTERES_DOCUMENTOS_POR_MENSAGEM = 40_000   # cabe na parte de texto de 64 KB
MAX_ANEXOS_ATIVOS_POR_USUARIO = 40
MAX_BYTES_ATIVOS_POR_USUARIO = 80 * MB
RETENCAO_DIAS = 7
MAX_PIXELS_IMAGEM = 40_000_000           # contra bomba de descompressão
MAX_LADO_IMAGEM = 8_000
MAX_DESCOMPACTADO_DOCX = 40 * MB
MAX_ENTRADAS_DOCX = 2_000

#: Assinaturas que nunca entram, mesmo com extensão "certa".
_PROIBIDAS = (
    (b"MZ", "executável Windows"),
    (b"\x7fELF", "executável Linux"),
    (b"\xcf\xfa\xed\xfe", "executável macOS"),
    (b"\xca\xfe\xba\xbe", "executável macOS"),
    (b"#!", "script"),
)
_MARCAS_HTML = re.compile(rb"^\s*(<\?xml|<!doctype\s+html|<html|<svg|<script)", re.I)


def normalizar_nome(nome: str) -> str:
    """Nome de exibição seguro: sem caminho, sem controle, NFC, até 120 caracteres."""
    base = (nome or "").replace("\\", "/").split("/")[-1]
    base = unicodedata.normalize("NFC", base)
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip().strip(".")
    if not base:
        base = "arquivo"
    if len(base) > 120:
        raiz, ponto, ext = base.rpartition(".")
        base = (raiz[: 110 - len(ext)] + "…." + ext) if ponto and len(ext) <= 8 else base[:120]
    return base


def extensao(nome: str) -> str:
    m = re.search(r"(\.[A-Za-z0-9]{1,8})$", nome or "")
    return m.group(1).lower() if m else ""


def _eh_texto(dados: bytes) -> bool:
    if b"\x00" in dados[:65536]:
        return False
    try:
        dados[:65536].decode("utf-8")
        return True
    except UnicodeDecodeError:
        # aceita latin-1/cp1252 comum em CSV exportado, desde que sem controle
        amostra = dados[:65536]
        controle = sum(1 for b in amostra if b < 9 or (13 < b < 32))
        return controle == 0


def _docx_valido(dados: bytes) -> None:
    try:
        z = zipfile.ZipFile(BytesIO(dados))
    except zipfile.BadZipFile as exc:
        raise AnexoRecusado("docx_invalido", "O DOCX está corrompido.") from exc
    infos = z.infolist()
    if len(infos) > MAX_ENTRADAS_DOCX:
        raise AnexoRecusado("docx_invalido", "O DOCX tem estrutura grande demais.")
    if sum(i.file_size for i in infos) > MAX_DESCOMPACTADO_DOCX:
        raise AnexoRecusado("docx_invalido", "O DOCX descompactado passa do limite.")
    nomes = {i.filename for i in infos}
    if "[Content_Types].xml" not in nomes or "word/document.xml" not in nomes:
        raise AnexoRecusado("docx_invalido", "O arquivo não é um DOCX do Word.")
    for n in nomes:
        baixo = n.lower()
        if "vbaproject" in baixo or baixo.endswith((".bin", ".exe", ".dll", ".js")) \
                or baixo.startswith("word/embeddings/"):
            raise AnexoRecusado("docx_com_conteudo_ativo",
                                "O DOCX tem macro ou objeto embutido; envie uma cópia sem eles.")


def identificar(dados: bytes, nome: str, content_type: Optional[str]) -> TipoAceito:
    """O tipo pelos BYTES, conferido contra extensão e Content-Type. Ou recusa."""
    if not dados:
        raise AnexoRecusado("arquivo_vazio", "O arquivo está vazio.")
    for assinatura, rotulo in _PROIBIDAS:
        if dados.startswith(assinatura):
            raise AnexoRecusado("tipo_proibido", f"Arquivo recusado: {rotulo}.")
    ext = extensao(nome)
    por_bytes: Optional[str] = None
    if dados.startswith(b"\x89PNG\r\n\x1a\n"):
        por_bytes = "png"
    elif dados.startswith(b"\xff\xd8\xff"):
        por_bytes = "jpeg"
    elif dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        por_bytes = "webp"
    elif dados.startswith(b"%PDF-"):
        por_bytes = "pdf"
    elif dados.startswith(b"PK\x03\x04"):
        if ext != ".docx":
            raise AnexoRecusado("tipo_proibido", "Arquivo compactado não é aceito.")
        _docx_valido(dados)
        por_bytes = "docx"
    elif _eh_texto(dados):
        if _MARCAS_HTML.match(dados[:512]):
            raise AnexoRecusado("tipo_proibido", "HTML, SVG ou script não são aceitos.")
        por_bytes = "csv" if ext == ".csv" else "txt"

    if por_bytes is None:
        raise AnexoRecusado("tipo_nao_suportado",
                            "Tipo não suportado. Use PNG, JPEG, WebP, PDF, TXT, CSV ou DOCX.")
    tipo = TIPOS[por_bytes]
    if ext not in tipo.extensoes:
        raise AnexoRecusado("tipo_divergente",
                            f"A extensão {ext or '(nenhuma)'} não corresponde ao conteúdo ({tipo.chave.upper()}).")
    declarado = (content_type or "").split(";")[0].strip().lower()
    if declarado and declarado not in (tipo.mime, "application/octet-stream") and \
            not (tipo.chave in ("txt", "csv") and declarado.startswith("text/")):
        raise AnexoRecusado("tipo_divergente", "O tipo declarado não corresponde ao conteúdo.")
    if len(dados) > tipo.max_bytes:
        raise AnexoRecusado("arquivo_grande",
                            f"{tipo.chave.upper()} acima de {tipo.max_bytes // MB} MB.")
    return tipo
