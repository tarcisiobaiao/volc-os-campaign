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
from typing import Any, Callable, Protocol, Sequence

from .contrato import Achado, Classe

# Só as regras de SENTIDO. As de forma (limite de caractere, DKI) ficam em
# código e nem chegam ao prompt — mandá-las convidaria o modelo a contar.
REGRAS_DE_SENTIDO = (
    "editorial.maiusculas.alternada",
    "editorial.maiusculas.tudo_caixa_alta",
    "editorial.repeticao.no_item",
    "editorial.repeticao.na_lista",
)

# As regras que o juiz pode citar SEM estarem no spec: o lastro (desde 19/08) e
# as perguntas de editor (B6, 30/09/2026). Um `erro` com regra fora disto e fora
# das regras entregues é opinião sem procedência — vira aviso, nunca regenera.
REGRAS_EDITORIAIS = ("ancoragem", "promessa", "destino", "identidade", "qualificador")

# Campo do anúncio (como `_linhas_do_anuncio` o nomeia) → campo do spec (`aplica_a`).
_CAMPO_SPEC = {"headline": "headline", "description": "description",
               "callout": "callout", "long_headline": "long_headline",
               "sitelink": "sitelink", "snippet": "snippet"}


class Cliente(Protocol):
    def gerar(self, sistema: str, usuario: str) -> str: ...


class JuizIndisponivel(RuntimeError):
    """O juiz não julgou: transporte caiu ou a resposta saiu do contrato.

    ⚠️ Até 30/09/2026 isto virava LISTA VAZIA — "nenhuma objeção". Com o juiz
    ligado a C7 e a C8 ficam desligadas, então a queda dele deixava a rodada
    sem checagem de lastro e a copy saía aceita (verificação adversarial V11).
    Agora a falha é dita: `ciclo.gerar` a transforma na pendência
    `JS.indisponivel`, religa a C7 e não aceita a copy.

    `motivo` nunca carrega a mensagem crua do erro de transporte (pode trazer
    URL com chave): só o tipo do erro.
    """

    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


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

4. O TIPO DO FATO PERMITE ESSA ALEGAÇÃO?
   Cada fato chega com o tipo entre colchetes. [contexto] é fato descritivo:
   sustenta relevância e nomeação — o órgão, o programa, a estrutura como
   OBJETO da frase — e NUNCA sustenta número, prazo nem condição, mesmo que o
   número esteja escrito dentro dele. Número pede [numero]; prazo pede [prazo]
   ou [data]; condição de quem tem direito pede [condicao]. Um fato com
   "escopo" vale só nele: regional não vira regra nacional. Alegação apoiada
   no tipo errado é falta de fato (regra 'ancoragem').

5. A PROMESSA SE SUSTENTA NO DESTINO?
   O clique leva ao DESTINO informado. É erro (regra 'promessa') a promessa que
   nenhum fato sustenta — garantia, aprovação, vaga, acesso, resultado —, com
   ou sem palavra de lista: "Vaga Assegurada" não usa palavra proibida nenhuma
   e promete. É erro (regra 'destino') o rótulo ou CTA que promete o que o
   destino não entrega: "Ver vagas abertas" quando a página só explica como
   consultar no portal oficial. CTA bom nomeia o avanço que o leitor quer
   ("ver", "descobrir se tenho direito", "encontrar a turma") e o destino
   entrega exatamente isso. Os TERMOS DE BUSCA dizem o que o leitor quer; se
   vierem NÃO COLETADOS, não presuma a busca.
   Identidade (regra 'identidade'): só quando o texto faz o leitor supor que o
   anunciante É o órgão, o banco ou o programa, ou fala por ele. Não exija
   aviso de independência em todo recurso.
   Qualificador material (regra 'qualificador'): o fato tem escopo, condição
   ou teto e o texto o omite a ponto de mudar a promessa ("gratuito" quando o
   fato diz "gratuito para renda até 2 salários").

6. PALAVRA MARCADA NÃO É VIOLAÇÃO.
   Os TRECHOS MARCADOS vêm de listas de palavras e NÃO reprovam sozinhos. "O
   acesso não é garantido a todos" usa "garantido" para NEGAR a promessa;
   "Procura" contém "cura". É erro só se, no contexto, a promessa for falsa,
   sem lastro, ou o site falar como quem presta o serviço.

