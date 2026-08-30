"""O juiz de SENTIDO — o que regex não consegue decidir.

## Por que este módulo existe

Em 19/08/2026 o contrato reprovou o card 74 três vezes pela mesma causa, com
três regras diferentes:

    'PagBank ou Ton: Como Escolher?'   → "letras maiúsculas alternadas"
    'Point Pro 3 Mercado Pago'         → "digito_nao_ano" excedente
    'Point Pro 3 Mercado Pago'         → "afirmação concreta sem fato declarado"

Nenhuma das três é verdade. `PagBank` é marca, não grito gráfico. O `3` de
`Point Pro 3` é parte do nome do produto, não um número afirmado. Regex não
distingue nome próprio de alegação porque essa distinção é de SENTIDO, e
sentido não cabe em padrão de caractere.

O custo disso não foi cosmético: a cota `digito_nao_ano ≤ 1 em 15` ficou
**insatisfazível** num nicho onde os produtos se chamam Point Pro 3, T3 Smart e
Minizinha NFC 2. A cascata queimou 142 s tentando obedecer uma regra impossível.

## O que este juiz NÃO faz — e é deliberado

Ele **não conta nada**. Contagem de caractere, número de títulos, cota por
marcador e reconciliação continuam em código, e devem continuar: na mesma
geração em que o modelo errou o sentido, ele também declarou 1 dígito onde havia
3, 5 títulos de leitura onde havia 6, e 1 verbo onde havia 0. Pedir contagem a
um LLM é pedir exatamente aquilo em que ele é pior que `len()`.

A divisão é esta, e ela não é preguiça:

    exato   → código   estrutura, contagem, caracteres, reconciliação
    sentido → LLM      é marca ou grito? é nome ou alegação? o fato sustenta?

## O juiz cita a regra, nunca opina

Toda observação devolvida traz o `id` da regra do `policy/spec.json` que a
sustenta, ou o `id` do fato que faltou. Um juiz que devolve "não gostei" produz
reescrita cega — que é o defeito que este módulo veio consertar, não repetir.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from .contrato import Achado, Classe

# Só as regras de SENTIDO. As de forma (limite de caractere, DKI) ficam em
# código e nem chegam ao prompt — mandá-las convidaria o modelo a contar.
REGRAS_DE_SENTIDO = (
    "editorial.maiusculas.alternada",
    "editorial.maiusculas.tudo_caixa_alta",
    "editorial.repeticao.no_item",
    "editorial.repeticao.na_lista",
)


class Cliente(Protocol):
    def gerar(self, sistema: str, usuario: str) -> str: ...


@dataclass(frozen=True)
class Observacao:
    """Uma observação do juiz, com a regra que a sustenta colada."""

    campo: str            # headline[3] | description[0] | sitelink[1] | ...
    regra: str            # id da regra do spec.json, ou 'ancoragem'
    severidade: str       # erro | aviso
    motivo: str           # uma frase, para humano
    trecho: str           # o texto exato julgado
    conserto: str = ""    # o que fazer — vazio quando não há sugestão óbvia


SISTEMA = """\
Você é o juiz editorial de anúncios do Google Ads desta operação.

Seu trabalho é decidir questões de SENTIDO que nenhum padrão de texto resolve.
Você NÃO conta caracteres, NÃO conta títulos e NÃO verifica limites de tamanho —
isso é medido em código, com exatidão, e você erraria.

As três perguntas que só você responde:

1. NOME PRÓPRIO OU ALEGAÇÃO?
   "Point Pro 3", "T3 Smart", "Minizinha NFC 2", "PagBank", "InfiniteSmart" são
   NOMES DE PRODUTO E MARCA. O número e a maiúscula interna fazem parte do nome.
   Um nome próprio não afirma nada e não precisa de fato que o sustente.
   Já "taxa de 0,58%", "5 anos de garantia", "em 3 dias" são ALEGAÇÕES: números
   que o anúncio afirma sobre o mundo, e que exigem fato declarado.

2. MARCA OU GRITO GRÁFICO?
   A política de maiúsculas mira ênfase artificial — "CoMpRe AgOrA", "OFERTA
   IMPERDÍVEL". Marca escrita como o dono da marca escreve (PagBank, iPhone,
   InfinitePay) é uso legítimo e NÃO viola.

3. O FATO SUSTENTA A ALEGAÇÃO?
   Para cada alegação numérica, existe um fato na lista que a sustente, com o
   mesmo valor e a mesma unidade? Aproximar, arredondar ou trocar a unidade
   NÃO sustenta.

REGRAS DA CASA:
- Cite SEMPRE a regra ou o fato. Observação sem procedência não serve.
- Na dúvida entre marca e grito, é marca. Falso positivo custou 142 s de
  regeneração inútil nesta operação; falso negativo o Google pega e avisa.
