"""Armazenamento PRIVADO e TEMPORÁRIO dos anexos, no host do backend.

Por que não Supabase Storage na V1: exigiria bucket e política novos no banco
oficial (checkpoint próprio). O contrato `Armazem` isola isso — a troca por um
bucket privado com URL assinada curta é uma implementação nova da mesma porta,
sem tocar no resto (ver HANDOFF).

Garantias:
- diretório raiz e por dono 0700, arquivos 0600; dono = auth UUID do token;
  o caminho nunca vem do navegador (id é uuid4 gerado aqui);
- gravação em temporário + rename: upload interrompido não deixa arquivo;
- anexo de outro dono, expirado ou inexistente = `None` (a rota responde 404);
- deduplicação por SHA-256 dentro do mesmo dono;
- cota por dono (quantidade e bytes ativos) e retenção de RETENCAO_DIAS;
- limpeza preguiçosa a cada upload e por `limpar_expirados()` (rotina do operador).
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import threading
import time
import re
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from app.agente_bia.anexos import dominio as dm
from app.agente_bia.anexos.extracao import processar

_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def diretorio_padrao() -> Path:
    return Path(os.environ.get("BIA_ANEXOS_DIR") or (Path.home() / ".volc-os" / "bia-anexos"))


@dataclass(frozen=True)
class Anexo:
    id: str
    dono: str
    nome: str
    tipo: str
    mime: str
    familia: str
    tamanho: int
    sha256: str
    sha256_original: str
    criado_em: str
    expira_em: str
    paginas: Optional[int] = None
    largura: Optional[int] = None
    altura: Optional[int] = None
    caracteres: Optional[int] = None
    truncado: bool = False

    def publico(self) -> Dict[str, object]:
        d = asdict(self)
        d.pop("dono")
        d.pop("sha256_original")
        return d

    def referencia(self) -> Dict[str, object]:
        """O que vai para `execucao.contexto` no ledger (cabe em 2 KB com 4 anexos)."""
        return {"id": self.id, "nome": self.nome[:80], "tipo": self.tipo, "familia": self.familia,
                "tamanho": self.tamanho, "sha256": self.sha256}


class CotaExcedida(dm.AnexoRecusado):
    pass


class Armazem:
    def __init__(self, raiz: Optional[Path] = None, *, relogio=None) -> None:
        self.raiz = Path(raiz) if raiz else diretorio_padrao()
        self._agora = relogio or (lambda: datetime.now(timezone.utc))
        self._travas: Dict[str, threading.Lock] = {}
        self._travas_lock = threading.Lock()

    # ── caminhos ──────────────────────────────────────────────────────────
    def _pasta(self, dono: str) -> Path:
        pasta = self.raiz / hashlib.sha256(dono.encode()).hexdigest()[:24]
        pasta.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.raiz, 0o700)
        os.chmod(pasta, 0o700)
        return pasta

    def _gravar(self, destino: Path, dados: bytes) -> None:
        fd, tmp = tempfile.mkstemp(dir=str(destino.parent), prefix=".tmp-")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(dados)
            os.replace(tmp, destino)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _ler_meta(self, pasta: Path, anexo_id: str) -> Optional[Anexo]:
        try:
            return Anexo(**json.loads((pasta / f"{anexo_id}.json").read_text()))
        except (OSError, ValueError, TypeError):
            return None

    # ── consulta ──────────────────────────────────────────────────────────
    def obter(self, dono: str, anexo_id: str) -> Optional[Anexo]:
        if not _ID.fullmatch(anexo_id or ""):
            return None
        a = self._ler_meta(self._pasta(dono), anexo_id)
        if a is None or a.dono != dono or self._expirado(a):
            return None
        return a

    def listar(self, dono: str) -> List[Anexo]:
        pasta = self._pasta(dono)
        saida = []
        for p in pasta.glob("*.json"):
            a = self._ler_meta(pasta, p.stem)
            if a and a.dono == dono and not self._expirado(a):
                saida.append(a)
        return sorted(saida, key=lambda a: a.criado_em)

    def bytes_de(self, dono: str, anexo_id: str) -> Optional[bytes]:
        a = self.obter(dono, anexo_id)
        if a is None:
            return None
        try:
            return (self._pasta(dono) / f"{anexo_id}.bin").read_bytes()
        except OSError:
            return None

    def texto_de(self, dono: str, anexo_id: str) -> Optional[str]:
        a = self.obter(dono, anexo_id)
        if a is None or a.familia != "documento":
            return None
        try:
            return (self._pasta(dono) / f"{anexo_id}.txt").read_text(encoding="utf-8")
        except OSError:
            return None

    # ── escrita ───────────────────────────────────────────────────────────
    @contextlib.contextmanager
    def _travado(self, dono: str):
        """Uma escrita por dono por vez: threads deste processo E outros processos (flock)."""
        pasta = self._pasta(dono)
        with self._travas_lock:
            trava = self._travas.setdefault(pasta.name, threading.Lock())
        with trava:
            with self._abrir_trava(pasta) as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    yield pasta
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)

    @staticmethod
    def _abrir_trava(pasta: Path):
        return os.fdopen(os.open(pasta / ".trava", os.O_RDWR | os.O_CREAT, 0o600), "r+")

    def guardar(self, dono: str, dados: bytes, nome: str, content_type: Optional[str]) -> Anexo:
        nome = dm.normalizar_nome(nome)
        tipo = dm.identificar(dados, nome, content_type)
        sha_original = hashlib.sha256(dados).hexdigest()
        # Decodificar/extrair é a parte cara: fora da trava. Cota, deduplicação e
        # gravação ficam dentro dela, juntas — sem corrida entre uploads paralelos.
        proc = processar(dados, tipo)
        with self._travado(dono) as pasta:
            self._limpar_pasta(pasta)
            for existente in self.listar(dono):
                if existente.sha256_original == sha_original:
                    # mesmo arquivo do mesmo dono: não ocupa cota de novo, e ganha validade nova
                    renovado = Anexo(**{**asdict(existente), "expira_em": (
                        self._agora() + timedelta(days=dm.RETENCAO_DIAS)).isoformat()})
                    self._gravar(pasta / f"{existente.id}.json",
                                 json.dumps(asdict(renovado), ensure_ascii=False).encode())
                    return renovado
            ativos = self.listar(dono)
            if len(ativos) >= dm.MAX_ANEXOS_ATIVOS_POR_USUARIO or \
                    sum(a.tamanho for a in ativos) + len(proc.dados) > dm.MAX_BYTES_ATIVOS_POR_USUARIO:
                raise CotaExcedida("cota_excedida",
                                   "Limite de anexos guardados atingido. Remova anexos ou aguarde a limpeza.")
            return self._escrever(pasta, dono, nome, tipo, proc, sha_original)

    def _escrever(self, pasta: Path, dono: str, nome: str, tipo, proc, sha_original: str) -> Anexo:
        agora = self._agora()
        anexo = Anexo(
            id=str(uuid.uuid4()), dono=dono, nome=nome, tipo=tipo.chave, mime=tipo.mime,
            familia=tipo.familia, tamanho=len(proc.dados),
            sha256=hashlib.sha256(proc.dados).hexdigest(), sha256_original=sha_original,
            criado_em=agora.isoformat(), expira_em=(agora + timedelta(days=dm.RETENCAO_DIAS)).isoformat(),
            paginas=proc.paginas, largura=proc.largura, altura=proc.altura,
            caracteres=len(proc.texto) if proc.texto is not None else None, truncado=proc.truncado,
        )
        self._gravar(pasta / f"{anexo.id}.bin", proc.dados)
        if proc.texto is not None:
            self._gravar(pasta / f"{anexo.id}.txt", proc.texto.encode("utf-8"))
        # metadado por último: sem ele o anexo não "existe" (upload interrompido some sozinho)
        self._gravar(pasta / f"{anexo.id}.json", json.dumps(asdict(anexo), ensure_ascii=False).encode())
        return anexo

    def remover(self, dono: str, anexo_id: str) -> bool:
        if self.obter(dono, anexo_id) is None:
            return False
        with self._travado(dono) as pasta:
            for ext in (".json", ".bin", ".txt"):
                (pasta / f"{anexo_id}{ext}").unlink(missing_ok=True)
        return True

    # ── retenção ──────────────────────────────────────────────────────────
    def _expirado(self, a: Anexo) -> bool:
        try:
            return datetime.fromisoformat(a.expira_em) <= self._agora()
        except ValueError:
            return True

    def limpar_expirados(self, dono: Optional[str] = None) -> int:
        """Remove anexos expirados (de um dono, ou de todos) e temporários órfãos."""
        if not self.raiz.exists():
            return 0
        if dono:
            with self._travado(dono) as pasta:
                return self._limpar_pasta(pasta)
        n = 0
        for pasta in [p for p in self.raiz.iterdir() if p.is_dir()]:
            with self._travas_lock:
                trava = self._travas.setdefault(pasta.name, threading.Lock())
            with trava, self._abrir_trava(pasta) as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    n += self._limpar_pasta(pasta)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        return n

    def _limpar_pasta(self, pasta: Path) -> int:
        """Chamado SEMPRE com a trava do dono. Temporário/órfão só se for velho."""
        velho = time.time() - dm.IDADE_MINIMA_ORFAO_S
        idade = lambda p: p.stat().st_mtime if p.exists() else time.time()  # noqa: E731
        n = 0
        for tmp in pasta.glob(".tmp-*"):
            if idade(tmp) < velho:
                tmp.unlink(missing_ok=True)
        for meta in pasta.glob("*.json"):
            a = self._ler_meta(pasta, meta.stem)
            if a is None or self._expirado(a):
                for ext in (".json", ".bin", ".txt"):
                    (pasta / f"{meta.stem}{ext}").unlink(missing_ok=True)
                n += 1
        for orfao in pasta.glob("*.bin"):
            if not (pasta / f"{orfao.stem}.json").exists() and idade(orfao) < velho:
                orfao.unlink(missing_ok=True)
                (pasta / f"{orfao.stem}.txt").unlink(missing_ok=True)
        return n
