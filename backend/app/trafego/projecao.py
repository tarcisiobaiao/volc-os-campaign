"""Os objetos do `volc_ads` projetados para a tela.

## Por que uma camada de projeção, e não `dataclasses.asdict`

`asdict` seria uma linha e três defeitos:

1. **Vaza tudo.** `Origem.texto_da_lp` carrega o artigo inteiro da landing page —
   dezenas de kB que a tela não usa, num payload que o cockpit pede a cada
   abertura. Aqui ele vira só o que a checagem de congruência precisa.
2. **Achata o que não pode achatar.** `Cpc` é um objeto de três campos
   (`valor`, `procedencia`, `moeda`) exatamente para que ninguém apresente o
   número sem dizer de onde veio. `asdict` o transformaria num dicionário
   anônimo que a tela pode desmontar sem perceber.
3. **Amarra a tela ao interno.** Renomear um campo do `volc_ads` quebraria o
   front em silêncio, e o front não tem teste de contrato contra o engine.

## A regra que esta camada existe para impor

**Nenhum CPC sai sem procedência.** `services_used` do cluster medido inclui
`n8n:dataforseo`, e `avg_cpc_local` e `currency` chegam NULOS. O
`DATAFORSEO-MEDIDO.md` mediu, com 96 chamadas, que `keyword_info.cpc`
superestima o CPC real em 7,4× **e inverte a ordem dentro do cluster** — nenhum
fator de correção resolve.

Um número de proveniência desconhecida apresentado como medição é o defeito
exato que o `PORTOES_EXIGEM_MEDICAO` do motor de pautas existe para impedir. Por
isso `_cpc()` é a única porta de saída de CPC deste módulo, e ela nunca devolve
um número solto.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _agora_iso() -> str:
    """O instante em que ESTA projeção foi montada, com fuso explícito.

    Mesmo formato de `routers/trafego.py:5268` (`_agora_iso`), e replicado aqui
    em vez de importado: a projeção é chamada PELO router, e importar de volta
    fecharia o ciclo. Duas linhas iguais custam menos que um import circular —
    e o que a tela não pode ter são dois FORMATOS de instante, não duas
    definições da mesma linha.

    Com fuso, e não `datetime.now()` nu: um instante ingênuo chega ao navegador
    interpretado no fuso de quem olha, que não é o fuso do servidor nem o da
    conta de anúncio.
    """
    return datetime.now(timezone.utc).isoformat()


def _cpc(c: Any) -> dict[str, Any] | None:
    """Um CPC com a procedência colada. Nunca um float solto.

    `moeda` pode chegar `None` — o cluster medido não a declara. A tela mostra
    "moeda não declarada" em vez de assumir BRL, porque assumir é como um número
    de sete países vira um número de um país sem ninguém notar.

    ⚠️ `valor` SAI `None` QUANDO É AUSENTE, E ISSO CONSERTA UMA CONTRADIÇÃO
    DESTE PRÓPRIO ARQUIVO.

    Até 03/09/2026 a linha era `float(getattr(c, "valor", 0) or 0)` — a única
    `or 0` do módulo. Um CPC não medido chegava à tela como `0.0` e era
    desenhado "R$ 0,00", que é uma AFIRMAÇÃO: diz que o clique é de graça. O
    docstring do topo abre com "Nenhum CPC sai sem procedência" e o de
    `escrita()` escreve, sobre outro campo, que "um zero ali seria um custo
    medido que não foi medido". A doutrina estava certa e a porta de saída a
    contradizia.

    Um `0.0` que chegue aqui daqui em diante é um zero MEDIDO e continua saindo
    como `0.0` — ausência e zero deixaram de ser a mesma coisa.
    """
    if c is None:
        return None
    valor = getattr(c, "valor", None)
    return {
        "valor": None if valor is None else float(valor),
        "procedencia": getattr(c, "procedencia", "") or "",
        "moeda": getattr(c, "moeda", None),
        "medido_na_conta": bool(getattr(c, "medido_na_conta", False)),
    }


def keyword(k: Any) -> dict[str, Any]:
    return {
        "texto": k.texto,
        "volume": k.volume,
        "cpc": _cpc(k.cpc),
        "competicao": k.competicao,
        "tendencia": k.tendencia,
        "tags": list(k.tags or ()),
        # O motivo pelo qual a mineração aprovou esta keyword para anúncio.
        # É o que permite ao operador discordar da triagem sabendo do quê.
        "motivo": k.motivo,
        "tambem_em_conteudo": bool(k.tambem_em_conteudo),
    }


def grupo(g: Any) -> dict[str, Any]:
    """Uma sub-intenção — que é um candidato a AD GROUP, não um rótulo.

    `cpc_simples` e `cpc_ponderado` viajam os dois de propósito: a média simples
    é a do conjunto de termos e a ponderada é a do tráfego que ele traria. Elas
    divergem quando um termo de volume enorme puxa o grupo, e essa divergência é
    informação — foi o que separou ACESSO (volume 31.030, CPC 0,74) de
    ELEGIBILIDADE (volume 11.580, CPC 1,09) no cluster medido.
    """
    return {
        "tipo": g.tipo,
        "descricao": g.descricao,
        "keywords": [keyword(k) for k in g.keywords],
        "volume": g.volume,
        "cpc_simples": _cpc(g.cpc_simples),
        "cpc_ponderado": _cpc(g.cpc_ponderado),
        # O que o Pautador DECLAROU contra o que a fila de anúncio de fato tem.
        # Divergência aqui não é erro: é a triagem tendo removido keyword do
        # grupo. Mostrar os dois evita que alguém "conserte" um número certo.
        "volume_declarado": g.volume_declarado,
        "keywords_declaradas": g.keywords_declaradas,
        "fora_da_fila": list(g.fora_da_fila or ()),
    }


def triagem(t: Any) -> dict[str, Any]:
    """A triagem que a mineração já fez, apresentada COMO triagem.

    `analisadas` é o denominador honesto. Mostrar "23 aprovadas" sem ele
    esconderia que 63 foram descartadas — e o descarte é a parte do trabalho que
    já foi feita, não lixo a ser omitido.
    """
    return {
        "analisadas": t.analisadas,
        "aprovadas_anuncio": t.aprovadas_anuncio,
        "para_conteudo": t.para_conteudo,
        "descartadas": t.descartadas,
        "breakdown": dict(t.breakdown or {}),
        "volume_total": t.volume_total,
        "volume_da_fila": t.volume_da_fila,
    }


def aviso(a: Any) -> dict[str, Any]:
    return {"codigo": a.codigo, "severidade": a.severidade,
            "titulo": a.titulo, "detalhe": a.detalhe}


def origem(o: Any, *, com_texto_da_lp: bool = False) -> dict[str, Any]:
    """O que a campanha herda do funil.

    ⚠️ `texto_da_lp` fica FORA por padrão. É o artigo inteiro — dezenas de kB
    num payload que a tela pede a cada abertura do cockpit. Ele só viaja quando
    alguém vai fazer a checagem de congruência anúncio × página, e aí viaja
    inteiro de propósito: cruzar com um resumo produziria falso negativo.
    """
    if o is None:
        return {}
    saida = {
        "opportunity_id": o.opportunity_id,
        "run_id": o.run_id,
        "project_id": o.project_id,
        "url_final": o.url_final,
        # De um RASCUNHO o WordPress devolve `?post_type=r&p=2146`, não o
        # permalink. Quem anunciar essa URL manda tráfego para um endereço que
        # vai mudar — por isso `status_wp` viaja colado.
        "url_procedencia": o.url_procedencia,
        "status_wp": o.status_wp,
        "post_type": o.post_type,
        "dominio": o.dominio,
        "nicho": o.nicho,
        "slug": o.slug,
        "pais": o.pais,
        "idioma": o.idioma,
        "idioma_declarado": o.idioma_declarado,
        # `vertical` não é rótulo: é o eixo do portão de habilitação
        # (país × vertical) do `policy/spec.py`. `vertical_declarada` guarda o
        # que o card dizia, para a divergência ficar visível.
        "vertical": o.vertical,
        "vertical_declarada": o.vertical_declarada,
        "resumo_da_pesquisa": o.resumo_da_pesquisa,
        "fatos": [{"id": f.id, "tipo": f.tipo, "texto": f.texto, "fonte": f.fonte}
                  for f in (o.fatos or ())],
        "tem_texto_da_lp": bool(o.texto_da_lp),
    }
    if com_texto_da_lp:
        saida["texto_da_lp"] = o.texto_da_lp
    return saida


def cockpit(c: Any, *, com_texto_da_lp: bool = False) -> dict[str, Any]:
    """O cockpit inteiro, COM o veredito de prontidão que o domínio já emitiu.

    ⚠️ `bloqueado` e `bloqueios` são COPIADOS, nunca recalculados aqui.

    `Cockpit.bloqueado` e `Cockpit.bloqueios` são `@property` de
    `volc_ads/pautador_ponte.py` desde sempre, e `para_json()` até emitia a
    primeira — mas esta função não copiava nenhuma das duas. O payload levava
    só `avisos[]`, e cada tela refiltrava por severidade no navegador: duas
    réguas para o mesmo veredito, a do engine barrando só `bloqueio` e a da
    tela barrando tudo que não fosse `informacao`. Refiltrar aqui seria a
    TERCEIRA régua, e é justamente o que `alerta_de_entrega()` documenta não
    fazer ("qualquer conta feita aqui seria uma segunda régua fora do alcance
    dos testes").

    Por isso o acesso é direto (`c.bloqueado`), sem `getattr(..., False)`: o
    default de um `getattr` seria "não há bloqueio", que é o fail-OPEN exato
    que um portão não pode ter. Um objeto que não carrega a propriedade não é
    um `Cockpit`, e é melhor que isso levante aqui do que vire um payload que
    diz "pode subir".
    """
    return {
        "opportunity_id": c.opportunity_id,
        "cluster_id": c.cluster_id,
        "origem": origem(c.origem, com_texto_da_lp=com_texto_da_lp),
        "triagem": triagem(c.triagem) if c.triagem else None,
        "grupos": [grupo(g) for g in (c.grupos or ())],
        "descartadas": [{"texto": d.texto, "volume": d.volume, "cpc": _cpc(d.cpc),
                         "motivo": d.motivo, "destino": d.destino}
                        for d in (c.descartadas or ())],
        "procedencia": {
            "servicos_declarados": list(getattr(c.procedencia, "servicos_declarados", ()) or ()),
            "engine": getattr(c.procedencia, "engine", None),
            "moeda_do_cluster": getattr(c.procedencia, "moeda_do_cluster", None),
            "moeda_da_oportunidade": getattr(c.procedencia, "moeda_da_oportunidade", None),
            "cpc_medio_do_cluster": getattr(c.procedencia, "cpc_medio_do_cluster", None),
            "medido_na_conta": bool(getattr(c.procedencia, "medido_na_conta", False)),
            "aviso": getattr(c.procedencia, "aviso", None),
        } if c.procedencia else None,
        "avisos": [aviso(a) for a in (c.avisos or ())],
        "bloqueado": bool(c.bloqueado),
        "bloqueios": [aviso(a) for a in (c.bloqueios or ())],
        # QUANDO esta projeção foi montada. Sem ele a tela só tinha o relógio do
        # navegador, que mede a hora de quem olha e não a idade do dado — um
        # cockpit de duas horas atrás parecia recém-lido.
        "lido_em": _agora_iso(),
    }


def preparo(p: Any) -> dict[str, Any]:
    """O resultado da prova. É o que decide se o botão de subir acende.

    Os três estados NÃO são intercambiáveis, e a tela precisa dizer qual foi:

      `recusa_local`     a validação de forma/política reprovou aqui, de graça,
                         antes de qualquer chamada. É o mais barato.
      `falha_validacao`  o payload chegou à API e ela recusou. `validate_only`
                         é leitura: nada foi criado.
      `selo`             passou nos dois. É o pré-requisito estrutural de
                         `subir()` — sem ele, escrever é recusado.
    """
    selo = p.selo
    return {
        "customer_id": p.customer_id,
        "login_customer_id": p.login_customer_id,
        "nome_campanha": p.nome_campanha,
        "n_operacoes": len(p.operacoes or ()),
        "selo": {
            "impressao": selo.impressao,
            "n_operacoes": selo.n_operacoes,
            "carimbo": selo.carimbo,
        } if selo else None,
        "recusa_local": _resultado(p.recusa_local),
        # O que a autocorreção de política fez. Vai SEMPRE — inclusive quando a
        # prova passou —, porque é justamente no sucesso que a mudança
        # silenciosa engana: o operador aprovaria uma campanha sem saber que
        # uma keyword saiu e outra foi isentada.
        "autocorrecao": list(getattr(p, "autocorrecao", ()) or []),
        # Os avisos da validação local. Pela MESMA razão da `autocorrecao`
        # acima: vão inclusive quando a prova passa. "a negativa 'saque' anula a
        # keyword 'saque anual fgts'" e "duplicata removida" só existiam dentro
        # do `Resultado`, e o `Resultado` só sobrevivia pelo `recusa_local` —
        # que é preenchido apenas quando algo BARRA. No caminho feliz, que é o
        # caminho em que o operador aprova e gasta, eles sumiam.
        "avisos_locais": list(getattr(p, "avisos_locais", ()) or []),
        # De onde vem cada imagem que este payload manda criar. Vazio para os
        # canais que não criam imagem — e `getattr` defensivo porque a projeção
        # também serve `Preparo` de versões que não tinham o campo.
        "linhagem": _linhagem(getattr(p, "linhagem", ())),
        "falha_validacao": _falha(p.falha_validacao),
        "aprovado": bool(selo),
    }


def _resultado(r: Any) -> dict[str, Any] | None:
    """O `validacao.Resultado` local, com cada achado nomeado.

    Um "reprovou" sem os achados obrigaria o operador a adivinhar o que
    consertar — que é exatamente o que o flow n8n fazia ao quebrar em silêncio.

    ⚠️ E era exatamente o que esta função fazia, até 19/08/2026.

    `Preparo.recusa_local` é uma **string** (`volc_ads/subir.py:127`), montada
    por `Resultado.resumo()`. Esta função esperava um objeto com `.ok` e
    `.achados`, então `getattr(str, "ok", False)` devolvia `False` e
    `getattr(str, "achados", ())` devolvia vazio: TODA recusa local chegava à
    tela como `{"ok": false, "achados": []}`.

    Medido no card 74 em 19/08/2026: o engine reprovou com **13 achados**
    (verificação de serviços financeiros ausente, uma description de 91 chars e
    8 violações de "letras maiúsculas alternadas") e a API devolveu zero. O
    operador via "reprovado" sem uma linha do que consertar.

    Agora a string é preservada em `resumo` — é ela que carrega os motivos — e
    o formato de objeto continua atendido quando o chamador passar um
    `Resultado` de verdade.
    """
    if r is None or r == "":
        return None
    # O caminho real hoje: `recusa_local` é o resumo textual da reprovação.
    if isinstance(r, str):
        return {"ok": False, "resumo": r, "achados": []}
    return {
        "ok": bool(getattr(r, "ok", False)),
        "resumo": r.resumo() if hasattr(r, "resumo") else "",
        "achados": [{
            "campo": getattr(a, "campo", ""),
            "valor": getattr(a, "valor", ""),
            "motivo": getattr(a, "motivo", ""),
            "severidade": getattr(a, "severidade", "erro"),
        } for a in (getattr(r, "achados", ()) or ())],
    }


def _falha(f: Any) -> dict[str, Any] | None:
    """A `FalhaGads` classificada, com a evidência de política preservada.

    `gads/errors.py` extrai o índice do campo, a `PolicyViolationKey` e o
    `is_exemptible` — sem eles, num mutate de ~72 operações sabe-se que ALGO
    violou e não se sabe O QUÊ. Achatar isso aqui desfaria o trabalho.
    """
    if f is None:
        return None
    return {
        "classe": _nome(getattr(f, "classe", None)),
        "resumo": f.resumo() if hasattr(f, "resumo") else str(f),
        "request_id": getattr(f, "request_id", None),
        # ⚠️ OS NOMES AQUI PRECISAM SER OS DO `ErroGads`, E NÃO ERAM.
        #
        # A dataclass declara `campo_codigo`, `valor_codigo`, `caminho_campo` e
        # `indice_operacao`. Esta projeção pedia `codigo`, `familia`, `caminho`
        # e `indice` — quatro nomes que não existem. Com `getattr(..., "")` o
        # erro é MUDO: nada levanta, os quatro chegam vazios à tela, e o que
        # sobra é "A policy was violated", que é a mensagem genérica do Google.
        #
        # Medido no card 65 em 19/08/2026: a violação era nomeável —
        # `NON_FAMILY_SAFE('como sacar o fgts na caixa')` e
        # `PERSONAL_LOANS('saldo bloqueado fgts empréstimo como desbloquear')`,
        # as duas isentáveis. O operador viu a frase genérica duas vezes.
        "erros": [{
            "codigo": getattr(e, "campo_codigo", ""),
            "valor": getattr(e, "valor_codigo", ""),
            "caminho": getattr(e, "caminho_campo", ""),
            "indice": getattr(e, "indice_operacao", None),
            "mensagem": getattr(e, "mensagem", ""),
            "gatilho": getattr(e, "gatilho", ""),
            "politica": _politica(getattr(e, "politica", None)),
        } for e in (getattr(f, "erros", ()) or ())],
        # O que a tela precisa para oferecer a decisão: o texto que violou e se
        # a violação COMPORTA isenção. Sem isto, "reprovado" é um beco.
        "textos_violadores": list(getattr(f, "textos_violadores", ()) or ()),
        "chaves_isentaveis": [str(k) for k in (getattr(f, "chaves_isentaveis", ()) or ())],
        "de_politica": bool(getattr(f, "de_politica", False)),
    }


def _politica(p: Any) -> dict[str, Any] | None:
    if p is None:
        return None
    # ⚠️ Mesma armadilha de `_falha`: a dataclass `Politica` declara `isentavel`
    # e `chave` (UMA, singular). Pedir `is_exemptible` e `chaves` devolvia
    # `None` e `[]` — e era justamente `is_exemptible` que dizia se havia
    # caminho de volta. A tela mostrava "reprovado" sem contar que a violação
    # era isentável.
    #
    # `remedio` é `@property`, então `getattr` já devolve a STRING; o `callable`
    # do código antigo nunca era verdadeiro e o ramo morria sem uso.
    chave = getattr(p, "chave", None)
    return {
        "formato": _nome(getattr(p, "formato", None)),
        "isentavel": getattr(p, "isentavel", None),
        "remedio": getattr(p, "remedio", ""),
        "nome_externo": getattr(p, "nome_externo", ""),
        "descricao_externa": getattr(p, "descricao_externa", ""),
        "chave": {"policy_name": getattr(chave, "policy_name", ""),
                  "violating_text": getattr(chave, "violating_text", "")} if chave else None,
        "topicos": [{"topico": getattr(t, "topico", ""),
                     "tipo": getattr(t, "tipo", ""),
                     "ignoravel": getattr(t, "ignoravel", None),
                     "evidencias": list(getattr(t, "evidencias", ()) or ())}
                    for t in (getattr(p, "topicos", ()) or ())],
    }


def recibo(r: Any) -> dict[str, Any]:
    """O que aconteceu na conta. Só existe depois de o mutate ter partido."""
    return {
        "estado": r.estado,
        "carimbo": r.carimbo,
        "customer_id": r.customer_id,
        "login_customer_id": r.login_customer_id,
        "nome_campanha": r.nome_campanha,
        "n_operacoes": r.n_operacoes,
        "impressao": r.impressao,
        "motivo": r.motivo,
        # Os resource names criados. Sem eles, uma campanha nova só é
        # reencontrável por busca textual no nome.
        "criados": [{"posicao": c.posicao, "tipo": c.tipo,
                     "resource_name": c.resource_name} for c in (r.criados or ())],
        "request_id": r.request_id,
        # A procedência do que foi enviado. Vale mais quando o estado é
        # INDETERMINADO: é ela que diz quais bytes, com qual hash e de qual
        # insumo saíram, e sem isso conferir a conta é comparar imagens a olho.
        "linhagem": _linhagem(getattr(r, "linhagem", ())),
        "falha": _falha(r.falha),
        "explicacao": r.explicacao,
    }


def _linhagem(itens: Any) -> list[dict[str, Any]]:
    """A procedência das imagens que o payload cria — ou criou.

    ⚠️ Vai SEMPRE, inclusive quando está vazia, e inclusive no sucesso. É a
    mesma razão de `autocorrecao`: é no sucesso que a ausência de rastro
    engana. Um operador que aprova gasto sobre um payload cujas imagens têm
    `confirmada: false` precisa ver isso ANTES de clicar — e até 27/08/2026
    esse sinal existia em `Preparo.linhagem` e morria no processo, porque esta
    função não o carregava.

    `confirmada` é escrita explicitamente por `Linhagem.para_json()`: ela é
    property, e `dataclasses.asdict` não enxerga property. Sem isso a tela
    receberia todos os campos e justamente não o veredito sobre eles.
    """
    saida = []
    for ln in (itens or ()):
        para_json = getattr(ln, "para_json", None)
        if callable(para_json):
            saida.append(para_json())
            continue
        # NEM SILENCIO, NEM EXCECAO. As duas versoes anteriores erraram, e a
        # segunda errou pior.
        #
        # A primeira usava `dict(ln)` como fallback e fazia exatamente o que o
        # paragrafo acima diz impedir: entregava os campos e perdia
        # `confirmada`, porque `confirmada` e property.
        #
        # A segunda levantava. Parecia mais honesto e era perigoso: esta funcao
        # roda em `routers/trafego.py` no `/subir`, e a linha
        # `projetado = projecao.recibo(recibo)` vem ANTES de
        # `_registrar_campanha(...)`, fora do try. Uma excecao aqui vira 500
        # DEPOIS de a campanha ja existir na conta e ANTES de ela ser gravada no
        # nosso banco — que e literalmente o defeito que o comentario daquele
        # trecho documenta ("o cockpit continuava oferecendo lancar campanha").
        # O proprio arquivo ja tinha decidido isto: "A gravacao NAO derruba o
        # lancamento (...) O erro vira aviso no recibo."
        #
        # Entao o item vira um registro que DECLARA nao ter sido projetado, com
        # `confirmada: null` — "nao apurei", que e a forma da casa para
        # ausencia. Aparece, nao mente, e nao custa a campanha.
        if isinstance(ln, dict):
            projetado = dict(ln)
            if projetado.get("confirmada") is None:
                projetado["confirmada"] = None
                projetado["erro_de_projecao"] = (
                    "veio como dict sem `confirmada`; o veredito sobre a "
                    "procedencia nao pode ser recalculado aqui")
            saida.append(projetado)
            continue
        saida.append({
            "nome": str(getattr(ln, "nome", "") or "?"),
            "confirmada": None,
            "erro_de_projecao": (
                f"tipo {type(ln).__name__} nao sabe virar JSON; esperado "
                "`campanha.brief.Linhagem`"),
        })
    return saida


def _nome(v: Any) -> str | None:
    """Enum → o nome, não o `repr`. `Classe.TERMINAL` vira `TERMINAL`."""
    if v is None:
        return None
    return getattr(v, "name", None) or getattr(v, "value", None) or str(v)


def escrita(e: Any) -> dict[str, Any]:
    """`copy/encomendar.Escrita` → a tela do estágio 3.

    ⚠️ `custo` sai como veio, e vem `None` quando o preço do modelo não está
    configurado — `copy/cliente.py` não inventa preço. A tela escreve "preço não
    configurado"; um zero ali seria um custo medido que não foi medido.

    `fatos_descartados` NÃO é ruído a esconder. Medido em 18/08/2026 no card 73:
    4 dos 6 fatos do funil têm `tipo: 'afirmacao'`, que a seção 2 do `PROMPT.md`
    não conhece — a copy foi escrita sem eles, e quem lê o anúncio precisa saber
    disso para não achar que o funil não tinha lastro.
    """
    return {
        "aceita": e.aceita,
        "copy": e.copy,
        # O que a cascata desistiu de consertar, com a classe e o alvo dentro
        # do texto. É o que diz QUAL título ficou torto, não que "algo" ficou.
        "pendentes": list(e.pendentes),
        "diario": list(e.diario),
        "geracoes_conjunto": e.geracoes_conjunto,
        "geracoes_asset": e.geracoes_asset,
        "fatos_usados": e.fatos_usados,
        "fatos_descartados": list(e.fatos_descartados),
        "medicao": e.medicao,
        "segundos": e.segundos,
    }


def alerta_de_entrega(d: Any, *, customer_id: str,
                      customer_name: str = "") -> dict[str, Any]:
    """`entrega.Diagnostico` → o que o cartão da tela mostra.

    ⚠️ Projeção BURRA de propósito. Ela não calcula, não compara e não sugere:
    só renomeia campos. Qualquer conta feita aqui seria uma segunda régua fora
    do alcance dos testes de `volc_ads/testes_entrega.py`, e a lição desta noite
    é exatamente essa — duas cópias do mesmo critério divergem na primeira
    mudança.

    O único derivado que viaja é `teto_de_cliques`, e ele nasce no módulo: é
    orçamento ÷ lance, divisão de dois fatos da conta.
    """
    return {
        # O contexto da conta faz parte da identidade da notificação. Sem ele,
        # o front só conseguiria chutar `contas[0]` ao montar o link do painel.
        "customer_id": customer_id,
        "customer_name": customer_name,
        "campaign_id": d.campaign_id,
        "campaign_name": d.campaign_name,
        "status": d.status,
        "veiculacao": d.veiculacao,
        "horas_ligada": d.horas_ligada,
        "impressoes": d.impressoes,
        "cliques": d.cliques,
        "custo": d.custo,
        "lance": d.lance,
        "orcamento": d.orcamento,
        "teto_de_cliques": d.teto_de_cliques,
        # O texto do Google, como ele escreveu. Lista vazia = sem observação.
        "razoes": list(d.razoes),
        "aprovacao_do_anuncio": d.aprovacao_do_anuncio,
        "sintoma": d.sintoma,
        "revisar": list(d.revisar()),
        "alteracoes": [
            {"quando": a.quando, "campo": a.campo, "de": a.de, "para": a.para,
             "origem": a.origem, "quem": a.quem, "resumo": a.resumo()}
            for a in d.alteracoes
        ],
    }
