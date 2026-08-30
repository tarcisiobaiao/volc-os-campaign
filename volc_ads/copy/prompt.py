"""Gerador do prompt dos agentes de copy — derivado do spec de políticas.

A ideia central: **o prompt e o validador são duas metades do mesmo contrato**,
e ambos nascem do `policy/spec.json`. Se uma regra muda no spec, o prompt muda
junto. Prompt escrito à mão e validador escrito à mão divergem em semanas —
foi assim que a lista do n8n virou folclore.

O prompt não pede "seja criativo dentro da política". Ele entrega as restrições
como **gramática** e libera o modelo para ser afiado dentro dela. Restrição
explícita produz copy melhor que restrição vaga, porque o modelo para de gastar
capacidade adivinhando o limite.
"""

from __future__ import annotations

from ..policy.spec import IDIOMA_PADRAO, Validador, carregar

# Mecânica de CTR, destilada do prompt "Sniper" que já rodava no n8n e do
# comportamento medido: 9,71% de CTR no Search contra ~5% nos demais canais
# vem de intenção qualificada, não de sensacionalismo.
BALDES = {
    "pt": [
        ("DKI", "Insere a busca do usuário no título. Máxima relevância percebida.",
         ["{KeyWord:FALLBACK}", "Consulte {KeyWord:FALLBACK}", "{KeyWord:FALLBACK} 2026"]),
        ("DÚVIDA LEGÍTIMA", "Pergunta que o leitor realmente tem. Curiosidade honesta, não isca.",
         ["Você Tem Direito Este Ano?", "Quem Fica De Fora Da Lista?", "O Que Mudou Nas Regras?"]),
        ("PRAZO E MUDANÇA", "Urgência ancorada em fato verificável, nunca inventada.",
         ["Até Quando Pode Solicitar?", "Prazo Pode Expirar Em Breve", "Novas Regras Deste Ano"]),
        ("CTA INFORMATIVO", "Promete informação — que é o que a página entrega de fato.",
         ["Veja Como Consultar", "Guia Gratuito Aqui", "Evite Erros Na Consulta"]),
    ],
    "es": [
        ("DKI", "Inserta la búsqueda del usuario en el título.",
         ["{KeyWord:FALLBACK}", "Consulta {KeyWord:FALLBACK}", "{KeyWord:FALLBACK} 2026"]),
        ("DUDA LEGÍTIMA", "Pregunta que el lector realmente tiene.",
         ["¿Tienes Derecho Este Año?", "¿Quién Queda Fuera?", "¿Qué Cambió En Las Reglas?"]),
        ("PLAZO Y CAMBIO", "Urgencia anclada en un hecho verificable.",
         ["¿Hasta Cuándo Se Puede?", "El Plazo Puede Vencer", "Nuevas Reglas Este Año"]),
        ("CTA INFORMATIVO", "Promete información, que es lo que la página entrega.",
         ["Mira Cómo Consultar", "Guía Gratuita Aquí", "Evita Errores Al Consultar"]),
    ],
    "en": [
        ("DKI", "Inserts the user's query into the headline.",
         ["{KeyWord:FALLBACK}", "Check {KeyWord:FALLBACK}", "{KeyWord:FALLBACK} 2026"]),
        ("LEGITIMATE QUESTION", "A question the reader actually has.",
         ["Are You Eligible This Year?", "Who Gets Left Out?", "What Changed In The Rules?"]),
        ("DEADLINE AND CHANGE", "Urgency anchored in a verifiable fact.",
         ["How Long Do You Have?", "The Deadline May Pass", "New Rules This Year"]),
        ("INFORMATIVE CTA", "Promises information — what the page actually delivers.",
         ["See How To Check", "Free Guide Here", "Avoid Common Mistakes"]),
    ],
}

_CABECALHO = {
    "pt": "Você escreve anúncios de Search do Google Ads para um portal de conteúdo.",
    "es": "Escribes anuncios de Search de Google Ads para un portal de contenido.",
    "en": "You write Google Ads Search ads for a content portal.",
}


def _restricoes_do_spec(v: Validador, spec: dict) -> list[str]:
    """Transforma cada regra ativa numa linha de instrução com sua fonte."""
    linhas = []
    regras = list(spec["estruturais"]) + spec["semanticas"].get(v.idioma, [])
    for r in regras:
        if r.get("verticais") and v.vertical not in r["verticais"]:
            continue
        if r["severidade"] not in ("erro", "bloqueio"):
            continue
        exemplos = r.get("proibidos") or r["deteccao"].get("frases", [])[:5]
        amostra = "; ".join(repr(e) for e in exemplos[:4])
        linhas.append(f"- {r['titulo']} — proibido. Ex.: {amostra}  [política {r['fonte']}]")
    return linhas


