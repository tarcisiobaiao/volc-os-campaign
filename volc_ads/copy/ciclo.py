"""A cascata de retry — cada falha com o remédio mais barato que a resolve.

## O princípio

Falha de FORMA se conserta em código. Falha de CONTAGEM a mais se corta. Falha
de política regenera UM asset. Só a ancoragem mentindo refaz o conjunto — e ela
refaz porque a mentira invalida a auditoria inteira, não porque foi mais fácil.

Nada aqui retenta transporte: `TRANSIENT` e `THROTTLED` já são resolvidos pela
`PoliticaRetry` de `gads/client.py`, e duplicar backoff produz backoff ao
quadrado. Nada aqui retenta o mesmo texto contra política — retentar política
não é ineficiência, é chamar atenção.

## Os tetos, e por que são por asset

  TETO_ASSET = 2   regenerações por asset
  parada dura      a MESMA regra falhando duas vezes no mesmo asset encerra
                   aquele asset. O modelo não está errando por azar: está
                   errando por não entender a regra, e a terceira tentativa
                   custa o mesmo e erra igual.
  TETO_REFAZ = 1   refazer o conjunto inteiro

Um contador global permitiria 6 regenerações do mesmo título teimoso enquanto
outro asset reprovado nunca é tocado. Por asset, cada um tem seu orçamento e o
esgotamento de um não consome o do outro.

## O orçamento de cota, que é o insumo fácil de esquecer

Regenerar um título isolado sem saber o que os SOBREVIVENTES já gastaram
produz o substituto que passa em forma, passa em política e estoura a seção 6
— a quinta pergunta num conjunto de teto 3. Por isso `_prompt_asset` recebe
`orcamento_restante()`, e por isso o C6 roda em CÓDIGO sobre o conjunto
pós-substituição, não no modelo.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Protocol

from ..gads.errors import FalhaGads
from ..ponte import extract_json
from .contrato import (
    AUTO_DECLARACAO,
    Achado,
    Alvo,
    Classe,
    Pedido,
    checar,
    comprimento_efetivo,
    cortar_excesso,
    faixas,
    medir,
    orcamento_restante,
    sanear,
)
from .mock import SISTEMA_ASSET, SISTEMA_COMPLETO

TETO_ASSET = 2
TETO_REFAZ = 1
TETO_RODADAS = 8


class Cliente(Protocol):
    """Contrato do cliente de texto. `cliente.py` e `mock.py` o cumprem igual."""

    def gerar(self, sistema: str, usuario: str) -> str: ...


# O juiz do Google é INJETADO: em produção é `validar_mutacoes` (validate_only,
# leitura); no banco de provas é o `JuizMock`. A cascata não sabe a diferença,
# e é isso que permite provar a cascata inteira sem rede e sem custo.
Juiz = Callable[[dict], FalhaGads | None]

# O juiz de SENTIDO, opcional. Recebe o payload e devolve achados — é ele que
# decide o que regex não decide (nome próprio × alegação, marca × grito).
# `None` mantém o comportamento antigo: C7 e C8 determinísticos ligados.
# Ver `copy/juiz_semantico.py` para por que essa fronteira existe.
JuizSemantico = Callable[[dict], list[Achado]]


@dataclass
class Estado:
    """Tudo que a cascata precisa lembrar entre rodadas."""

    regras_por_asset: dict[str, list[str]] = field(default_factory=dict)
    geracoes_por_asset: Counter = field(default_factory=Counter)
    refazes: int = 0
    abandonados: dict[str, str] = field(default_factory=dict)
    saneamentos: list[str] = field(default_factory=list)
    cortes: list[str] = field(default_factory=list)
    diario: list[str] = field(default_factory=list)

    def registrar(self, alvo: Alvo, codigo: str) -> bool:
        """Anota a regra e diz se ainda vale tentar este asset.

        False quando a MESMA regra já falhou nele, ou quando o teto estourou.
        """
        chave = str(alvo)
        vistas = self.regras_por_asset.setdefault(chave, [])
        if codigo in vistas:
            self.abandonados[chave] = f"{codigo} falhou duas vezes"
            return False
        if self.geracoes_por_asset[chave] >= TETO_ASSET:
            self.abandonados[chave] = f"teto de {TETO_ASSET} regenerações"
            return False
        vistas.append(codigo)
        return True

    def anotar(self, linha: str) -> None:
        self.diario.append(linha)


@dataclass
class Resultado:
    ok: bool
    dados: dict
    pendentes: list[Achado] = field(default_factory=list)
    estado: Estado = field(default_factory=Estado)
    geracoes_conjunto: int = 0
    geracoes_asset: int = 0

    def relatorio(self) -> str:
        linhas = list(self.estado.diario)
        linhas.append("")
        linhas.append(
            f"veredito: {'ACEITO' if self.ok else 'PARCIAL'}  ·  "
            f"gerações de conjunto: {self.geracoes_conjunto}  ·  "
            f"de asset: {self.geracoes_asset}"
        )
        if self.estado.abandonados:
            for chave, motivo in self.estado.abandonados.items():
                linhas.append(f"  abandonado {chave}: {motivo}")
        for a in self.pendentes:
            linhas.append(f"  pendente {a}")
        return "\n".join(linhas)


# ── entrada ─────────────────────────────────────────────────────────────────


def gerar(
    *,
    cliente: Cliente,
    juiz: Juiz,
    pedido: Pedido,
    prompt_usuario: str,
    fatos_texto: str = "",
    # O juiz de SENTIDO. Quando presente, C7 e C8 determinísticos são desligados
    # em `checar()` — ver a docstring dela para os números que motivaram isso.
    juiz_semantico: JuizSemantico | None = None,
) -> Resultado:
    """Roda a cascata até aceitar, esgotar tetos, ou não ter mais o que tentar."""
    estado = Estado()
    dados: dict = {}
    pendentes: list[Achado] = []
    n_conjunto = 0
    n_asset = 0

    bruto = cliente.gerar(SISTEMA_COMPLETO, prompt_usuario)
    n_conjunto += 1
    estado.anotar("rodada 1 · geração do conjunto")

    for rodada in range(1, TETO_RODADAS + 1):
        # ── parse, com o reparo determinístico do backend ───────────────────
        try:
            dados = extract_json(bruto)
        except ValueError as exc:
            estado.anotar(f"  ✗ JSON ilegível mesmo após reparo: {exc}")
            if estado.refazes >= TETO_REFAZ:
                pendentes = [Achado("C1.json", Classe.ESTRUTURA, str(exc))]
                break
            estado.refazes += 1
            estado.anotar(f"  → refaz o conjunto ({estado.refazes}/{TETO_REFAZ})")
            bruto = cliente.gerar(SISTEMA_COMPLETO, prompt_usuario)
            n_conjunto += 1
            continue
        if rodada == 1:
            estado.anotar("  ✓ JSON parseado (reparo determinístico disponível)")

        # ── saneamento e corte: tudo que não custa LLM ──────────────────────
        dados, feitos = sanear(dados)
        if feitos:
            estado.saneamentos += feitos
            estado.anotar(f"  ✓ saneado sem LLM ×{len(feitos)}: {feitos[0]}")
        cortados = cortar_excesso(dados, pedido)
        if cortados:
            estado.cortes += cortados
            estado.anotar(f"  ✓ excesso cortado sem LLM: {'; '.join(cortados)}")

        # ── os juízes ───────────────────────────────────────────────────────
        achados = [a for a in checar(dados, pedido,
                                     semantico_ativo=juiz_semantico is not None)
                   if a.classe is not Classe.CONTAGEM_EXCESSO]
        # ⚠️ O juiz de sentido roda DEPOIS do determinístico e só quando a
        # estrutura está de pé — julgar sentido de um JSON quebrado é gastar
        # LLM para descobrir que o JSON está quebrado.
        if juiz_semantico is not None and not any(
                a.classe is Classe.ESTRUTURA for a in achados):
            achados += juiz_semantico(dados)
        falha = juiz(dados)
        if falha is not None:
            achados += _achados_do_google(falha, dados, estado)

        if not achados:
            estado.anotar("  ✓ contrato + Google: sem achados")
            return Resultado(True, dados, [], estado, n_conjunto, n_asset)

        estado.anotar(f"  contrato + Google: {len(achados)} achado(s)")
        for a in achados[:6]:
            estado.anotar(f"      {a}")

        # ── ancoragem mentindo: o ÚNICO caminho que refaz o conjunto ────────
        # E ele tem GATILHO, não é qualquer deslize. O C4 do PROMPT.md manda
        # refazer a passada 1 quando "mais de um terço dos títulos cai" — não
        # quando um título erra a contagem de caracteres por um. Implementar
        # sem o limiar transformava uma mentira isolada em regeneração do
        # conjunto, que é exatamente a preguiça que a cascata existe para
        # evitar: um título estourado derrubava os catorze bons junto.
        #
        # Mentira de CONJUNTO (sem alvo — ancoragem desalinhada, contagem_final
        # divergente) não tem versão por asset: ela invalida a auditoria
        # inteira, e aí o gatilho dispara sozinho.
        # ⚠️ AUTO-DECLARAÇÃO NÃO GASTA O REFAZER — e gastava.
        #
        # `C4.chars` e `C6.divergencia` são o modelo errando a CONTABILIDADE
        # QUE ELE MESMO ESCREVEU ("declarou 7, medido 8" num marcador de
        # estilo). O que eles declaram já é medido de forma independente, então
        # a divergência não muda uma letra do que vai ao ar.
        #
        # Medido no card 65 em 19/08/2026: a C9 gerou o achado certo — os
        # termos de busca em 7 de 15 títulos, precisos 9 — e a cascata morreu
        # antes de corrigi-lo, porque `C4.chars` levou o primeiro refazer e
        # `C6.divergencia` bateu no teto. Um erro de contagem cosmético
        # consumiu o orçamento que o defeito PUBLICÁVEL precisava, e o anúncio
        # subiu com Ad Strength ruim.
        #
        # Elas continuam em `achados`, então viram pendência na tela. O que
        # muda é que não disparam mais a regeneração do conjunto.
        mentiras = [a for a in achados
                    if a.classe is Classe.ANCORAGEM_MENTIU
                    and a.codigo not in AUTO_DECLARACAO]
        de_conjunto = [a for a in mentiras if a.alvo is None]
        limiar = max(1, pedido.n_headlines // 3)
        if de_conjunto or len(mentiras) > limiar:
            if de_conjunto:
                estado.anotar(
                    f"  · mentira de conjunto ({de_conjunto[0].codigo}): "
                    f"não há versão por asset")
            else:
                estado.anotar(
                    f"  · {len(mentiras)} mentiras > limiar {limiar} "
                    f"(um terço de {pedido.n_headlines})")
            if estado.refazes >= TETO_REFAZ:
                estado.anotar(
                    f"  ✗ ancoragem mentiu de novo e o teto de refazer "
                    f"({TETO_REFAZ}) estourou — não refaço em laço"
                )
                pendentes = achados
                break
            estado.refazes += 1
            estado.anotar(
                f"  → C4: a passada 2 foi teatro ({mentiras[0].codigo}). "
                f"Refaz a passada 1 inteira ({estado.refazes}/{TETO_REFAZ})"
            )
            bruto = cliente.gerar(SISTEMA_COMPLETO, prompt_usuario)
            n_conjunto += 1
            continue

        # ── tudo o mais é por asset ─────────────────────────────────────────
        agiu = False
        for alvo, grupo in _agrupar(achados).items():
            codigo = grupo[0].codigo
            if alvo is None:
                continue
            if not estado.registrar(alvo, codigo):
                estado.anotar(
                    f"  ⊘ {alvo} abandonado: {estado.abandonados[str(alvo)]}")
                continue
            estado.geracoes_por_asset[str(alvo)] += 1
            n_asset += 1
            agiu = True
            n = estado.geracoes_por_asset[str(alvo)]
            estado.anotar(
                f"  → regenera SÓ {alvo} ({n}/{TETO_ASSET}) por {codigo}")
            _regenerar(cliente, dados, alvo, grupo, pedido, estado, fatos_texto)

        if not agiu:
            estado.anotar("  ✗ nada mais a tentar sem violar teto")
            pendentes = achados
            break

        # ── C6 em CÓDIGO, sobre o conjunto pós-substituição ─────────────────
        _reconciliar(dados, pedido, estado)
        fora = _cotas_fora(dados, pedido)
        if fora:
            estado.anotar(f"  ! C6 pós-substituição: {'; '.join(fora)}")

        bruto = _rebruto(dados)

    else:
        estado.anotar(f"  ✗ teto de {TETO_RODADAS} rodadas")

    return Resultado(False, dados, pendentes, estado, n_conjunto, n_asset)


# ── do erro do Google para o asset ──────────────────────────────────────────


def _achados_do_google(
    falha: FalhaGads, dados: dict, estado: Estado
) -> list[Achado]:
    """Traduz a reprovação da API em achados endereçados a assets.

    É aqui que a reescrita de `gads/errors.py` paga: `textos_violadores` vem de
    `policy_violation_details.key.violating_text` e das evidências de texto dos
    `policy_topic_entries`. Sem isso o único achado possível seria "algo em
    algum lugar das 72 operações", e o único remédio seria regenerar tudo.
    """
    if not falha.de_politica:
        # Terminal sem política é defeito de FORMA que passou pelo juiz 1 —
        # regenerar não conserta um `string_length_error`, conserta-se o juiz.
        return [Achado("G.forma", Classe.FORMA_REESCREVER,
                       f"terminal não-política: {falha.resumo()[:160]}",
                       _por_caminho(falha, dados))]

    out: list[Achado] = []
    for texto in falha.textos_violadores:
        alvo = _localizar(dados, texto) or _por_caminho(falha, dados)
        isento = any(k.violating_text == texto for k in falha.chaves_isentaveis)
        marca = " [isentável]" if isento else ""
        out.append(Achado(
            "G.politica", Classe.FORMA_REESCREVER,
            f"reprovado pela API{marca}: {texto!r}", alvo))
    if not out:
        out.append(Achado("G.politica_sem_texto", Classe.FORMA_REESCREVER,
                          falha.resumo()[:160], _por_caminho(falha, dados)))
    return out


def _localizar(dados: dict, texto: str) -> Alvo | None:
    """Acha o asset cujo texto é exatamente o que a API apontou."""
    for tipo, chave in (("headline", "headlines"), ("description", "descriptions"),
                        ("callout", "callouts")):
        for i, t in enumerate(dados.get(chave) or []):
            if str(t) == texto:
                return Alvo(tipo, i)
    for i, s in enumerate(dados.get("sitelinks") or []):
        if not isinstance(s, dict):
            continue
        for sub in ("title", "description1", "description2"):
            if str(s.get(sub, "")) == texto:
                return Alvo("sitelink", i, sub)
    for i, v in enumerate((dados.get("snippet") or {}).get("values") or []):
        if str(v) == texto:
            return Alvo("snippet", i)
    return None


def _por_caminho(falha: FalhaGads, dados: dict) -> Alvo | None:
    """Fallback: o índice do field_path, que só existe porque agora é lido."""
    for erro in falha.erros:
        if "headlines[" not in erro.caminho_campo:
            continue
        try:
            miolo = erro.caminho_campo.split("headlines[", 1)[1].split("]", 1)[0]
            return Alvo("headline", int(miolo))
        except (ValueError, IndexError):
            continue
    return None


# ── regeneração de UM asset ─────────────────────────────────────────────────


def _regenerar(
    cliente: Cliente,
    dados: dict,
    alvo: Alvo,
    grupo: list[Achado],
    pedido: Pedido,
    estado: Estado,
    fatos_texto: str,
) -> None:
    if grupo[0].codigo == "C2.falta":
        _preencher_deficit(cliente, dados, alvo, pedido, estado, fatos_texto)
        return

    original = alvo.ler(dados)
    prompt = _prompt_asset(dados, alvo, grupo, pedido, original, fatos_texto)
    try:
        resposta = extract_json(cliente.gerar(SISTEMA_ASSET, prompt))
    except ValueError:
        estado.anotar(f"      ✗ substituto ilegível para {alvo}")
        return
    novo = str(resposta.get("texto", "")).strip()
    if not novo:
        estado.anotar(f"      ✗ substituto vazio para {alvo}")
        return
    alvo.escrever(dados, novo)
    # ⚠️ CONFERE QUE A ESCRITA PEGOU. O alvo pode ter SUMIDO entre achar e
    # consertar: uma correção de excesso encurta a lista, e o índice deste
    # achado passa a apontar para fora. `Alvo.escrever` ignora esse caso de
    # propósito (derrubar a geração inteira por isso já custou uma cascata
    # pagas no card 65) — mas anotar "trocou" quando nada foi trocado seria
    # a pior forma de sucesso: a que não deixa rastro.
    if alvo.ler(dados) != novo:
        estado.anotar(f"      ✗ {alvo} sumiu antes do conserto (lista encurtada)")
        return
    estado.anotar(f"      {original!r} → {novo!r}")
    _atualizar_ancoragem(dados, alvo, novo, resposta)


def _preencher_deficit(
    cliente: Cliente,
    dados: dict,
    alvo: Alvo,
    pedido: Pedido,
    estado: Estado,
    fatos_texto: str,
) -> None:
    """Contagem a menos: gera só o déficit, nunca o conjunto."""
    from .contrato import _PLURAL  # noqa: PLC0415 — detalhe interno do contrato

    chave = _PLURAL.get(alvo.tipo, alvo.tipo)
    atual = dados.get(chave) or []
    faltam = {"headlines": pedido.n_headlines, "descriptions": pedido.n_descriptions,
              "sitelinks": pedido.n_sitelinks,
              "callouts": pedido.n_callouts}[chave] - len(atual)
    orc = orcamento_restante(dados.get("headlines") or [], pedido, vagas=faltam)
    prompt = (
        f"Faltam {faltam} item(ns) em `{chave}`. Gere APENAS os que faltam.\n"
        f"NÃO reescreva os {len(atual)} existentes.\n"
        f"{_texto_orcamento(orc)}\n{fatos_texto}\n"
        f'Responda {{"textos": [{{"texto": "...", "mecanica": "M?", '
        f'"fato": "F? ou -"}}, ...{faltam}]}}.'
    )
    try:
        resposta = extract_json(cliente.gerar(SISTEMA_ASSET, prompt))
    except ValueError:
        estado.anotar(f"      ✗ déficit ilegível para {chave}")
        return

    # O déficit carrega ancoragem como qualquer asset: um título novo com
    # dígito e sem fato cai na checagem 7 na rodada seguinte, e aí a cascata
    # gastaria uma segunda geração para consertar o que a primeira já sabia.
    itens = resposta.get("textos") or []
    novos = [i if isinstance(i, dict) else {"texto": str(i)} for i in itens][:faltam]
    dados[chave] = list(atual) + [str(i.get("texto", "")) for i in novos]
    estado.anotar(f"      +{len(novos)} em {chave} (os {len(atual)} anteriores intactos)")
    anc = (dados.get("ancoragem") or {}).get(chave)
    if isinstance(anc, list):
        for j, item in enumerate(novos, start=len(atual)):
            texto = str(item.get("texto", ""))
            anc.append({"i": j,
                        "mecanica": str(item.get("mecanica", "M1")).upper(),
                        "fato": str(item.get("fato", "-")),
                        "papel": "a página | nomear | informação | FONTE",
                        "chars": comprimento_efetivo(texto)})


def _prompt_asset(
    dados: dict,
    alvo: Alvo,
    grupo: list[Achado],
    pedido: Pedido,
    original: str,
    fatos_texto: str,
) -> str:
    """O prompt menor. Carrega os quatro insumos, e o quarto é o esquecível.

    1. o original          2. a regra que o matou
    3. os fatos            4. **o orçamento de cota que sobrou**

    Sem o (4), o substituto entrega a quinta pergunta num conjunto de teto 3.
    """
    sobreviventes = [h for i, h in enumerate(dados.get("headlines") or [])
                     if not (alvo.tipo == "headline" and i == alvo.indice)]
    orc = orcamento_restante(sobreviventes, pedido, vagas=1)
    motivos = "\n".join(f"  - {a.codigo}: {a.detalhe}" for a in grupo)
    return (
        f"Reescreva UM recurso: {alvo}.\n\n"
        f"ORIGINAL: {original!r}\n\n"
        f"CAIU POR:\n{motivos}\n\n"
        f"C2 — TROCA LATERAL, NÃO DESCENDENTE: o substituto marca pelo menos "
        f"tantos eixos (mecânica, fato, verbo, pergunta, dígito) quanto o "
        f"original. Trocar um título ousado por um vago é perder duas vezes.\n\n"
        f"{_texto_orcamento(orc)}\n"
        f"{fatos_texto}\n"
        f'Responda JSON puro: {{"texto": "...", "mecanica": "M?", "fato": "F? ou -"}}'
    )


def _texto_orcamento(orc: dict[str, tuple[int, int]]) -> str:
    livres = [f"{k} até +{hi}" for k, (lo, hi) in orc.items() if hi > 0]
    presos = [f"{k} JÁ NO TETO" for k, (lo, hi) in orc.items() if hi == 0]
    devidos = [f"{k} FALTAM {lo}" for k, (lo, hi) in orc.items() if lo > 0]
    return (
        "ORÇAMENTO DE COTA RESTANTE (seção 6, contando os sobreviventes):\n"
        f"  ainda cabe:  {', '.join(livres) or '—'}\n"
        f"  esgotado:    {', '.join(presos) or '—'}\n"
        f"  em débito:   {', '.join(devidos) or '—'}"
    )


# ── consistência pós-substituição ───────────────────────────────────────────


def _atualizar_ancoragem(dados: dict, alvo: Alvo, novo: str, resposta: dict) -> None:
    if alvo.tipo != "headline":
        return
    for e in (dados.get("ancoragem") or {}).get("headlines") or []:
        if isinstance(e, dict) and int(e.get("i", -1)) == alvo.indice:
            e["chars"] = comprimento_efetivo(novo)
            if resposta.get("mecanica"):
                e["mecanica"] = str(resposta["mecanica"]).upper()
            if resposta.get("fato"):
                e["fato"] = str(resposta["fato"])


def _reconciliar(dados: dict, pedido: Pedido, estado: Estado) -> None:
    """Recalcula `contagem_final` em CÓDIGO após as trocas.

    A checagem 6 do contrato é detector de mentira e roda sobre o que o MODELO
    declarou. Depois que a cascata substitui em código, a declaração antiga
    deixa de descrever o payload — então ela é recalculada aqui, e o que passa
    a valer é a conferência de FAIXA (`_cotas_fora`), não a de igualdade.
    """
    aud = dados.setdefault("auditoria", {})
    contagem = medir(dados.get("headlines") or [], pedido.idioma)
    anterior = aud.get("contagem_final") or {}
    contagem["mecanicas_distintas"] = len({
        str(e.get("mecanica", "")).upper()
        for e in (dados.get("ancoragem") or {}).get("headlines") or []
        if isinstance(e, dict)
    })
    contagem["max_titulos_por_fato"] = anterior.get("max_titulos_por_fato", 2)
    aud["contagem_final"] = contagem


def _cotas_fora(dados: dict, pedido: Pedido) -> list[str]:
    atual = medir(dados.get("headlines") or [], pedido.idioma)
    fx = faixas(pedido.n_headlines)
    fora = []
    for marcador, (lo, hi) in fx.items():
        v = atual.get(marcador, 0)
        if v < lo or v > hi:
            fora.append(f"{marcador}={v} fora de {lo}–{hi}")
    return fora


def _agrupar(achados: list[Achado]) -> dict[Alvo | None, list[Achado]]:
    fora: dict[Alvo | None, list[Achado]] = {}
    for a in achados:
        fora.setdefault(a.alvo, []).append(a)
    return fora


def _rebruto(dados: dict) -> str:
    import json

    return json.dumps(dados, ensure_ascii=False)