VOCÊ É EDITOR, NÃO NEUTRALIZADOR:
- Preserve o ângulo, o benefício e a voz. Texto correto e genérico não é erro.
- `conserto` é o menor ajuste que resolve o erro, com a evidência (fato,
  destino ou regra). Nunca reescreva o recurso inteiro nem troque o ângulo.
- Estilo, gosto ou "poderia ser mais forte" é 'aviso', nunca 'erro'. Aviso não
  é aplicado automaticamente.

REGRAS DA CASA:
- Cite SEMPRE a regra ou o fato. Observação sem procedência não serve.
- Na dúvida entre marca e grito, é marca. Falso positivo custou 142 s de
  regeneração inútil nesta operação; falso negativo o Google pega e avisa.
- Se estiver tudo certo, devolva lista vazia. Um juiz que sempre acha algo é
  ruído.

Responda APENAS com JSON válido, sem markdown e sem comentário:
{"observacoes": [
  {"campo": "headline[3]", "regra": "<id da regra listada, ou ancoragem | promessa | destino | identidade | qualificador>",
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
            # `description1/2` é o nome que o PROMPT.md manda o modelo usar; só
            # `descricao1/2` era lido, e a descrição do sitelink nunca chegava
            # ao juiz.
            for campo in ("texto", "title", "descricao1", "descricao2",
                          "description1", "description2"):
                if s.get(campo):
                    saida.append((f"sitelink[{i}].{campo}", str(s[campo])))
    snip = dados.get("snippet") or {}
    if isinstance(snip, dict):
        if snip.get("header"):
            saida.append(("snippet.header", str(snip["header"])))
        for i, v in enumerate(snip.get("valores") or snip.get("values") or []):
            saida.append((f"snippet.valor[{i}]", str(v)))
    return saida


def localizar(dados: dict, *, pais: str = "BR", idioma: str = "pt",
              vertical: str = "informativo", spec: dict | None = None) -> list[str]:
    """Os trechos que uma regra `localizador` do spec marcou — para o juiz ler.

    A lista de palavras não reprova (inventário da frente A, ADS-07/08/09/15):
    ela APONTA. Cada linha diz o campo, a regra e o texto, e o juiz decide pelo
    sentido. Sem marca, lista vazia — e isso não quer dizer "texto limpo".
    """
    from ..policy.spec import Validador  # noqa: PLC0415 — carrega o spec.json

    v = Validador(spec, pais=pais, vertical=vertical, idioma=idioma)
    ids = {r["id"] for r in v._regras() if r.get("localizador")}
    if not ids:
        return []
    marcas: list[str] = []
    for campo, texto in _linhas_do_anuncio(dados):
        base = campo.split("[", 1)[0].split(".", 1)[0]
        campo_spec = _CAMPO_SPEC.get(base)
        if not campo_spec:
            continue
        for viol in v.checar_texto(texto, campo_spec):
            if viol.regra in ids:
                marcas.append(f"  {campo}: {viol.regra} → {texto!r}")
    return marcas


def regras_do_juiz(*, idioma: str = "pt", vertical: str = "informativo",
                   spec: dict | None = None) -> list[dict]:
    """As regras de sentido de forma + as regras `localizador` do idioma."""
    from ..policy import spec as _spec  # noqa: PLC0415

    sp = spec or _spec.carregar()
    regras = [r for r in (sp.get("estruturais") or [])
              if r.get("id") in REGRAS_DE_SENTIDO]
    vistos = {r["id"] for r in regras}
    for r in (sp.get("semanticas") or {}).get(idioma, []):
        if not r.get("localizador") or r["id"] in vistos:
            continue
        if r.get("verticais") and vertical not in r["verticais"]:
            continue
        regras.append(r)
        vistos.add(r["id"])
    return regras


def bloco_promessa_da_lp(promessa: Any) -> str:
    """A promessa da LP (`pautador_ponte._promessa_da_lp`) como texto do prompt.

    `presente` → título, subtítulo e CTAs, com a fonte. `ausente` → a ausência
    COM o motivo: o juiz sabe que não recebeu e não presume o que a LP diz.
    `None` (quem chamou não trouxe) → vazio, e o prompt diz "não entregue".
    """
    if not isinstance(promessa, dict):
        return ""
    if promessa.get("estado") != "presente":
        motivo = str(promessa.get("motivo_ausencia") or "sem motivo informado")
        return f"  AUSENTE ({motivo}): não presuma o que a página diz."
    linhas = []
    if promessa.get("titulo"):
        linhas.append(f"  título: {promessa['titulo']!r}")
    if promessa.get("subtitulo"):
        linhas.append(f"  subtítulo: {promessa['subtitulo']!r}")
    for i, cta in enumerate(promessa.get("ctas") or [], 1):
        linhas.append(f"  CTA[{i}]: {cta!r}")
    if promessa.get("fonte"):
        linhas.append(f"  (fonte: {promessa['fonte']})")
    return "\n".join(linhas)


def montar_juiz(cliente: Cliente, *, fatos_texto: str, nicho: str,
                termos_texto: str = "", destino: str = "", promessa_lp: str = "",
                pais: str = "BR", idioma: str = "pt", vertical: str = "informativo",
                spec: dict | None = None) -> Callable[[dict], list[Achado]]:
    """O juiz de sentido pronto para a cascata: dados → achados acionáveis.

    Recebe o que um editor precisa e o juiz não recebia até 30/09/2026: os
    termos de busca com o estado da coleta, o destino do clique, a PROMESSA da
    página de destino (título, subtítulo e CTA da LP; S2 · item 4) e os trechos
    que as listas de palavras marcaram. Os fatos já chegavam tipados (B3b).
    Só `erro` com procedência (regra entregue ou editorial) vira achado.
    """
    regras = regras_do_juiz(idioma=idioma, vertical=vertical, spec=spec)
    validas = {r["id"] for r in regras} | set(REGRAS_EDITORIAIS)

    def _juiz(dados: dict) -> list[Achado]:
        marcas = localizar(dados, pais=pais, idioma=idioma, vertical=vertical, spec=spec)
        return como_achados(julgar(
            cliente, dados, fatos_texto=fatos_texto, nicho=nicho, regras=regras,
            termos_texto=termos_texto, destino=destino, promessa_lp=promessa_lp,
            localizadores=marcas),
            regras_validas=validas)

    return _juiz


def montar_prompt(dados: dict, *, fatos_texto: str, nicho: str,
                  regras: Sequence[dict], termos_texto: str = "",
                  destino: str = "", localizadores: Sequence[str] = (),
                  promessa_lp: str = "") -> str:
    linhas = "\n".join(f"  {campo}: {texto!r}" for campo, texto in _linhas_do_anuncio(dados))
    txt_regras = "\n".join(
        f"  - {r['id']} ({r.get('severidade', 'aviso')}): {r.get('titulo', '')}"
        f"\n      {r.get('nota', '')}".rstrip()
        for r in regras)
    return f"""\
NICHO: {nicho}

O ANÚNCIO:
{linhas}

OS FATOS DECLARADOS, com o tipo entre colchetes (a única base para alegação
numérica — e [contexto] não é base para número, prazo nem condição):
{fatos_texto or '  (nenhum fato declarado)'}

O QUE O LEITOR BUSCOU (termos de busca, com o estado da coleta):
{termos_texto or '  NÃO INFORMADO a este juiz — não presuma a busca.'}

O DESTINO (para onde o clique leva):
{destino or '  NÃO INFORMADO a este juiz — não julgue congruência com o destino.'}

A PROMESSA DA PÁGINA DE DESTINO (o que o leitor encontra ao clicar; o anúncio
e o rótulo não prometem o que ela não entrega):
{promessa_lp or '  NÃO ENTREGUE a este juiz: julgue o que o anúncio promete pelos fatos, e o rótulo pelo que a URL e os fatos dizem.'}

TRECHOS MARCADOS POR LOCALIZADOR (listas de palavras — não reprovam sozinhos;
decida pela promessa no contexto e diante do destino):
{chr(10).join(localizadores) or '  (nenhum)'}

AS REGRAS DE SENTIDO QUE VOCÊ APLICA:
{txt_regras}

Julgue. Lembre: nome de produto não é alegação, marca não é grito, e palavra
marcada não é violação.
"""


def julgar(cliente: Cliente, dados: dict, *, fatos_texto: str, nicho: str,
           regras: Sequence[dict], termos_texto: str = "", destino: str = "",
           localizadores: Sequence[str] = (), promessa_lp: str = "") -> list[Observacao]:
    """Devolve as observações de sentido; lista vazia = julgou e não objetou.

    ⚠️ Um juiz que explode e leva a geração junto é pior que juiz nenhum: os
    ~140 s de cascata já estão pagos quando ele roda. Por isso a falha NÃO é
    uma exceção qualquer: é `JuizIndisponivel`, com o motivo, que a cascata
    converte em pendência explícita. Nunca lista vazia calada — ver a classe.
    """
    try:
        bruto = cliente.gerar(SISTEMA, montar_prompt(
            dados, fatos_texto=fatos_texto, nicho=nicho, regras=regras,
            termos_texto=termos_texto, destino=destino, localizadores=localizadores,
            promessa_lp=promessa_lp))
    except Exception as exc:  # noqa: BLE001 — ver a docstring
        raise JuizIndisponivel(
            f"falha na chamada ao juiz ({type(exc).__name__})") from None
    try:
        limpo = str(bruto or "").strip()
        if limpo.startswith("```"):
            limpo = limpo.split("```")[1]
            limpo = limpo[4:] if limpo.startswith("json") else limpo
        resposta = json.loads(limpo)
    except (ValueError, IndexError):
        raise JuizIndisponivel("resposta ilegível do juiz (JSON inválido)") from None
    obs = resposta.get("observacoes") if isinstance(resposta, dict) else None
    if not isinstance(obs, list):
        raise JuizIndisponivel(
            "resposta do juiz fora do contrato (sem a lista `observacoes`)")

    saida: list[Observacao] = []
    for o in obs:
        if not isinstance(o, dict) or not o.get("campo"):
            continue
        saida.append(Observacao(
            campo=str(o.get("campo", "")),
            regra=str(o.get("regra", "")),
            # B8/R2: "Erro", " erro ", "bloqueante" são erro; o resto é aviso
            severidade=("erro" if str(o.get("severidade") or "").strip().lower()
                        in ("erro", "bloqueante") else "aviso"),
            motivo=str(o.get("motivo", ""))[:300],
            trecho=str(o.get("trecho", ""))[:120],
            conserto=str(o.get("conserto", ""))[:200],
        ))
    return saida


_REGRAS_SO_ESTILO = frozenset({"estilo", "oportunidade"})


def como_achados(obs: Sequence[Observacao], *,
                 regras_validas: set[str] | None = None) -> list[Achado]:
    """Traduz para o vocabulário da cascata, para ela regenerar por asset.

    Só `erro` vira Achado acionável — `aviso` fica para a tela. A cascata tem
    teto de 2 regenerações por asset; gastar uma delas com aviso é gastar LLM
    para trocar seis por meia dúzia.

    Com `regras_validas`, um `erro` de ESTILO (ou oportunidade) é opinião sem
    procedência e NÃO regenera: sugestão de estilo nunca é aplicada
    automaticamente (contrato entre as trilhas, decisão 7). Qualquer outro
    rótulo fora do conjunto ("Promessa", "JS.promessa", "") NÃO some (B8/R2):
    casa com a regra entregue quando a grafia difere, ou vira `JS.sentido`.
    """
    from .contrato import Alvo

    saida: list[Achado] = []
    for o in obs:
        if o.severidade != "erro":
            continue
        regra = o.regra
        if regras_validas is not None and regra not in regras_validas:
            canon = regra.strip().lower()
            canon = canon[3:] if canon.startswith("js.") else canon
            if canon in _REGRAS_SO_ESTILO:
                continue
            regra = next((r for r in regras_validas if r.lower() == canon), "sentido")
        alvo = Alvo.de_texto(o.campo) if hasattr(Alvo, "de_texto") else None
        detalhe = f"{o.motivo} → {o.trecho!r}"
        if o.conserto:
            detalhe += f" · {o.conserto}"
        saida.append(Achado(f"JS.{regra or 'sentido'}", Classe.FORMA_REESCREVER,
                            detalhe, alvo))
    return saida
