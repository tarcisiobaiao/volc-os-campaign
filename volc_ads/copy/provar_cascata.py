"""Banco de provas da CASCATA. Zero rede, zero custo, zero conta tocada.

Um caso por gatilho, cada um encenado com um roteiro determinístico. O que
cada caso tem de provar:

  · o remédio aplicado foi o MAIS BARATO que resolve aquele defeito;
  · nenhum caminho regenerou o conjunto inteiro por preguiça — só a ancoragem
    mentindo faz isso, e por decisão declarada (C4), com teto;
  · a parada dura funciona: a mesma regra falhando duas vezes no mesmo asset
    encerra aquele asset em vez de gastar a terceira tentativa.

Uso:
    .venv/bin/python -m volc_ads.copy.provar_cascata
"""

from __future__ import annotations

import copy as _copy
import json

from .ciclo import gerar
from .contrato import Pedido
from .mock import ClienteMock, JuizMock, copy_valida, falha_politica

PEDIDO = Pedido(
    n_headlines=15, n_descriptions=4, n_sitelinks=4, n_callouts=4, n_snippet=4,
    idioma="pt", fatos=("F1", "F2", "F3", "F4", "F5"),
    headers_snippet=("Tipos",), max_dki=1,
)

PROMPT = "<PROMPT.md renderizado — render.py entra no item 3>"
FATOS = "FATOS: F1 prazo · F2 tabela · F3 regra · F4 lei · F5 carência"


def _base() -> dict:
    return _copy.deepcopy(copy_valida())


# ── os oito casos ───────────────────────────────────────────────────────────


def caso_json_ilegivel():
    """`]` a mais — o defeito real que descartou 19k tokens do Gemini."""
    d = _base()
    bruto = json.dumps(d, ensure_ascii=False)[:-1] + "]}"
    return ClienteMock([bruto]), JuizMock(), "JSON ilegível"


def caso_forma_saneavel():
    """Espaço duplo e emoji: `re.sub` resolve. Toda geração poupada é dinheiro."""
    d = _base()
    d["headlines"][3] = "Tabela  Oficial por Faixa"   # espaço duplo
    d["callouts"][0] = "Conteúdo informativo ✅"        # emoji
    # `chars` declara o texto JÁ SANEADO: sanear roda antes de checar, e é o
    # texto que vai para o Google que a ancoragem descreve.
    return ClienteMock([d]), JuizMock(), "FORMA saneável"


def caso_contagem_excesso():
    """17 títulos onde cabem 15: corta pelo fim, sem consultar modelo."""
    d = _base()
    d["headlines"] += ["Título Extra Um", "Título Extra Dois"]
    d["ancoragem"]["headlines"] += [
        {"i": 15, "mecanica": "M1", "fato": "-", "chars": 15},
        {"i": 16, "mecanica": "M1", "fato": "-", "chars": 17},
    ]
    return ClienteMock([d]), JuizMock(), "contagem a MAIS"


def caso_contagem_falta():
    """13 títulos: gera só os 2 que faltam, sem tocar nos 13 que existem."""
    d = _base()
    d["headlines"] = d["headlines"][:13]
    d["ancoragem"]["headlines"] = d["ancoragem"]["headlines"][:13]
    _sincronizar(d, 0)
    cliente = ClienteMock([d, {"textos": [
        {"texto": "Multa Rescisória em 2026", "mecanica": "M5", "fato": "F1"},
        {"texto": "Vale a Pena Aderir?", "mecanica": "M8", "fato": "-"},
    ]}])
    return cliente, JuizMock(), "contagem a MENOS"


def caso_forma_reescrever():
    """Estouro de caractere: cortar mudaria o sentido que a passada 2 auditou."""
    d = _base()
    d["headlines"][2] = "Quem Tem Direito ao Saque Este Ano Todo?"
    _sincronizar(d, 2)
    cliente = ClienteMock([d, {"texto": "Quem Tem Direito Este Ano?",
                               "mecanica": "M8", "fato": "-"}])
    return cliente, JuizMock(), "FORMA não-saneável"


def caso_ancoragem_isolada():
    """UMA mentira: declara M8 numa string sem `?`.

    Abaixo do limiar do C4 (um terço). Prova que um deslize isolado NÃO
    derruba os catorze títulos bons — regenera só o título que mentiu.
    """
    d = _base()
    d["ancoragem"]["headlines"][3]["mecanica"] = "M8"   # 'Tabela Oficial por Faixa'
    cliente = ClienteMock([d, {"texto": "Qual É a Sua Faixa?",
                               "mecanica": "M8", "fato": "-"}])
    return cliente, JuizMock(), "ancoragem: 1 mentira"


