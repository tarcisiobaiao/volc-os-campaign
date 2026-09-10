#!/usr/bin/env python3
"""COSTURA — o solver de composição vertical. Aritmética pura, sem navegador.

Recebe a tabela de medidas (medida.py), a declaração de composição do spec e os
tokens da pele; devolve a posição de cada bloco. Não mede nada: quem mede é o
instrumento, e quem julga são os portões. Por isso este módulo roda em
milissegundos sobre uma fixture JSON — é o primeiro teste do parque que não
precisa de Chromium.

O QUE O SPEC DEIXA DE DIZER: `pos.y` de bloco gerido, e o `h` do gráfico.
O QUE O SPEC PASSA A DIZER: a PILHA (ordem) e o LAÇO entre vizinhos.

O vocabulário de laços é do MOTOR, não da marca — são razões geométricas, e uma
pele que pudesse editá-las poderia afrouxar a lei declarando `mesma_unidade`
onde a peça precisa de `articulacao`. A única alavanca da marca é o
`escada_offset`, que desloca a escada inteira preservando TODAS as razões: é
invariante de escala, logo nenhum portão muda de valor.

FOLGA. Com as costuras no alvo, quase sempre sobra campo. A sobra vai INTEIRA
para UMA costura declarada, que deve ser adjacente a um trilho. Nunca rateada:
ratear produz razões novas em todas as juntas ao mesmo tempo, e o resultado é o
espaçamento uniforme que denuncia layout automático. Se ninguém declarou destino
para a sobra, o motor NÃO inventa silêncio — reprova.
"""
from __future__ import annotations

# k_min = o mínimo que ainda significa aquele laço; k_alvo = o que a lei pede.
# Escada {0.5, 1, 2, 3}: cada degrau é razão >= 1.5 do anterior, que é o limite
# abaixo do qual a leitura deixa de distinguir dois níveis de proximidade.
LACOS = {
    "mesma_unidade": {"k_min": 0.5, "k_alvo": 0.5},   # o bloco e sua própria legenda
    "relacionado":   {"k_min": 0.5, "k_alvo": 1.0},   # dois blocos do mesmo assunto
    "separado":      {"k_min": 1.0, "k_alvo": 2.0},   # mudança de assunto
    "articulacao":   {"k_min": 2.0, "k_alvo": 3.0},   # a maior quebra da página
}
ESCADA_DIVISORES = (2, 3, 4)      # M candidato = L/d, na ordem: o maior primeiro


class Reprova(Exception):
    """Fail-closed: o solver não devolve composição ruim, ele não devolve nada."""


def _k(laco: str, offset: int = 0) -> tuple[float, float]:
    if laco not in LACOS:
        raise Reprova(f"laço desconhecido: {laco!r} (vocabulário: {sorted(LACOS)})")
    v = LACOS[laco]
    if not offset:
        return v["k_min"], v["k_alvo"]
    # offset desloca a escada {0.5,1,2,3} → {1,2,3,6} preservando as razões
    mapa = {0.5: 1.0, 1.0: 2.0, 2.0: 3.0, 3.0: 6.0}
    return mapa[v["k_min"]], mapa[v["k_alvo"]]


def _costuras(decl: dict) -> list[tuple[str, str, str]]:
    """A sequência de costuras: trilho de topo → pilha → trilho de base."""
    campo = decl["campo"]
    ordem = [campo["rail_topo"]] + [b["ref"] for b in decl["pilha"]] + [campo["rail_base"]]
    declarados = {(v["entre"][0], v["entre"][1]): v["laco"] for v in decl["vinculos"]}
    fora = []
    for a, b in zip(ordem, ordem[1:]):
        laco = declarados.get((a, b))
        if laco is None:
            raise Reprova(f"costura {a}→{b} sem laço declarado")
        fora.append((a, b, laco))
    if len(declarados) != len(fora):
        extra = set(declarados) - {(a, b) for a, b, _ in fora}
        raise Reprova(f"laço declarado para par que não é costura: {sorted(extra)}")
    return fora