- Se estiver tudo certo, devolva lista vazia. Um juiz que sempre acha algo é
  ruído.

Responda APENAS com JSON válido, sem markdown e sem comentário:
{"observacoes": [
  {"campo": "headline[3]", "regra": "<id da regra ou 'ancoragem'>",
   "severidade": "erro|aviso", "motivo": "<uma frase>",
   "trecho": "<o texto julgado>", "conserto": "<o que fazer, ou vazio>"}
]}
"""


def _linhas_do_anuncio(dados: dict) -> list[tuple[str, str]]:
    """Achata o anúncio em (campo, texto). Só o que o operador vê."""
    saida: list[tuple[str, str]] = []
    for chave in ("headlines", "descriptions", "callouts", "long_headlines"):
        for i, item in enumerate(dados.get(chave) or []):
            txt = item.get("texto") if isinstance(item, dict) else item
            if txt:
                saida.append((f"{chave[:-1]}[{i}]", str(txt)))
    for i, s in enumerate(dados.get("sitelinks") or []):
        if isinstance(s, dict):
            for campo in ("texto", "title", "descricao1", "descricao2"):
                if s.get(campo):
                    saida.append((f"sitelink[{i}].{campo}", str(s[campo])))
    snip = dados.get("snippet") or {}
    if isinstance(snip, dict):
        if snip.get("header"):
            saida.append(("snippet.header", str(snip["header"])))
        for i, v in enumerate(snip.get("valores") or snip.get("values") or []):
            saida.append((f"snippet.valor[{i}]", str(v)))
    return saida


def montar_prompt(dados: dict, *, fatos_texto: str, nicho: str,
                  regras: Sequence[dict]) -> str:
    linhas = "\n".join(f"  {campo}: {texto!r}" for campo, texto in _linhas_do_anuncio(dados))
    txt_regras = "\n".join(
        f"  - {r['id']} ({r.get('severidade', 'aviso')}): {r.get('titulo', '')}"
        f"\n      {r.get('nota', '')}".rstrip()
        for r in regras)
    return f"""\
NICHO: {nicho}

O ANÚNCIO:
{linhas}

OS FATOS DECLARADOS (a única base para alegação numérica):
{fatos_texto or '  (nenhum fato declarado)'}

AS REGRAS DE SENTIDO QUE VOCÊ APLICA:
{txt_regras}

Julgue. Lembre: nome de produto não é alegação, e marca não é grito.
"""


def julgar(cliente: Cliente, dados: dict, *, fatos_texto: str, nicho: str,
           regras: Sequence[dict]) -> list[Observacao]:
    """Devolve as observações de sentido. Falha de transporte NÃO derruba a copy.

    ⚠️ Um juiz que explode e leva a geração junto é pior que juiz nenhum: os
    ~140 s de cascata já estão pagos quando ele roda. Erro de rede ou JSON
    ilegível vira lista vazia e o contrato de código continua valendo.
    """
    try:
        bruto = cliente.gerar(SISTEMA, montar_prompt(
            dados, fatos_texto=fatos_texto, nicho=nicho, regras=regras))
        limpo = bruto.strip()
        if limpo.startswith("```"):
            limpo = limpo.split("```")[1]
            limpo = limpo[4:] if limpo.startswith("json") else limpo
        obs = json.loads(limpo).get("observacoes") or []
    except Exception:  # noqa: BLE001 — ver a docstring
        return []

    saida: list[Observacao] = []
    for o in obs:
        if not isinstance(o, dict) or not o.get("campo"):
            continue
        saida.append(Observacao(
            campo=str(o.get("campo", "")),
            regra=str(o.get("regra", "")),
            severidade="erro" if str(o.get("severidade")) == "erro" else "aviso",
            motivo=str(o.get("motivo", ""))[:300],
            trecho=str(o.get("trecho", ""))[:120],
            conserto=str(o.get("conserto", ""))[:200],
        ))
    return saida


def como_achados(obs: Sequence[Observacao]) -> list[Achado]:
    """Traduz para o vocabulário da cascata, para ela regenerar por asset.

    Só `erro` vira Achado acionável — `aviso` fica para a tela. A cascata tem
    teto de 2 regenerações por asset; gastar uma delas com aviso é gastar LLM
    para trocar seis por meia dúzia.
    """
    from .contrato import Alvo

    saida: list[Achado] = []
    for o in obs:
        if o.severidade != "erro":
            continue
        alvo = Alvo.de_texto(o.campo) if hasattr(Alvo, "de_texto") else None
        detalhe = f"{o.motivo} → {o.trecho!r}"
        if o.conserto:
            detalhe += f" · {o.conserto}"
        saida.append(Achado(f"JS.{o.regra or 'sentido'}", Classe.FORMA_REESCREVER,
                            detalhe, alvo))
    return saida