def caso_ancoragem_conjunto():
    """`contagem_final` divergente: mentira sem alvo, invalida a auditoria toda.

    Não existe "o asset que mentiu" — a declaração é do conjunto. Aqui, e só
    aqui por defeito de ancoragem, o C4 refaz a passada 1.
    """
    d = _base()
    d["auditoria"]["contagem_final"]["pergunta"] = 9    # medido: 2
    cliente = ClienteMock([d, _base()])                  # a 2ª vem honesta
    return cliente, JuizMock(), "ancoragem: conjunto"


def caso_politica():
    """A API nomeia o texto violador. Sem isso, o remédio seria refazer tudo."""
    d = _base()
    d["headlines"][6] = "Antecipe Seu FGTS Hoje"
    d["ancoragem"]["headlines"][6]["mecanica"] = "M1"
    _sincronizar(d, 6)
    cliente = ClienteMock([d, {"texto": "As Regras da Lei do Fundo",
                               "mecanica": "M1", "fato": "-"}])
    juiz = JuizMock([falha_politica("Antecipe Seu FGTS Hoje"), None])
    return cliente, juiz, "TERMINAL de política"


def caso_regra_repetida():
    """O substituto estoura de novo, pela MESMA regra. Encerra aquele asset."""
    d = _base()
    d["headlines"][2] = "Quem Tem Direito ao Saque Este Ano Todo?"
    _sincronizar(d, 2)
    cliente = ClienteMock([
        d,
        {"texto": "Quem Tem Direito ao Saque Neste Ano Inteiro?"},  # estoura igual
    ])
    return cliente, JuizMock(), "parada em REGRA REPETIDA"


def _sincronizar(d: dict, i: int) -> None:
    """Deixa `ancoragem` e `auditoria` COERENTES com o título trocado.

    Sem isto, trocar um título por um mais longo produziria também uma mentira
    de `chars` — e o caso testaria dois gatilhos ao mesmo tempo, sem dizer
    qual dos dois a cascata atendeu.
    """
    from .contrato import comprimento_efetivo, medir

    d["ancoragem"]["headlines"][i]["chars"] = comprimento_efetivo(d["headlines"][i])
    c = medir(d["headlines"])
    c["mecanicas_distintas"] = len({e["mecanica"]
                                    for e in d["ancoragem"]["headlines"]})
    c["max_titulos_por_fato"] = 2
    d["auditoria"]["contagem_final"] = c


CASOS = [caso_json_ilegivel, caso_forma_saneavel, caso_contagem_excesso,
         caso_contagem_falta, caso_forma_reescrever, caso_ancoragem_isolada,
         caso_ancoragem_conjunto, caso_politica, caso_regra_repetida]


def main() -> int:
    linhas = []
    print("═" * 78)
    print("CASCATA CONTRA O MOCK — um caso por gatilho. Nenhuma chamada de rede.")
    print("═" * 78)

    for fabrica in CASOS:
        cliente, juiz, nome = fabrica()
        r = gerar(cliente=cliente, juiz=juiz, pedido=PEDIDO,
                  prompt_usuario=PROMPT, fatos_texto=FATOS)
        print(f"\n┌─ {nome}")
        for linha in r.estado.diario:
            print(f"│ {linha}")
        print(f"└─ {'ACEITO' if r.ok else 'PARCIAL'} · "
              f"conjunto={r.geracoes_conjunto} asset={r.geracoes_asset} · "
              f"chamadas ao modelo={cliente.n_chamadas}")
        for chave, motivo in r.estado.abandonados.items():
            print(f"   ⊘ {chave}: {motivo}")
        for a in r.pendentes:
            print(f"   pendente: {a}")
        linhas.append((nome, r))

    print("\n" + "═" * 78)
    print(f"{'gatilho':<26}{'veredito':<10}{'conjunto':>9}{'asset':>7}{'sem LLM':>9}")
    print("─" * 78)
    for nome, r in linhas:
        sem_llm = len(r.estado.saneamentos) + len(r.estado.cortes)
        print(f"{nome:<26}{'ACEITO' if r.ok else 'PARCIAL':<10}"
              f"{r.geracoes_conjunto:>9}{r.geracoes_asset:>7}{sem_llm:>9}")
    print("─" * 78)

    refeitos = [n for n, r in linhas if r.geracoes_conjunto > 1]
    print(f"regeneraram o CONJUNTO: {refeitos or 'nenhum'}")
    print("  (só a mentira SEM ALVO, ou acima do limiar de um terço, pode — C4)")
    ok = refeitos == ["ancoragem: conjunto"]
    print(f"nenhuma regeneração de conjunto por preguiça: {'SIM' if ok else 'NÃO'}")
    print("═" * 78)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
