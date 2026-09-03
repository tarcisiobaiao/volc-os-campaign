"""A REAUDITORIA AO VIVO — o ato explícito que emite um recibo de escopo `live`.

## O buraco que este módulo fecha, medido e declarado

A barreira 3 exige um recibo com `fingerprint_scope="live"`. Até aqui NENHUM
caminho de produção emitia um: o portão 2 carimba o ARTEFATO — o corpo que o
motor escreveu — e a página que o Google visita é esse corpo DENTRO do tema do
WordPress, com cabeçalho, menu, rodapé e slots de anúncio. São dois documentos
diferentes por construção, e o próprio `routers/trafego.py` escreve o aviso
contra compará-los: fazer isso emitia `DERIVA_AO_VIVO` em 100% das páginas
reais.

A consequência está registrada em
`docs/closure/paid-destination-policy-spine-v2/REMAINING-RISKS.md`, seção 6bis:
com `live_drift` em `NAO_APLICAVEL_E_DESCONHECIDO_EM`, a ausência do recibo
`live` REPROVA — e nenhum destino fica elegível para campanha. É fail-closed,
logo é seguro; e é uma parada operacional total.

O que faltava não era mais uma varredura. Era o ATO que registra a aprovação
sobre a página NO AR.

## Por que o ato tem DUAS ETAPAS, e por que a separação é o assunto

Um portão que se autoaprova em silêncio não é portão. Se `provar` já gravasse o
recibo, o recibo `live` passaria a existir como efeito colateral de uma leitura
— e a leitura acontece sempre que alguém abre uma tela.

Então:

    provar      → LÊ ao vivo, avalia, monta o recibo CANDIDATO e devolve o
                  HASH da prova. Não grava nada, em lugar nenhum.
    confirmar   → recebe aquele hash, RE-LÊ ao vivo, RE-AVALIA, e só então
                  devolve o recibo para quem grava.

O hash é o vínculo entre as duas etapas. Ele cobre a URL canônica, a impressão
do conteúdo ao vivo, as duas versões de política, o veredito, os bloqueios, os
desconhecidos e o inventário de links: qualquer um desses mudar entre a prova e
a confirmação muda o hash, e a confirmação vira conflito explícito em vez de
gravar uma aprovação sobre uma página que já não é a que foi provada.

`confirmar` NÃO confia na prova que recebeu. Ela poderia ter sido montada há uma
hora, ou por outra sessão. O que ela faz é refazer a prova e comparar hashes —
a prova antiga é o ESPERADO, nunca a evidência.

## O que este módulo não faz

Ele não abre conexão com o Supabase, não publica, não altera página, não ativa
campanha e não chama mutate nenhum do Google Ads. A reauditoria é SOMENTE
LEITURA; a confirmação devolve um recibo, e quem o grava é a rota — pelo
`paginas_publicadas` que já existe, sem tabela nova. É o mesmo desenho de
`landing_policy.registro`, e pelo mesmo motivo: I/O fora daqui é o que deixa o
portão inteiro ser testado sem rede.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import time
from typing import Any, Callable, Iterable, Sequence

from app.landing_policy import (
    CHAVE_DO_RECIBO,
    JANELA_DE_FRESCOR_PADRAO_S,
    POLICY_CONTRACT_VERSION,
    PaginaObservada,
    PapelDestino,
    PapelRelaxadoPeloCliente,
    carregar_fontes,
    elegibilidade_de_destino_de_campanha,
    emitir_recibo,
    impressao,
    impressao_canonica,
    papel_do_servidor,
    url_canonica,
    versao_da_fonte,
)
from app.landing_policy.varredura import REGIAO_CORPO, REGIOES_DE_CHROME
from app.publisher_quality.fetch import USER_AGENT_PADRAO, fetch_public_https_chain

#: O nome do artefato que `provar_destino` devolve. Ele viaja para a tela e para
#: o corpo da confirmação; versioná-lo é o que impede uma tela antiga de ler uma
#: prova nova "na medida do possível".
ESQUEMA_DA_PROVA = "landing_policy_reaudit_proof.v1"

#: A chave sob a qual o recibo ANTERIOR fica guardado quando um novo entra.
#:
#: ⚠️ Sobrescrever o recibo sem guardar o anterior apagaria a única prova de
#: contra o que a página foi aprovada da última vez — e é exatamente essa a
#: pergunta de uma auditoria seis semanas depois. Uma chave irmã custa nada;
#: `paginas_publicadas` é jsonb e não valida forma.
CHAVE_DO_RECIBO_ANTERIOR = "landing_policy_receipt_anterior"

#: O escopo que só a leitura ao vivo pode carimbar. `artifact` é o do portão 2.
ESCOPO_AO_VIVO = "live"

#: Teto por leitura. São três, e todas ficam na frente de uma ação humana.
TIMEOUT_DE_LEITURA_S = 8

#: Os três user-agents, e por que são TRÊS.
#:
#: A doutrina é a de `routers/trafego.py:LEITURAS_DO_DESTINO`, copiada de
#: propósito em vez de importada — aquele módulo é de outra frente e importar
#: dele acoplaria a reauditoria ao roteador de tráfego.
#:
#: `varrer_redirecionamento` só consegue falar de cloaking quando existe uma
#: variante ROTULADA como rastreador e pelo menos uma humana; sem o par a
#: verificação sai `unavailable`, vira desconhecido e reprova por ausência.
#: Duas leituras bastariam para isso.
#:
#: A TERCEIRA existe pelo falso positivo medido em `/r/fgts-saque-aniversario/`:
#: com UMA variante humana só, qualquer diferença entre ela e a do rastreador
#: vira acusação de cloaking — inclusive a que vem de layout por dispositivo.
#: Ali o Googlebot recebeu HTML byte a byte igual ao do desktop, e desktop e
#: mobile é que diferiam em 27 bytes de um token rotativo de push. Com duas
#: variantes humanas, "desktop ≠ mobile" é observação de dispositivo e não vira
#: achado.
#:
#: ⚠️ O rótulo `adsbot` não é decorativo: `varredura._ROTULO_DE_RASTREADOR_RE`
#: casa `bot\b|bot[-_]|googlebot|adsbot|crawler|spider`, e é o RÓTULO — não o
#: user-agent — que decide qual variante conta como rastreador. Renomear a
#: chave para algo sem "bot" desliga a checagem de cloaking em silêncio.
#:
#: E o AdsBot, e não o Googlebot, porque é ele que o Google manda ao DESTINO
#: PAGO. A identidade do VOLC vem primeiro na string para que o dono do site —
#: a própria casa — veja quem leu.
LEITURAS_DA_REAUDITORIA: tuple[tuple[str, str], ...] = (
    ("usuario_desktop", USER_AGENT_PADRAO),
    ("usuario_movel", f"{USER_AGENT_PADRAO} (Mobile; Android)"),
    ("adsbot",
     f"{USER_AGENT_PADRAO} (compatible; AdsBot-Google/1.0; "
     "+http://www.google.com/adsbot.html)"),
)

#: A variante que vale como "a página" para as varreduras que leem o HTML.
ROTULO_PRINCIPAL = LEITURAS_DA_REAUDITORIA[0][0]

#: A que aponta para o TEMA/WordPress e a que aponta para o FUNIL.
#:
#: ⚠️ Os dois códigos descrevem o mesmo fato físico — um hyperlink externo
#: clicável num destino pago — e mesmo assim têm donos diferentes, porque o
#: CONSERTO é feito em lugares diferentes: um sai do template do site, o outro
#: sai do texto que o motor escreveu. Mandar o operador ao repositório errado é
#: como um bloqueio fica seis semanas aberto.
#:
#: ⚠️ E nenhum dos dois é limpo por allowlist do cliente nem por
#: `adtech_declarada`: só `chrome_declarado_pelo_site` — configuração de
#: servidor, com procedência — limpa o do chrome. Ver o aviso em
#: `varredura` na linha que emite `LINK_EXTERNO_NO_CHROME`.
DONO_POR_CODIGO: dict[str, str] = {
    "LINK_EXTERNO_NO_CHROME": "tema/WordPress",
    "LINK_EXTERNO_CLICAVEL_EM_DESTINO_PAGO": "funil",
}

#: O dono quando o código não está no mapa e a evidência não diz a região.
#:
#: ⚠️ Ele é um PALPITE, e está escrito como um. O que a varredura mede é a
#: região do DOM; fora dos dois códigos de link não existe medição de
#: procedência, e inventar uma ("isto é do tema") mandaria o operador consertar
#: onde não há o que consertar. `funil` é o default porque é o único lado cujo
#: conteúdo este pipeline escreve — quando ele erra, erra apontando para a casa.
DONO_PADRAO = "funil"


class ReauditoriaRecusada(RuntimeError):
    """A prova não passou, ou a leitura não concluiu.

    ⚠️ As duas coisas na MESMA exceção de propósito: "a página tem bloqueio" e
    "não consegui olhar a página" terminam no mesmo lugar — não há recibo
    `live`, logo não há destino elegível. Separá-las em dois caminhos convidaria
    alguém a tratar a segunda como transitória e seguir mesmo assim.
    """


class ProvaDivergente(RuntimeError):
    """A confirmação não bate com a prova: a página mudou no meio do caminho.

    Carrega os dois hashes porque a mensagem sozinha não permite reconciliar —
    e porque a resposta da rota os mostra em 12 caracteres, que é o suficiente
    para o operador ver que são outros.
    """

    def __init__(self, esperado: str, observado: str) -> None:
        super().__init__(
            "a página mudou entre a prova e a confirmação: a impressão "
            f"observada agora ({observado[:12]}) não é a que foi provada "
            f"({esperado[:12]})."
        )
        self.esperado = esperado
        self.observado = observado


def _agora_iso(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc).isoformat()


def _com_dono(achado: dict[str, Any]) -> dict[str, Any]:
    """Acrescenta `owner` a um achado já serializado.

    O contrato de política não carrega dono — e não deveria: quem conserta é
    fato desta casa, não da política do Google. A atribuição mora aqui, ao lado
    do mapa que a sustenta.
    """
    codigo = str(achado.get("code") or "")
    dono = DONO_POR_CODIGO.get(codigo)
    if dono is None:
        evidencia = achado.get("evidence")
        regiao = ""
        if isinstance(evidencia, dict):
            regiao = str(evidencia.get("regiao") or "")
        dono = "tema/WordPress" if regiao in REGIOES_DE_CHROME else DONO_PADRAO
    return {**achado, "owner": dono}


def _inventario_de_links(avaliacao: Any) -> list[dict[str, Any]]:
    """O inventário de links, SANITIZADO e ordenado.

    ⚠️ Sai o texto da âncora. Ele é conteúdo da página, e o inventário viaja
    para a tela e para dentro do hash da prova — devolver âncora aqui faria a
    API do VOLC republicar trecho de página que ela só observou. O que fica é o
    que decide o veredito: host, região, classe, se está num botão e se está
    oculto.

    A ordenação é para o HASH: `impressao` canoniza chaves, não a ORDEM da
    lista, e uma lista com os mesmos links em outra ordem produziria outro hash
    — a confirmação viraria conflito a cada leitura, e um conflito que sempre
    acontece é um conflito que ninguém lê.
    """
    itens: list[dict[str, Any]] = []
    for verificacao in avaliacao.verificacoes:
        if verificacao.nome != "external_links":
            continue
        for bruto in verificacao.inventario:
            itens.append({
                "host": str(bruto.get("host") or ""),
                "regiao": str(bruto.get("regiao") or REGIAO_CORPO),
                "classe": str(bruto.get("classe") or ""),
                "em_botao": bool(bruto.get("em_botao")),
                "oculto": bool(bruto.get("oculto")),
            })
    return sorted(
        itens,
        key=lambda i: (i["host"], i["regiao"], i["classe"], i["em_botao"], i["oculto"]),
    )


def impressao_da_prova(
    *,
    canonica: str,
    impressao_do_conteudo: str,
    versao_do_contrato: str,
    versao_das_fontes: str,
    veredito: str,
    bloqueios: Sequence[dict[str, Any]],
    desconhecidos: Sequence[dict[str, Any]],
    inventario_de_links: Sequence[dict[str, Any]],
) -> str:
    """O HASH que amarra a prova à confirmação.

    ## O que está dentro, e por que cada peça

    * **URL canônica** — confirmar a prova de uma página gravando o recibo de
      outra é a falha que faz uma aprovação vazar para o destino errado.
    * **impressão do conteúdo ao vivo** — a projeção estrutural do que está no
      ar. É ela, e não o sha256 do byte, porque o byte muda a cada rotação de
      token de push e a confirmação viraria conflito permanente.
    * **as DUAS versões de política** — a do contrato (a forma da avaliação) e a
      da fonte (o texto das regras). Elas mudam por motivos diferentes, e um
      deploy entre a prova e a confirmação pode mudar só uma.
    * **veredito, bloqueios e desconhecidos** — o desfecho e o que o sustenta.
      Uma página que ganhou um bloqueio no meio do caminho tem outro hash.
    * **o hash do inventário de links** — porque um link novo pode não virar
      bloqueio HOJE (um host classificado, no corpo, num papel mais frouxo) e
      ainda assim ser a mudança que interessa. Sem isto, a página poderia ganhar
      um link e a confirmação passaria calada.

    ## O que NÃO está dentro, de propósito

    O instante da leitura. Se o carimbo entrasse, TODA confirmação divergiria —
    o hash mudaria a cada segundo e a segunda etapa seria impossível de
    concluir. O que amarra é a página, não o relógio.
    """
    return impressao({
        "esquema": ESQUEMA_DA_PROVA,
        "url_canonica": canonica,
        "content_fingerprint": impressao_do_conteudo,
        "policy_contract_version": versao_do_contrato,
        "policy_source_version": versao_das_fontes,
        "veredito": veredito,
        # `sort_keys` do JSON canônico ordena as CHAVES; a ordem das LISTAS é
        # nossa. Ordenar pelo JSON de cada item é estável e não depende de qual
        # campo existe em qual achado.
        "bloqueios": sorted(
            bloqueios,
            key=lambda a: (str(a.get("code") or ""), str(a.get("owner") or ""),
                           impressao(a)),
        ),
        "desconhecidos": sorted(
            desconhecidos, key=lambda d: str(d.get("verificacao") or "")
        ),
        "inventario_de_links_sha256": impressao(list(inventario_de_links)),
    })


@dataclasses.dataclass(frozen=True)
class ProvaDaReauditoria:
    """O que a leitura ao vivo provou — e o recibo que ela AINDA NÃO gravou.

    ⚠️ `recibo_candidato` já vem carimbado com `fingerprint_scope="live"`, e
    mesmo assim não é uma aprovação: ele só passa a existir para o portão 3
    quando alguém confirma e a rota grava. Um recibo `live` que nascesse gravado
    faria de toda abertura de tela uma aprovação.
    """

    url_canonica: str
    #: O HASH DE CONFIRMAÇÃO (sha256 hex, 64). Ver `impressao_da_prova`.
    impressao_da_prova: str
    elegivel: bool
    veredito: str
    motivos: list[str]
    bloqueios: list[dict[str, Any]]
    riscos: list[dict[str, Any]]
    desconhecidos: list[dict[str, Any]]
    recibo_candidato: dict[str, Any]
    inventario_de_links: list[dict[str, Any]]
    diff_com_o_recibo_anterior: dict[str, Any]
    lido_em_epoch: float

    def para_json(self) -> dict[str, Any]:
        """A evidência é ESTRUTURAL: códigos, hashes e contagens.

        Nada de HTML aqui dentro — a mesma regra de
        `trafego.DestinoDeCampanha.para_json`. O portão lê página pública;
        devolvê-la na resposta faria a API republicar o que ela só observou.
        """
        return {
            "schema": ESQUEMA_DA_PROVA,
            "url_canonica": self.url_canonica,
            "impressao_da_prova": self.impressao_da_prova,
            "elegivel": self.elegivel,
            "veredito": self.veredito,
            "motivos": list(self.motivos),
            "bloqueios": list(self.bloqueios),
            "riscos": list(self.riscos),
            "desconhecidos": list(self.desconhecidos),
            "recibo_candidato": dict(self.recibo_candidato),
            "inventario_de_links": list(self.inventario_de_links),
            "diff_com_o_recibo_anterior": dict(self.diff_com_o_recibo_anterior),
            "lido_em_epoch": self.lido_em_epoch,
            "lido_em": _agora_iso(self.lido_em_epoch),
        }


def _ler_ao_vivo(url: str, ler: Callable[..., dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """As três leituras públicas, ou `ReauditoriaRecusada`.

    `fetch_public_https_chain` já falha fechado em host privado, em salto para
    fora do HTTPS público e em resposta acima do teto de bytes. Ela TOLERA
    resposta de erro HTTP de propósito (o status é o dado), e é aqui que o
    status vira recusa: um destino que não serve a página não é destino, e
    avaliar o corpo de um 404 diria coisas verdadeiras sobre a página errada.

    ⚠️ O `except` largo é o oposto do permissivo — ele só consegue produzir
    RECUSA. Uma falha traduzida em recusa é o contrato; uma falha engolida é
    como "não deu para olhar" vira verde.
    """
    leituras: dict[str, dict[str, Any]] = {}
    for rotulo, agente in LEITURAS_DA_REAUDITORIA:
        try:
            leitura = ler(url, user_agent=agente, timeout=TIMEOUT_DE_LEITURA_S)
        except Exception as exc:  # noqa: BLE001 — traduzida abaixo, nunca engolida
            raise ReauditoriaRecusada(
                f"a leitura {rotulo!r} do destino não concluiu "
                f"({type(exc).__name__}: {str(exc)[:160]})") from exc
        status = int(leitura.get("status") or 0)
        if status != 200:
            raise ReauditoriaRecusada(
                f"a leitura {rotulo!r} do destino respondeu HTTP {status}. Um "
                "destino que não serve a página não é um destino elegível.")
        leituras[rotulo] = dict(leitura)
    return leituras


def _diff(recibo_anterior: dict[str, Any] | None, impressao_agora: str) -> dict[str, Any]:
    """O que mudou desde o último recibo desta URL.

    ⚠️ `escopo_anterior` está aqui porque é a distinção que fechou a barreira 3:
    um recibo de escopo `artifact` NÃO é o lado esquerdo desta comparação. Ele
    impressiona o corpo que o motor escreveu; esta impressão é a da página
    dentro do tema. `mudou` só afirma mudança quando os dois lados falam do
    mesmo documento — caso contrário a resposta honesta é "não havia com o que
    comparar", e é isso que `False` significa junto de um escopo diferente.
    """
    anterior = recibo_anterior or {}
    escopo = str(anterior.get("fingerprint_scope") or "") if anterior else ""
    impressao_anterior = str(anterior.get("content_fingerprint") or "")
    comparavel = bool(anterior) and escopo == ESCOPO_AO_VIVO and bool(impressao_anterior)
    return {
        "tinha_recibo": bool(anterior),
        "escopo_anterior": escopo or None,
        "impressao_anterior_12": impressao_anterior[:12] or None,
        "impressao_agora_12": impressao_agora[:12],
        "mudou": bool(comparavel and impressao_anterior != impressao_agora),
        "comparavel": comparavel,
    }


def provar_destino(
    *,
    url: str,
    papel_do_motor: str,
    recibo_anterior: dict[str, Any] | None,
    chrome_declarado_pelo_site: Sequence[str] = (),
    promessa_do_anuncio: str = "",
    agora: float | None = None,
    ler: Callable[..., dict[str, Any]] = fetch_public_https_chain,
) -> ProvaDaReauditoria:
    """Lê a página NO AR, avalia no ponto de campanha e monta o candidato.

    ZERO escrita: nem no WordPress, nem no Supabase, nem em disco. Três GETs
    públicos e aritmética.

    ⚠️ ELA NÃO SE AUTOAPROVA. O que sai daqui é um recibo CANDIDATO e um hash.
    Chamar esta função mil vezes não deixa nenhum destino elegível — só
    `confirmar_reauditoria`, com o hash na mão, devolve um recibo para gravar.

    ⚠️ E ela avalia EXATAMENTE os bytes que leu. Nada de reaproveitar o corpo do
    artefato: se o tema do WordPress injeta um link no rodapé, é aqui — e só
    aqui — que ele aparece.
    """
    canonica = url_canonica(url)
    if not canonica:
        raise ReauditoriaRecusada(
            "sem URL para reauditar: esta página não tem endereço no ar.")

    momento = time.time() if agora is None else float(agora)

    # ⚠️ O PAPEL É DO SERVIDOR, e ele é FORÇADO.
    #
    # `elegibilidade_de_destino_de_campanha` já força `paid_destination` lá
    # dentro; esta linha existe para provar aqui em cima que nada que o chamador
    # mande relaxa o regime — e para que a tentativa de relaxar levante em vez de
    # passar. `papel_do_motor` só chega ao recibo como `role_declared`, ao lado
    # do papel efetivamente avaliado: divergir não é erro, é a explicação de por
    # que o rigor subiu.
    try:
        papel = papel_do_servidor(
            e_destino_de_campanha=True, papel_do_motor=str(papel_do_motor or ""))
    except PapelRelaxadoPeloCliente as exc:
        raise ReauditoriaRecusada(str(exc)) from exc
    if papel is not PapelDestino.PAID_DESTINATION:  # pragma: no cover - trava de contrato
        raise ReauditoriaRecusada(
            "o papel apurado pelo servidor não é destino pago; a reauditoria "
            "não roda em regime mais frouxo do que o ponto que ela serve.")

    leituras = _ler_ao_vivo(canonica, ler)
    principal = leituras[ROTULO_PRINCIPAL]
    html = str(principal.get("html") or "")

    # ⚠️ A IMPRESSÃO CANÔNICA, E NÃO O SHA256 DO BYTE, COMO VALOR DA VARIANTE.
    #
    # A comparação entre variantes é de igualdade, e comparar bytes produziria
    # acusação de cloaking em toda página com nonce, token rotativo de push ou
    # carimbo de cache. Os bytes não somem: `sha256_observado` continua sendo o
    # do corpo lido. É a mesma escolha de `trafego._pagina_do_destino`.
    variantes = {
        rotulo: impressao_canonica(str(leitura.get("html") or ""))
        for rotulo, leitura in leituras.items()
    }
    impressao_ao_vivo = variantes[ROTULO_PRINCIPAL]
    sha256_ao_vivo = str(principal.get("sha256") or "")

    # ⚠️ SÓ UM RECIBO DE ESCOPO `live` SERVE COMO LADO ESQUERDO DA DERIVA.
    #
    # O recibo do portão 2 impressiona o ARTEFATO. Comparar os dois emitia
    # `DERIVA_AO_VIVO` em 100% das páginas reais — foi assim que a barreira 3
    # travou. Enquanto o recibo anterior for `artifact`, a deriva é honestamente
    # inobservável, e `live_drift` está em `NAO_APLICAVEL_E_DESCONHECIDO_EM`:
    # a ausência REPROVA. É fail-closed, não isenção — e é exatamente por isso
    # que esta rodada existe, para que a PRÓXIMA reauditoria tenha com o que
    # comparar.
    anterior_e_ao_vivo = (
        str((recibo_anterior or {}).get("fingerprint_scope") or "") == ESCOPO_AO_VIVO
    )
    pagina = PaginaObservada(
        url=canonica,
        html=html,
        status_http=int(principal.get("status") or 0) or None,
        # `None` seria "não foi medido"; aqui houve leitura, então a lista vem
        # mesmo vazia — é a diferença entre `unavailable` e `absent_confirmed`.
        saltos_redirecionamento=list(principal.get("hops") or []),
        cabecalhos=dict(principal.get("headers") or {}),
        variantes_sha256=variantes,
        sha256_observado=sha256_ao_vivo or None,
        sha256_aprovado=(
            str((recibo_anterior or {}).get("content_sha256") or "") or None
            if anterior_e_ao_vivo else None
        ),
        impressao_aprovada=(
            str((recibo_anterior or {}).get("content_fingerprint") or "") or None
            if anterior_e_ao_vivo else None
        ),
        recibo_de_aprovacao=recibo_anterior,
        avaliado_em_epoch=momento,
        # ⚠️ A JANELA É A DO CONTRATO, NUNCA A QUE O RECIBO DECLARA. Ler dali
        # deixaria a evidência escolher por quanto tempo ela mesma vale.
        janela_de_frescor_s=JANELA_DE_FRESCOR_PADRAO_S,
        promessa_do_anuncio=promessa_do_anuncio,
        papel_declarado=str(papel_do_motor or ""),
        chrome_declarado_pelo_site=tuple(chrome_declarado_pelo_site or ()),
        origem="reauditoria_ao_vivo",
        observado_em=_agora_iso(momento),
    )

    fontes = carregar_fontes()
    avaliacao = elegibilidade_de_destino_de_campanha(pagina, fontes=fontes)

    bloqueios = [_com_dono(a.para_json()) for a in avaliacao.bloqueios]
    riscos = [_com_dono(a.para_json()) for a in avaliacao.riscos]
    desconhecidos = [dict(d) for d in avaliacao.desconhecidos]
    inventario = _inventario_de_links(avaliacao)

    recibo_candidato = emitir_recibo(
        avaliacao,
        hash_do_conteudo=sha256_ao_vivo,
        carimbo=_agora_iso(momento),
        fontes=fontes,
        impressao_do_conteudo=impressao_ao_vivo,
        # ⚠️ A ÚNICA linha do sistema que carimba `live`. É ela que dá ao portão
        # 3 o lado esquerdo que faltava — e é por isso que ela mora atrás de uma
        # confirmação humana, e não dentro de uma leitura de tela.
        escopo_da_impressao=ESCOPO_AO_VIVO,
        carimbo_epoch=momento,
        janela_de_frescor_s=JANELA_DE_FRESCOR_PADRAO_S,
        papel_declarado=str(papel_do_motor or ""),
    )

    return ProvaDaReauditoria(
        url_canonica=canonica,
        impressao_da_prova=impressao_da_prova(
            canonica=canonica,
            impressao_do_conteudo=impressao_ao_vivo,
            versao_do_contrato=POLICY_CONTRACT_VERSION,
            versao_das_fontes=versao_da_fonte(fontes),
            veredito=avaliacao.veredito.value,
            bloqueios=bloqueios,
            desconhecidos=desconhecidos,
            inventario_de_links=inventario,
        ),
        # ⚠️ `paid_destination_ready`, e NUNCA `not bloqueios`. Testar só
        # bloqueios ignora os DESCONHECIDOS — verificação exigida que não pôde
        # ser concluída —, e as duas listas dizem coisas diferentes: só uma
        # delas some quando o software quebra.
        elegivel=bool(avaliacao.paid_destination_ready),
        veredito=avaliacao.veredito.value,
        motivos=list(avaliacao.motivos),
        bloqueios=bloqueios,
        riscos=riscos,
        desconhecidos=desconhecidos,
        recibo_candidato=recibo_candidato,
        inventario_de_links=inventario,
        diff_com_o_recibo_anterior=_diff(recibo_anterior, impressao_ao_vivo),
        lido_em_epoch=momento,
    )


def confirmar_reauditoria(
    *,
    prova_esperada: str,
    url: str,
    papel_do_motor: str,
    recibo_anterior: dict[str, Any] | None,
    chrome_declarado_pelo_site: Sequence[str] = (),
    promessa_do_anuncio: str = "",
    agora: float | None = None,
    ler: Callable[..., dict[str, Any]] = fetch_public_https_chain,
) -> tuple[dict[str, Any], ProvaDaReauditoria]:
    """RE-LÊ, RE-AVALIA e devolve o recibo `live` — ou levanta.

    ⚠️ Ela NÃO confia na prova que recebeu. A prova é o ESPERADO; a evidência é
    a leitura de agora. Uma confirmação que aceitasse o `recibo_candidato` que
    veio no corpo transformaria o hash num crachá — quem tem o texto entra.

    A ordem das duas recusas é deliberada:

    1. **divergência primeiro.** Se a página mudou, o veredito de agora fala de
       outra página, e recusar por "não elegível" mandaria o operador consertar
       um bloqueio que talvez nem exista mais.
    2. **elegibilidade depois.** Uma prova que já saiu reprovada tem hash
       estável — ela CASA na comparação — e precisa da segunda tranca, senão
       confirmar uma recusa gravaria um recibo de recusa como se fosse
       aprovação.

    Não grava nada. Quem grava é a rota, e a gravação é idempotente.
    """
    prova = provar_destino(
        url=url,
        papel_do_motor=papel_do_motor,
        recibo_anterior=recibo_anterior,
        chrome_declarado_pelo_site=chrome_declarado_pelo_site,
        promessa_do_anuncio=promessa_do_anuncio,
        agora=agora,
        ler=ler,
    )

    if prova.impressao_da_prova != str(prova_esperada or ""):
        raise ProvaDivergente(str(prova_esperada or ""), prova.impressao_da_prova)

    if not prova.elegivel:
        raise ReauditoriaRecusada(
            "a reauditoria ao vivo não concluiu que este destino pode receber "
            "tráfego pago: " + "; ".join(prova.motivos))

    return prova.recibo_candidato, prova


#: O que dois recibos precisam ter em comum para afirmarem A MESMA COISA.
#:
#: ⚠️ É uma LISTA DO QUE ENTRA, e não do que sai, e a escolha foi medida. A
#: primeira versão excluía `observed_at`/`observed_at_epoch` e comparava todo o
#: resto — e ainda assim dois `confirmar` seguidos divergiam, em
#: `inventory_hashes`: aquele dicionário carrega o hash do inventário de
#: `approval_receipt`, que descreve o RECIBO ANTERIOR, e o recibo anterior muda
#: justamente porque a primeira confirmação gravou o novo. Uma lista de exclusão
#: teria de crescer a cada campo derivado que alguém acrescentasse ao recibo, e
#: cada esquecimento voltaria a gravar em duplicata sem ninguém notar.
#:
#: O que está aqui é o que um consumidor LÊ para decidir: qual página, contra
#: qual política, com que veredito e o que sobrou. Nada disso muda por causa do
#: relógio, e tudo isso muda quando a página muda.
CAMPOS_DA_AFIRMACAO = (
    "url",
    "content_sha256",
    "content_fingerprint",
    "fingerprint_scope",
    "policy_contract_version",
    "policy_source_version",
    "gate_point",
    "role",
    "verdict",
    "paid_destination_ready",
    "not_ready_reasons",
    "blockers",
    "risks",
    "unknowns",
)


def _mesma_afirmacao(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Os dois recibos dizem a mesma coisa sobre a página, fora o carimbo.

    ⚠️ É ESTA, e não a igualdade estrita, que decide `mudou` — e a razão é
    MEDIDA: dois `confirmar` seguidos NUNCA produzem recibos byte a byte iguais.
    `observed_at` e `observed_at_epoch` carregam o instante real da leitura, e
    `inventory_hashes` carrega o hash do inventário do RECIBO ANTERIOR, que a
    primeira confirmação acabou de trocar. Com igualdade estrita, todo
    duplo-clique gravava de novo, empurrava
    o recibo da primeira confirmação para `..._anterior` e apagava o recibo que
    de fato precedeu a reauditoria — o histórico ficava com um item que dizia a
    mesma coisa que o atual, e a auditoria perdia exatamente o registro que
    procura.

    ⚠️ O QUE ISSO CUSTA, dito por extenso: uma reauditoria que reencontra a
    página inalterada NÃO renova o carimbo de frescor. A janela do contrato é de
    24 h, então uma página parada volta a vencer mesmo tendo sido relida. É uma
    troca deliberada — perder um refresco é reversível (basta a página mudar, ou
    a política mudar de versão); perder o histórico não é.
    """
    return all(a.get(campo) == b.get(campo) for campo in CAMPOS_DA_AFIRMACAO)