def montar(
    *,
    nicho: str,
    url: str,
    keywords: list[str],
    pais: str = "BR",
    vertical: str = "informativo",
    ano: int = 2026,
    n_headlines: int = 15,
    n_descriptions: int = 4,
    spec: dict | None = None,
) -> str:
    spec = spec or carregar()
    v = Validador(spec, pais=pais, vertical=vertical)
    idioma = v.idioma
    baldes = BALDES.get(idioma, BALDES["en"])

    hab = spec["habilitacao"].get(vertical)
    aviso_hab = ""
    if hab and pais in hab["paises_exigem"]:
        aviso_hab = (
            f"\nATENÇÃO — esta vertical exige `{hab['exige']}` em {pais}. "
            f"Sem isso o anúncio é reprovado independentemente do texto. "
            f"Escreva como portal de conteúdo que EXPLICA o tema, nunca como "
            f"quem presta o serviço.\n"
        )

    restricoes = "\n".join(_restricoes_do_spec(v, spec))
    exemplos_baldes = "\n".join(
        f"\n{i}. {nome} — {desc}\n   " + "\n   ".join(ex)
        for i, (nome, desc, ex) in enumerate(baldes, 1)
    )

    return f"""{_CABECALHO.get(idioma, _CABECALHO['en'])}

CONTEXTO
  nicho: {nicho}
  destino: {url}
  país: {pais} | idioma do anúncio: {idioma} | ano: {ano}
  vertical: {vertical}
{aviso_hab}
O QUE A PÁGINA ENTREGA
  Conteúdo explicativo sobre o tema. Ela NÃO executa serviço, NÃO consulta
  dados pessoais, NÃO processa pedido. Todo texto precisa ser verdadeiro em
  relação a isso — prometer o que a página não faz é deturpação (política
  6020955), e é a causa mais comum de reprovação em portal de conteúdo.

OBJETIVO
  CTR alto por RELEVÂNCIA, não por sensacionalismo. O leitor que clica
  esperando informação e encontra informação permanece, lê e interage. O que
  clica enganado sai em 3 segundos — e isso destrói tanto a receita da página
  quanto a qualidade percebida do anúncio.
  Referência medida: Search entrega 9,71% de CTR contra ~5% dos demais
  canais, e essa diferença vem de intenção qualificada.

RESTRIÇÕES ABSOLUTAS — derivadas da política oficial do Google Ads
{restricoes}

  Adicionalmente, jamais use: emoji, PONTUAÇÃO DUPLA, CAIXA ALTA em palavra
  comum (siglas como FGTS, CPF, INSS são permitidas), espaço duplo, letra
  trocada por número, ou a mesma palavra repetida dentro do mesmo texto.

MECÂNICA DE CTR — distribua os {n_headlines} títulos entre os quatro baldes
{exemplos_baldes}

REGRAS DE FORMA
  - Títulos: máximo 30 caracteres. A tag DKI conta pelo FALLBACK, não pelo
    texto cru: "{{KeyWord:Saque FGTS}} 2026" conta 15, não 25.
  - Descrições: máximo 90 caracteres, {n_descriptions} no total.
  - Title Case em títulos. Frase normal em descrições.
  - Nenhuma palavra com 4+ letras pode aparecer em mais de 4 títulos
    (política 14848296 — repetição entre recursos). As raízes do termo
    buscado são a ÚNICA exceção: repeti-las é o que o Google pede em
    "Try including more keywords in your headlines", e o teto acima existe
    contra vocabulário repetido à toa, não contra relevância.
  - Use APENAS as keywords fornecidas como base semântica. Não invente
    termos que a página não cobre — relevância pouco clara é violação
    (política 15936964).

KEYWORDS VALIDADAS
{chr(10).join('  - ' + k for k in keywords)}

SAÍDA — JSON puro, sem cercas de código:
{{
  "headlines": [{n_headlines} strings],
  "descriptions": [{n_descriptions} strings],
  "sitelinks": [{{"title": "≤25", "description1": "≤35", "description2": "≤35"}}, ...4],
  "callouts": [4 strings de ≤25],
  "snippet": {{"header": "<header oficial>", "values": [4 strings de ≤25]}}
}}

Antes de responder, releia cada string contra as RESTRIÇÕES ABSOLUTAS.
Um texto reprovado custa dias de revisão e mancha a conta; um texto morno
custa apenas um teste. Prefira morno a reprovado — mas busque afiado."""
