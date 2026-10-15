"""GTM read-only com capacidades SEM hierarquia.

LEITURA, EDITAR, CRIAR_VERSAO e PUBLICAR são concedidas uma a uma; nenhuma
implica outra, e PUBLICAR nunca é herdada de LEITURA. O teto do laboratório é
só LEITURA: ampliá-lo exige commit humano explícito neste arquivo e um OAuth
novo com os escopos de edição, que hoje não foram concedidos.

ClienteGTMLeitura só faz GET e não tem método de criar versão ou publicar.
"""
from __future__ import annotations

import enum
import time
from dataclasses import asdict, dataclass, field

from .google_credencial import sessao as _sessao_padrao
from .recibos import agora_utc

BASE = "https://tagmanager.googleapis.com/tagmanager/v2"
PAUSA_S = 1.2  # ~0,83 req/s; abaixo do limite por usuário observado sem 429 na prova de 15/10


class CapacidadeGTM(enum.Enum):
    LEITURA = "readonly"
    EDITAR = "edit"
    CRIAR_VERSAO = "create_version"
    PUBLICAR = "publish"


ESCOPO = {
    CapacidadeGTM.LEITURA: "https://www.googleapis.com/auth/tagmanager.readonly",
    CapacidadeGTM.EDITAR: "https://www.googleapis.com/auth/tagmanager.edit.containers",
    CapacidadeGTM.CRIAR_VERSAO: "https://www.googleapis.com/auth/tagmanager.edit.containerversions",
    CapacidadeGTM.PUBLICAR: "https://www.googleapis.com/auth/tagmanager.publish",
}

#: O que o Freedom Lab pode conceder. Mudar isto é decisão humana com commit próprio.
TETO_DO_LAB = frozenset({CapacidadeGTM.LEITURA})


class CapacidadeNegada(PermissionError):
    pass


@dataclass(frozen=True)
class ConcessaoGTM:
    capacidades: frozenset
    motivo: str

    def __post_init__(self):
        fora = frozenset(self.capacidades) - TETO_DO_LAB
        if fora:
            raise CapacidadeNegada(f"fora do teto do lab: {sorted(c.value for c in fora)}")
        if len(self.motivo.strip()) < 10:
            raise CapacidadeNegada("concessão exige motivo descritivo")

    def exigir(self, cap: CapacidadeGTM) -> None:
        if cap not in self.capacidades:  # pertença exata; nada implica nada
            raise CapacidadeNegada(f"{cap.value} não concedida explicitamente")

    def escopos(self) -> frozenset[str]:
        return frozenset(ESCOPO[c] for c in self.capacidades)


@dataclass
class InventarioGTM:
    accounts: int = 0
    containers: int = 0
    workspaces: int = 0
    workspaces_inventariados: int = 0
    tags: int = 0
    triggers: int = 0
    variables: int = 0
    erros_http: dict[str, int] = field(default_factory=dict)  # listas perdidas: contagem é piso
    recuos_429: int = 0
    escopos_efetivos: list[str] = field(default_factory=list)
    em: str = ""

    def recibo(self) -> dict:
        return {"broker": "gtm", "operacao": "leitura:inventario", **asdict(self)}


class ClienteGTMLeitura:
    def __init__(self, concessao: ConcessaoGTM, *, fabrica_sessao=_sessao_padrao, pausa_s=PAUSA_S):
        concessao.exigir(CapacidadeGTM.LEITURA)
        self._s = fabrica_sessao(concessao.escopos())
        self._pausa = pausa_s

    def _listar(self, caminho: str, chave: str, inv: InventarioGTM) -> list[dict]:
        itens, token = [], None
        while True:
            if self._pausa:
                time.sleep(self._pausa)
            for tentativa in range(4):  # 429 = cota; recua e tenta de novo
                r = self._s.get(f"{BASE}/{caminho}", params={"pageToken": token} if token else None,
                                timeout=30)
                if r.status_code != 429:
                    break
                inv.recuos_429 += 1
                if self._pausa and tentativa < 3:
                    time.sleep(self._pausa * 5 * 2 ** tentativa)
            if r.status_code != 200:
                k = str(r.status_code)
                inv.erros_http[k] = inv.erros_http.get(k, 0) + 1
                return itens
            d = r.json()
            itens += d.get(chave, [])
            token = d.get("nextPageToken")
            if not token:
                return itens

    def inventariar(self, *, todos_workspaces: bool = True, limite_containers: int | None = None) -> InventarioGTM:
        inv = InventarioGTM(escopos_efetivos=sorted(getattr(self._s, "escopos_efetivos", ())))
        for a in self._listar("accounts", "account", inv):
            inv.accounts += 1
            for c in self._listar(f"{a['path']}/containers", "container", inv):
                if limite_containers is not None and inv.containers >= limite_containers:
                    break
                inv.containers += 1
                ws = self._listar(f"{c['path']}/workspaces", "workspace", inv)
                inv.workspaces += len(ws)
                for w in ws if todos_workspaces else ws[:1]:
                    inv.workspaces_inventariados += 1
                    inv.tags += len(self._listar(f"{w['path']}/tags", "tag", inv))
                    inv.triggers += len(self._listar(f"{w['path']}/triggers", "trigger", inv))
                    inv.variables += len(self._listar(f"{w['path']}/variables", "variable", inv))
        inv.em = agora_utc()
        return inv