def aplicar_recibo(
    paginas_publicadas: Iterable[dict[str, Any]] | None,
    url: str,
    recibo: dict[str, Any],
) -> tuple[list[dict[str, Any]], bool]:
    """Põe o recibo na PÁGINA CERTA de `paginas_publicadas`. Devolve (lista, mudou).

    ## Por que uma lista NOVA

    `paginas_publicadas` é lida por outros passos na mesma requisição. Mutar em
    lugar transformaria um erro de ordem de execução em corrupção silenciosa do
    estado do run — é a mesma razão de `registro.anexar_recibo` devolver um dict
    novo.

    ## Por que idempotente, e sobre O QUÊ

    O operador clica duas vezes, o navegador reenvia, o retry da automação
    repete. Gravar de novo um recibo que afirma a mesma coisa não é errado, mas
    RESPONDER que gravou é: a tela mostraria "recibo atualizado" sem nada ter
    mudado, e o `updated_at` da linha andaria sem fato por trás.

    ⚠️ A comparação é sobre a AFIRMAÇÃO, não sobre os bytes — ver
    `_mesma_afirmacao`. Igualdade estrita nunca acontece entre duas
    confirmações, porque o carimbo é o instante real da leitura, e com ela o
    duplo-clique gravava sempre.

    ## Por que o recibo anterior não se perde

    Ele vai para `landing_policy_receipt_anterior`. A pergunta de auditoria não
    é só "contra o que esta página está aprovada hoje", é "contra o que ela
    estava aprovada quando a campanha rodou" — e sobrescrever apaga a segunda.
    Guardar só UM nível é deliberado: um histórico infinito dentro de uma coluna
    jsonb cresce sem teto e sem ninguém olhando.

    ⚠️ E o duplo-clique não o empurra para fora: um recibo que afirma o mesmo
    que o atual não é uma gravação, então nada rotaciona. Ver `_mesma_afirmacao`.

    ## Por que nenhuma página casada LEVANTA

    Devolver `(lista, False)` seria indistinguível do retry idempotente — a rota
    responderia `gravado=false` e o operador leria "já estava lá" quando na
    verdade o recibo não foi a lugar nenhum. Fail-closed e barulhento.
    """
    alvo = url_canonica(url)
    if not alvo:
        raise ReauditoriaRecusada(
            "sem URL canônica: não há página em que pendurar este recibo.")

    novas: list[dict[str, Any]] = []
    mudou = False
    casou = False
    for pagina in paginas_publicadas or []:
        if not isinstance(pagina, dict):
            # Uma linha que não é dict não é uma página publicada; preservá-la
            # verbatim é melhor que descartar dado que não é nosso.
            novas.append(pagina)
            continue
        if url_canonica(str(pagina.get("url_wp") or "")) != alvo:
            novas.append(dict(pagina))
            continue
        casou = True
        atual = pagina.get(CHAVE_DO_RECIBO)
        if isinstance(atual, dict) and atual and _mesma_afirmacao(atual, recibo):
            # Nada a dizer que já não esteja dito. O recibo que FICA é o que já
            # estava lá — trocá-lo por um gêmeo com outro carimbo seria uma
            # escrita sem fato por trás, e é ela que rotacionava o histórico.
            novas.append(dict(pagina))
            continue
        nova = {**pagina, CHAVE_DO_RECIBO: recibo}
        if isinstance(atual, dict) and atual:
            nova[CHAVE_DO_RECIBO_ANTERIOR] = atual
        novas.append(nova)
        mudou = True

    if not casou:
        raise ReauditoriaRecusada(
            f"nenhuma página publicada deste run tem a URL {alvo!r}. O recibo "
            "não foi gravado — gravá-lo em outra linha seria aprovar a página "
            "errada.")

    return novas, mudou
