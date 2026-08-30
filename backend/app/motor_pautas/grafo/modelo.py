"""O grafo — a estrutura que unifica o que hoje vive em cinco JSONs sem se falar.

## A ideia central

    o que está acontecendo no mundo   ×   como o ser humano reage   =   pauta agora
            (muda todo dia)                   (não muda nunca)

O lado direito é o ativo. Ele não roda — ele **existe**, e é estável: sete
tensões, uma taxonomia de arquétipos, os nove eixos do espaço. O lado esquerdo é
fluxo: publicação regulatória, calendário, trend, notícia.

O grafo é onde os dois se encontram.

## Por que grafo e não tabela

Uma tabela esconde o que mais importa: **o arquétipo é o invariante, a entidade
é a pele local.**

    TENSÃO      dinheiro_esquecido
       │
    ARQUÉTIPO   fundo_verba_trabalhista
       │
       ├── BR ──── FGTS          ●  explorado
       ├── CO ──── Cesantias     ●  explorado
       ├── PE ──── CTS           ●  explorado
       ├── CL ──── ?             ○  VAZIO
       └── CA ──── ?             ○  VAZIO

Um nó de arquétipo com três filhos acesos e o resto apagado. **As arestas
ausentes são o produto.** Uma planilha mostra células vazias como falta de
dado; o grafo mostra como oportunidade — e mostra a propagação quando um evento
acende um nó e você vê quais outros países têm a mesma tensão sem ninguém
atendendo.

## O que NÃO entra aqui

Nenhum valor derivado de lucro ou gasto da operação-exemplo. A taxonomia de
arquétipos vem de lá — os NOMES e as regras de classificação, que são trabalho
de organização — mas o RPM medido não, porque `spend` sozinho previa aquele
alvo com AUC 0,971 e contaminaria o grafo inteiro. Ver `RETIRADO.md`.
"""

from __future__ import annotations

import datetime
import json
from collections import defaultdict
from dataclasses import dataclass, field

# Tipos de nó. A ordem importa para leitura: de universal para local, de estável
# para volátil.
TIPOS_NO = ("tensao", "arquetipo", "pais", "entidade", "evento")

# Tipos de aresta.
#   aciona      arquetipo → tensao      (qual aflição aquele arquétipo mexe)
#   instancia   entidade  → arquetipo   (o nome local de um invariante)
#   habita      entidade  → pais
#   explora     arquetipo → pais        ← A ARESTA QUE INTERESSA: existe ou não
#   ativa       evento    → entidade    (um fato do mundo tocando uma entidade)
TIPOS_ARESTA = ("aciona", "instancia", "habita", "explora", "ativa")

# Estados de uma célula (arquétipo × país). `vazio` não é ausência de dado — é
# o produto do sistema.
VAZIO = "vazio"
ESTADOS = ("forte", "subexplorado", "perdeu", VAZIO)


@dataclass
class No:
    id: str
    tipo: str
    rotulo: str
    atributos: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.tipo not in TIPOS_NO:
            raise ValueError(f"tipo de nó {self.tipo!r} inválido. Use: {TIPOS_NO}")


@dataclass
class Aresta:
    origem: str
    destino: str
    tipo: str
    atributos: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.tipo not in TIPOS_ARESTA:
            raise ValueError(f"tipo de aresta {self.tipo!r} inválido. Use: {TIPOS_ARESTA}")

    @property
    def chave(self) -> tuple[str, str, str]:
        return (self.origem, self.destino, self.tipo)