def _modulo(laminas: list[dict]) -> tuple[float, str]:
    """M vem da entrelinha MEDIDA, e é da CLASSE — não da lâmina. Um carrossel
    cujo módulo muda de lâmina para lâmina não rima, e rima é o ponto."""
    Ls = [l["L"] for l in laminas if l.get("L")]
    if not Ls:
        raise Reprova("classe sem entrelinha medida: impossível derivar módulo")
    L = sorted(Ls)[len(Ls) // 2]
    for d in ESCADA_DIVISORES:
        M = L / d
        # o candidato sobrevive se TODA lâmina da classe quantiza nele dentro de
        # meio-passo; senão as lâminas não compartilham ritmo e o M seria ficção
        if all(abs(li - L) <= M / 2 for li in Ls):
            return M, f"L/{d} (L={L:.2f} mediana de {len(Ls)})"
    raise Reprova(f"classe_sem_modulo: entrelinhas medidas {[round(x,2) for x in Ls]} "
                  f"não compartilham ritmo em nenhum divisor {ESCADA_DIVISORES}")


def resolve_lamina(lam: dict, M: float, offset: int = 0) -> dict:
    decl, bl = lam["decl"], lam["blocos"]
    costuras = _costuras(decl)
    flex_id = next((b["ref"] for b in decl["pilha"] if b.get("flex")), None)

    def alt(bid):
        b = bl[bid]
        return b["ink_base"] - b["ink_topo"]

    campo_topo = bl[decl["campo"]["rail_topo"]]["ink_base"]
    campo_base = bl[decl["campo"]["rail_base"]]["ink_topo"]
    H = campo_base - campo_topo

    pilha = [b["ref"] for b in decl["pilha"]]
    rigido = sum(alt(b) for b in pilha if b != flex_id)
    soma_alvo = sum(_k(l, offset)[1] for _, _, l in costuras) * M
    soma_min = sum(_k(l, offset)[0] for _, _, l in costuras) * M

    faixa = lam.get("faixa_forma", {}).get(flex_id) if flex_id else None
    span_min, span_max = (faixa if faixa else (alt(flex_id), alt(flex_id))) if flex_id else (0, 0)

    if rigido + soma_min + span_min > H:
        raise Reprova(
            f"nao_cabe: falta {rigido + soma_min + span_min - H:.1f}px "
            f"({(rigido + soma_min + span_min - H)/M:.2f} módulos) no campo de "
            f"{lam['id']!r} — alívio R1..R4 é decisão de LOTE, não de lâmina")

    # o campo disponível já precisa descontar o MÍNIMO do flexível; sem isso o
    # span_min entra duas vezes na conta e a atribuição não fecha (o resíduo sai
    # exatamente igual ao span_min, que é a assinatura desta classe de erro)
    residual = H - rigido - soma_alvo - span_min
    span = span_min
    if flex_id:
        # ATÉ o alvo, folga vira vão; DEPOIS do alvo, folga vira tamanho. Acima do
        # alvo a proximidade já saturou: vão adicional não compra agrupamento
        # nenhum, enquanto tamanho ainda compra legibilidade do argumento.
        span = max(span_min, min(span_max, span_min + max(0.0, residual)))
        residual -= (span - span_min)

    sobra = residual
    borda = decl.get("folga_de_borda")
    if sobra > 0.5:
        if not borda:
            raise Reprova(f"sobra_sem_destino: {sobra:.1f}px ({sobra/M:.2f} módulos) "
                          f"em {lam['id']!r} — declare `folga_de_borda`")
        if borda not in ("topo", "base"):
            raise Reprova(f"folga_de_borda inválida: {borda!r} (topo|base)")

    i_folga = 0 if borda == "topo" else len(costuras) - 1
    vaos, saida = [], []
    for i, (a, b, laco) in enumerate(costuras):
        k = _k(laco, offset)[1]
        # a sobra é atribuída SEMPRE, por menor que seja: o limiar de 0.5px
        # servia para exigir a declaração de destino, não para descartar px.
        # Descartada, ela reaparecia como resíduo e derrubava a conservação —
        # e o resíduo do radar era exatamente o erro de 0.18px da bissecção.
        px = k * M + (sobra if i == i_folga else 0.0)
        vaos.append(px)
        saida.append({"id": f"{a}>{b}", "laco": laco, "k": k, "optico": round(px, 2),
                      "borda": i in (0, len(costuras) - 1),
                      "carrega_folga": i == i_folga and sobra > 0.5})

    # tinta → caixa: o CSS posiciona a caixa, e a excursão medida é a ponte
    y, pos = campo_topo, {}
    for i, bid in enumerate(pilha):
        y += vaos[i]
        h = span if bid == flex_id else alt(bid)
        pos[bid] = {"ink_topo": round(y, 2), "ink_base": round(y + h, 2),
                    "caixa_y": round(y - (bl[bid].get("exc_topo") or 0), 2)}
        if bid == flex_id:
            # O SOLVER DECIDE O SPAN, NUNCA A ALTURA. Converter span→h somando a
            # excursão só é exato quando dspan/dh vale 1 — medido, a excursão do
            # radar espalha 72px ao longo da faixa (109 em h=260, 37 em h=620).
            # Quem resolve a altura é elastico.resolve_h, por bissecção sobre
            # medida real. Publicar `param_flex` aqui reintroduziria a inversão
            # de reta que o COSTURA proíbe.
            pos[bid]["span_alvo"] = round(span, 2)
        y += h

    fecha = abs((campo_base - y) - vaos[-1])
    if fecha > 0.02:
        raise Reprova(f"atribuição não fecha em {lam['id']!r}: resíduo {fecha:.3f}px")

    return {"slide": lam["id"], "modulo_px": round(M, 2), "campo": [campo_topo, campo_base],
            "costuras": saida, "posicoes": pos,
            "flex": ({"id": flex_id, "span": round(span, 2),
                      "faixa_forma": [round(span_min, 2), round(span_max, 2)],
                      "saturado": abs(span - span_max) < 0.5} if flex_id else None),
            "sobra_px": round(sobra, 2), "sobra_M": round(sobra / M, 2),
            "atribuicao_fecha_px": round(fecha, 3)}


def resolve_classe(laminas: list[dict], tokens: dict | None = None) -> dict:
    """Resolve o LOTE inteiro. M é único para a classe, então nenhuma lâmina pode
    ser resolvida antes de todas serem medidas."""
    off = int(((tokens or {}).get("composicao") or {}).get("escada_offset", 0))
    if off not in (0, 1):
        raise Reprova(f"escada_offset deve ser 0 ou 1, veio {off!r}")
    M, origem = _modulo(laminas)
    fora = [resolve_lamina(l, M, off) for l in laminas]
    por_costura = {}
    for r in fora:
        for c in r["costuras"]:
            por_costura.setdefault(c["id"], []).append(c["optico"])
    identicas = {k: (max(v) - min(v)) for k, v in por_costura.items() if len(v) > 1}
    return {"modulo_px": round(M, 2), "modulo_origem": origem, "escada_offset": off,
            "laminas": fora,
            "lote": {"amplitude_por_costura_px": {k: round(v, 2) for k, v in identicas.items()},
                     "costuras_identicas": all(v <= 0.02 for v in identicas.values()),
                     "amplitude_folga_M": round(
                         max(r["sobra_M"] for r in fora) - min(r["sobra_M"] for r in fora), 2)}}