class Grafo:
    def __init__(self):
        self.nos: dict[str, No] = {}
        self.arestas: dict[tuple, Aresta] = {}
        self._saindo: dict[str, list[Aresta]] = defaultdict(list)
        self._entrando: dict[str, list[Aresta]] = defaultdict(list)

    # ── construção ──────────────────────────────────────────────────────────

    def no(self, id: str, tipo: str, rotulo: str = "", **atrs) -> No:
        """Idempotente: chamar de novo atualiza atributos, não duplica.

        Importa porque o grafo é reconstruído todo dia a partir de fontes que
        se sobrepõem — o calendário e o mapa de entidades falam das mesmas
        entidades, e duplicar quebraria a contagem de células vazias.
        """
        if id in self.nos:
            self.nos[id].atributos.update(atrs)
            if rotulo:
                self.nos[id].rotulo = rotulo
            return self.nos[id]
        n = No(id=id, tipo=tipo, rotulo=rotulo or id, atributos=dict(atrs))
        self.nos[id] = n
        return n

    def liga(self, origem: str, destino: str, tipo: str, **atrs) -> Aresta:
        for lado in (origem, destino):
            if lado not in self.nos:
                raise KeyError(f"nó {lado!r} não existe — crie antes de ligar")
        a = Aresta(origem, destino, tipo, dict(atrs))
        if a.chave in self.arestas:
            self.arestas[a.chave].atributos.update(atrs)
            return self.arestas[a.chave]
        self.arestas[a.chave] = a
        self._saindo[origem].append(a)
        self._entrando[destino].append(a)
        return a

    # ── consulta ────────────────────────────────────────────────────────────

    def por_tipo(self, tipo: str) -> list[No]:
        return [n for n in self.nos.values() if n.tipo == tipo]

    def vizinhos(self, id: str, tipo_aresta: str | None = None,
                 direcao: str = "saindo") -> list[No]:
        arestas = self._saindo[id] if direcao == "saindo" else self._entrando[id]
        if tipo_aresta:
            arestas = [a for a in arestas if a.tipo == tipo_aresta]
        chave = "destino" if direcao == "saindo" else "origem"
        return [self.nos[getattr(a, chave)] for a in arestas]

    def aresta(self, origem: str, destino: str, tipo: str) -> Aresta | None:
        return self.arestas.get((origem, destino, tipo))

    # ── a matriz, que é a adjacência arquétipo × país ───────────────────────

    def celula(self, arquetipo: str, pais: str) -> str:
        """Estado da célula. `vazio` quando não há aresta `explora`."""
        a = self.aresta(arquetipo, pais, "explora")
        return a.atributos.get("estado", VAZIO) if a else VAZIO

    def entidades_de(self, arquetipo: str, pais: str | None = None) -> list[No]:
        ents = self.vizinhos(arquetipo, "instancia", direcao="entrando")
        if pais:
            ents = [e for e in ents if e.atributos.get("pais") == pais]
        return ents

    def forca_do_arquetipo(self, arquetipo: str) -> int:
        """Em quantos países ele já se provou. É o que autoriza transpor.

        Não usa lucro: usa PRESENÇA. Um arquétipo que funcionou em três países
        diferentes, com três nomes locais diferentes, provou que a tensão viaja
        — e é a tensão que estamos transpondo, não o resultado financeiro.
        """
        return sum(1 for p in self.por_tipo("pais")
                   if self.celula(arquetipo, p.id) == "forte")

    def celulas_vazias(self, *, forca_minima: int = 2) -> list[tuple[str, str]]:
        """O produto: arquétipos provados em N+ países, apagados em outro.

        `forca_minima=2` é deliberado. Um arquétipo que funcionou num país só
        pode ser sorte, coincidência local ou execução; funcionar em dois países
        com nomes diferentes é evidência de que a tensão atravessa fronteira.

        Devolve **rótulos**, não IDs — quem consome pensa em `habitacao_popular`
        e `CA`, não em `a:habitacao_popular` e `p:CA`. Devolver ID aqui já
        custou um bug de prefixo duplo.
        """
        out = []
        for arq in self.por_tipo("arquetipo"):
            if self.forca_do_arquetipo(arq.id) < forca_minima:
                continue
            for p in self.por_tipo("pais"):
                if self.celula(arq.id, p.id) == VAZIO:
                    out.append((arq.rotulo, p.rotulo))
        return out

    def eventos_ativos(self, hoje: datetime.date, *, janela_dias: int = 120) -> list[No]:
        """Eventos que estão acontecendo ou vêm aí. É o pulso do lado esquerdo."""
        out = []
        for e in self.por_tipo("evento"):
            d = e.atributos.get("data")
            if not d:
                continue
            dias = (datetime.date.fromisoformat(d) - hoje).days
            if -30 <= dias <= janela_dias:
                out.append(e)
        return sorted(out, key=lambda e: e.atributos.get("data", ""))

    # ── saída ───────────────────────────────────────────────────────────────

    def resumo(self) -> dict:
        por_tipo = {t: len(self.por_tipo(t)) for t in TIPOS_NO}
        por_aresta: dict[str, int] = defaultdict(int)
        for a in self.arestas.values():
            por_aresta[a.tipo] += 1
        estados: dict[str, int] = defaultdict(int)
        for arq in self.por_tipo("arquetipo"):
            for p in self.por_tipo("pais"):
                estados[self.celula(arq.id, p.id)] += 1
        return {
            "nos": por_tipo,
            "arestas": dict(por_aresta),
            "celulas": dict(estados),
            "total_celulas": len(self.por_tipo("arquetipo")) * len(self.por_tipo("pais")),
        }

    def exportar(self) -> dict:
        return {
            "nos": [{"id": n.id, "tipo": n.tipo, "rotulo": n.rotulo, **n.atributos}
                    for n in self.nos.values()],
            "arestas": [{"origem": a.origem, "destino": a.destino, "tipo": a.tipo,
                         **a.atributos} for a in self.arestas.values()],
        }

    def para_mermaid(self, arquetipo: str, *, max_paises: int = 12) -> str:
        """Um arquétipo e seus países — aceso e apagado.

        A visualização que uma tabela não dá: filho aceso é país onde a tensão
        já tem nome; apagado é onde ela existe e ninguém atende.
        """
        arq = self.nos.get(arquetipo)
        if arq is None:
            raise KeyError(f"arquétipo {arquetipo!r} não está no grafo")
        tensoes = self.vizinhos(arquetipo, "aciona")
        L = ["graph TD"]
        if tensoes:
            t = tensoes[0]
            L.append(f'  T["🧠 {t.rotulo}"]')
            L.append(f'  A["{arq.rotulo}"]')
            L.append("  T --> A")
        else:
            L.append(f'  A["{arq.rotulo}"]')

        # ordena para que os acesos venham primeiro: o olho lê o que existe
        # antes de reparar no que falta, e é a falta que é o produto
        ordem = {"forte": 0, "subexplorado": 1, "perdeu_dinheiro": 2, "perdeu": 2, VAZIO: 3}
        paises = sorted(self.por_tipo("pais"),
                        key=lambda p: ordem.get(self.celula(arquetipo, p.id), 9))
        for p in paises[:max_paises]:
            estado = self.celula(arquetipo, p.id)
            ents = self.entidades_de(arquetipo, p.rotulo)
            nome = ents[0].rotulo if ents else "—"
            marca = {"forte": "●", "subexplorado": "◐",
                     "perdeu_dinheiro": "✕", "perdeu": "✕"}.get(estado, "○")
            nid = p.rotulo.replace("-", "_")
            L.append(f'  A --> {nid}["{marca} {p.rotulo} · {nome[:26]}"]')
            if estado == VAZIO:
                L.append(f"  style {nid} fill:#fff3cd,stroke:#d39e00,stroke-width:3px")
            elif estado in ("perdeu", "perdeu_dinheiro"):
                L.append(f"  style {nid} fill:#f8d7da,stroke:#842029")
            elif estado == "forte":
                L.append(f"  style {nid} fill:#d1e7dd,stroke:#0f5132")
        return "\n".join(L)


def salvar(g: Grafo, caminho) -> None:
    import pathlib
    p = pathlib.Path(caminho)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(g.exportar(), ensure_ascii=False, indent=1))
