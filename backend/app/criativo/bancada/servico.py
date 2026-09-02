"""A porta HTTP da bancada, e o unico lugar que decide ONDE o trabalho roda.

⚠️ A escolha do despachante e uma decisao de ambiente, nao de dominio. Hoje ha
um so: o local, sincrono, que roda no mesmo processo. Ele NAO e producao e a
diferenca esta declarada em `DespachanteLocal`. Quando Cloud Run Job ou worker
permanente entrarem, entram aqui — e `Encomenda`, `Recibo` e `MotorDeProducao`
nao mudam uma linha.

## Por que ha um singleton aqui, se o executor existe para nao ter singleton

Porque este e o singleton do PROCESSO (qual fila, qual pasta), nao do TRABALHO.
O que nao pode ser compartilhado e estado mutavel de execucao: diretorio,
semente, arquivo intermediario. Cada trabalho continua com o seu.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from volc_ads.criativo.contrato import NaturezaDaProcedencia

from .adaptadores.png_local import MotorPngLocal
from .adaptadores.remotion import MotorRemotion
from .adaptadores.tipografico import MotorTipografico
from . import fronteira_publica
from .contrato import FalhaDoMotor
from .operario import DespachanteLocal, Operario, Reaper
from .porta import Deposito, escolher_deposito

_TRAVA = threading.Lock()
_BANCADA: tuple[Deposito, Operario, DespachanteLocal] | None = None
_REAPER: Reaper | None = None


def raiz_da_bancada() -> Path:
    """Onde a fila e os diretorios de trabalho vivem.

    ⚠️ Sem caminho absoluto embutido. `CRIATIVO_BANCADA_DIR` manda; sem ela, cai
    para `~/.volc-os/bancada`, que e a mesma familia de caminho que o
    `ArmazenamentoLocal` ja usa.
    """
    do_ambiente = os.environ.get("CRIATIVO_BANCADA_DIR")
    if do_ambiente:
        return Path(do_ambiente)
    return Path.home() / ".volc-os" / "bancada"


def montar() -> tuple[Deposito, Operario, DespachanteLocal]:
    global _BANCADA
    with _TRAVA:
        if _BANCADA is not None:
            return _BANCADA
        raiz = raiz_da_bancada()
        raiz.mkdir(parents=True, exist_ok=True)
        # ⚠️ Pela PORTA, e nao pela classe. `escolher_deposito` le
        # `CRIATIVO_DEPOSITO` e devolve o adapter do ambiente; ausencia e
        # `sqlite`, que e o unico que sobe sem infraestrutura, e pedir
        # `postgres` sem DSN LEVANTA em vez de cair aqui em silencio. Instanciar
        # `DepositoDeTrabalhos` direto — como era — significava que o processo
        # web tinha uma fila e o worker podia ter outra.
        deposito = escolher_deposito(caminho_sqlite=raiz / "fila.db")

        motores: dict[str, Any] = {}
        # ⚠️ Um motor que nao consegue nascer NAO derruba a bancada, e tambem nao
        # e silenciado: ele simplesmente nao entra no registro, e um trabalho que
        # o pedir falha com `motor_desconhecido`, que e legivel. Registrar um
        # motor quebrado seria pior: a falha apareceria no meio do render.
        try:
            motores["tipografico-local"] = MotorTipografico()
        except FalhaDoMotor:
            pass
        # ⚠️ O motor de PNG local NAO esta dentro de um `try`, e a ausencia e
        # deliberada: ele nao tem pre-requisito nenhum (`zlib` e `struct` vem com
        # o interpretador). Se ele falhasse ao nascer, isso seria defeito nosso e
        # nao condicao de maquina — e silencia-lo apagaria justamente o unico
        # motor que garante que esta bancada consegue produzir alguma coisa.
        motores[MotorPngLocal.slug] = MotorPngLocal()
        # ⚠️ O motor de VIDEO fica dentro do `try` pelo mesmo motivo que o
        # tipografico: ele tem pre-requisitos que nem toda maquina cumpre —
        # `node`, o runtime Remotion instalado e a fonte licenciada no
        # repositorio. Se algum faltar, ele NAO se registra, e um pedido de video
        # falha com `motor_desconhecido`, que e legivel. Registrar um motor que
        # nao consegue nascer faria a falha aparecer no meio do render.
        try:
            motores[MotorRemotion.slug] = MotorRemotion()
        except FalhaDoMotor:
            pass

        operario = Operario(
            deposito, motores, raiz / "trabalhos", loja=_loja_da_bancada()
        )
        _BANCADA = (deposito, operario, DespachanteLocal(operario))
        return _BANCADA


def _loja_da_bancada() -> Any | None:
    """O armazenamento que o operario usa para publicar e RELER.

    ⚠️ Antes desta fatia o operario nao publicava em lugar nenhum: gravava no
    disco do proprio processo e pronto. A consequencia estava escrita no
    inventario e ninguem tinha fechado — um worker em OUTRA maquina produzia
    pecas que a web classificava como perdidas, porque a leitura web faz
    `Path(caminho).read_bytes()` sobre um caminho que so existe no disco de quem
    produziu.

    `None` quando o armazenamento nao pode ser construido. Isso NAO derruba a
    bancada e tambem nao e silenciado: o recibo registra cada artefato como
    `NAO_PUBLICADO`, com nome, em vez de deixar o campo vazio parecendo que
    ninguem perguntou.
    """
    from app.criativo.armazenamento import armazenamento_padrao  # noqa: PLC0415

    try:
        return armazenamento_padrao()
    except Exception:  # noqa: BLE001 — ambiente sem storage configurado
        return None


def iniciar_reaper(*, intervalo_s: float = 10.0) -> Reaper:
    """Liga o coletor de leases vencidos. Idempotente."""
    global _REAPER
    with _TRAVA:
        if _REAPER is not None and _REAPER.vivo:
            return _REAPER
        deposito, _, _ = montar()
        _REAPER = Reaper(deposito, intervalo_s=intervalo_s).iniciar()
        return _REAPER


def parar_reaper() -> None:
    global _REAPER
    with _TRAVA:
        if _REAPER is not None:
            _REAPER.parar()
            _REAPER = None


def motores_disponiveis() -> list[dict[str, Any]]:
    """Quais motores esta maquina consegue rodar AGORA.

    Isto e diferente de `criativo_motor`, que diz quais motores existem no
    patrimonio. A tela precisa dos dois: um motor registrado que esta maquina nao
    consegue rodar nao pode oferecer botao de render.
    """
    _, operario, _ = montar()
    saida = []
    for slug, motor in sorted(operario.motores.items()):
        natureza = natureza_do_motor(motor)
        saida.append(
            {
                "slug": slug,
                "versao": getattr(motor, "versao", None),
                "versoes": motor.versoes_congeladas(),
                "produz": ["imagem"],
                # ⚠️ A tela precisa dos dois. Um motor cuja saida NAO e
                # publicavel nao pode oferecer botao de publicar, e derivar isso
                # do slug ("parece nome de motor local") seria uma heuristica
                # que envelhece mal.
                "natureza": natureza.value,
                "publicavel": natureza.publicavel,
            }
        )
    return saida


def natureza_do_motor(motor: Any) -> NaturezaDaProcedencia:
    """A natureza que o motor declara — e `NAO_DECLARADA` quando ele nao declara.

    ⚠️ Nunca `PRODUCAO` por omissao. Quem nao respondeu nao autorizou, e o erro
    caro tem uma direcao so: apresentar ensaio como producao. Uma declaracao em
    string solta tambem nao vale: ela parece resposta e nao e comparavel.
    """
    declarada = getattr(motor, "natureza", None)
    if isinstance(declarada, NaturezaDaProcedencia):
        return declarada
    return NaturezaDaProcedencia.NAO_DECLARADA


# ─────────────────────────────────────────────────────────────────────────────
# A produção local, ponta a ponta — o que a tela `/criativos` consome
# ─────────────────────────────────────────────────────────────────────────────
#
# ## Por que isto mora AQUI, e não num módulo novo
#
# Porque um segundo caminho seria a nona cópia do mesmo assunto. A bancada já
# tem fila durável, lease, batimento, reaper, gate bloqueante e recibo com
# assinatura determinista; a camada de criativo (`volc_ads/criativo/`) já tem
# régua por canal, medição a partir dos bytes, validação e a ponte até o
# contrato de campanha. O que faltava era alguém chamar as duas em ordem.
#
# ## As duas metades, e o que cada uma responde
#
#   bancada          "este trabalho existe, rodou, e aqui está o recibo"
#   criativo/ponte   "estes arquivos servem para o canal, e aqui está a linhagem"
#
# Elas se encontram num ponto só: os `Artefato` do recibo viram `Asset` medidos
# do DISCO — nunca do que o motor declarou — e seguem para a ponte.
#
# ## Nenhum caminho de disco no envelope
#
# `Artefato.caminho` existe e é lido aqui, e não sai daqui. `Operario.
# _mensagem_para_o_operador` já paga esse preço no tratamento de falha, pelo
# mesmo motivo: o operador não precisa do caminho e não deveria vê-lo.

from datetime import datetime, timezone  # noqa: E402

from volc_ads import criativo_ponte as _ponte  # noqa: E402
from volc_ads.criativo import producao as _producao  # noqa: E402
from volc_ads.criativo import requisitos as _requisitos  # noqa: E402
from volc_ads.criativo.adaptadores import medir_imagem as _medir  # noqa: E402
from volc_ads.criativo.contrato import (  # noqa: E402
    Asset as _Asset,
    LoteDeAssets as _LoteDeAssets,
    Origem as _Origem,
    Procedencia as _Procedencia,
    TipoDeAsset as _TipoDeAsset,
    hash_de_conteudo as _hash_de_conteudo,
)

from .adaptadores.png_local import SLUG as MOTOR_LOCAL_SLUG  # noqa: E402
from .contrato import Encomenda, EstadoDoTrabalho, SaidaPedida, TERMINAIS  # noqa: E402
from .despacho import DespachoIndisponivel, ambiente_atual, escolher_despachante  # noqa: E402

#: Cada canal tem uma porta na ponte, e a tabela é explícita. Um `getattr` por
#: nome de canal aceitaria qualquer string e falharia longe daqui.
_PORTA_DA_PONTE = {
    _producao.CANAL_DISPLAY: _ponte.imagens_de_display,
    _producao.CANAL_DEMAND_GEN: _ponte.imagens_de_demand_gen,
}

_DESTINOS = {d.value: d for d in _ponte.Destino}


def receitas_locais() -> list[dict[str, Any]]:
    """As receitas que ESTA máquina consegue produzir agora, offline.

    `saidas` é derivado da régua do canal (`criativo/requisitos.yaml`), não de
    uma lista escrita à mão: se o YAML mudar, a tela muda junto. Uma receita
    cujo canal não tem régua de arquivo não é listada — e não é escondida por
    engano: `exigencia_binaria_de` levanta com motivo, e a receita simplesmente
    não existe para esta máquina.
    """
    _, operario, _ = montar()
    motor = operario.motores.get(MOTOR_LOCAL_SLUG)
    natureza = natureza_do_motor(motor) if motor is not None else None

    saida: list[dict[str, Any]] = []
    for receita in _producao.RECEITAS:
        try:
            exigencia = _requisitos.exigencia_binaria_de(receita.canal)
        except ValueError:
            continue
        if receita.canal not in _PORTA_DA_PONTE:
            continue
        saida.append({
            "receita_id": receita.id,
            "canal": receita.canal,
            "rotulo": receita.rotulo,
            "motor_slug": MOTOR_LOCAL_SLUG,
            "disponivel": motor is not None,
            "natureza": natureza.value if natureza else None,
            "publicavel": bool(natureza and natureza.publicavel),
            "exigencia_fonte": exigencia.fonte or None,
            "exigencia_provisoria": exigencia.provisorio,
            "saidas": [
                {
                    "slot": s.slot,
                    "papel": _papel_de(receita.canal, _TipoDeAsset(s.slot.split("-", 1)[1])),
                    "tipo": s.slot.split("-", 1)[1],
                    "largura": s.largura,
                    "altura": s.altura,
                }
                for s in _saidas_da_receita(receita, exigencia)
            ],
        })
    return saida


def produzir_local(
    *,
    receita_id: str,
    tenant_id: str,
    insumo: str,
    intencao: str = "",
    seed: int = 0,
    destino: str = "ensaio",
) -> dict[str, Any]:
    """Enfileira e executa a receita, e devolve o envelope de `estado_da_producao`.

    ## Por que não levanta por entrada inválida

    Porque a rota teria de adivinhar o status HTTP a partir do texto da exceção.
    Receita desconhecida, insumo vazio, motor ausente e ambiente sem processo
    longo voltam como envelope com `erro` preenchido e `trabalho_id: None`. Erro
    de programador (assinatura errada) continua sendo `TypeError`, como deve ser.

    ## Por que consulta `escolher_despachante` antes de qualquer coisa

    Porque `despacho.py` é fail-closed por um motivo medido: numa função
    serverless, render dentro do request encontra o teto de tempo e um retry do
    cliente vira segunda produção. Chamar `DespachanteLocal` direto daqui
    contornaria essa fronteira em silêncio — a peça local é barata, mas o
    precedente não é.
    """
    if not str(tenant_id or "").strip():
        return _erro("tenant_vazio", "tenant_id é obrigatório: dois inquilinos "
                                     "com o mesmo pedido são dois trabalhos")
    if not str(insumo or "").strip():
        return _erro("insumo_vazio", "sem insumo não há do que gerar")
    if destino not in _DESTINOS:
        return _erro("destino_desconhecido",
                     f"destino {destino!r} não existe. Conhecidos: "
                     f"{', '.join(sorted(_DESTINOS))}")
    try:
        receita = _producao.receita_de(receita_id)
    except _producao.ReceitaDesconhecida as exc:
        return _erro("receita_desconhecida", str(exc.args[0]))
    try:
        exigencia = _requisitos.exigencia_binaria_de(receita.canal)
    except ValueError as exc:
        return _erro("canal_sem_regua", str(exc))

    try:
        escolher_despachante()
    except DespachoIndisponivel as exc:
        return _erro("ambiente_sem_processo_longo",
                     f"{exc.motivo} (ambiente: {exc.ambiente})")

    deposito, operario, despachante = montar()
    if MOTOR_LOCAL_SLUG not in operario.motores:
        return _erro("motor_indisponivel",
                     f"o motor {MOTOR_LOCAL_SLUG!r} não está registrado nesta "
                     f"máquina; nenhuma produção local é possível")

    encomenda = Encomenda(
        receita_id=receita.id,
        tenant_id=str(tenant_id),
        motor_slug=MOTOR_LOCAL_SLUG,
        modo_slug="ensaio-local",
        finalidade_slug=receita.canal.lower(),
        seed=int(seed),
        saidas=_saidas_da_receita(receita, exigencia),
        parametros={
            "insumo": str(insumo),
            "canal": receita.canal,
            "intencao": str(intencao or receita.id),
        },
    )
    trabalho, _criado = deposito.enfileirar(encomenda)
    # `_criado=False` não é erro: é a idempotência funcionando, e o despacho de
    # um trabalho que já saiu da fila é um no-op declarado em `DespachanteLocal`.
    despachante.despachar(trabalho.id)
    envelope = estado_da_producao(trabalho.id, tenant_id=str(tenant_id),
                                  destino=destino)
    assert envelope is not None  # acabamos de criá-lo com este tenant
    return envelope


def estado_da_producao(
    trabalho_id: str, *, tenant_id: str, destino: str = "ensaio"
) -> dict[str, Any] | None:
    """O envelope de uma produção, ou `None` quando ela não existe para o tenant.

    `None` quer dizer "não existe / não é seu" — a rota traduz para 404. Nunca
    quer dizer "existe e está vazio".
    """
    deposito, operario, _ = montar()
    trabalho = deposito.por_id(trabalho_id, tenant_id=tenant_id)
    if trabalho is None:
        return None
    return _envelope(trabalho, operario, destino=destino)


# ── construção do envelope ──────────────────────────────────────────────────


def _erro(codigo: str, mensagem: str) -> dict[str, Any]:
    """Envelope de pedido recusado — o desfecho em que nem trabalho existiu.

    ⚠️ Ele NÃO é um envelope de falha com campos a menos. `trabalho_id` é `None`
    e `estado` é `None`, e essas duas ausências são o que permite a tela dizer
    "seu pedido não foi aceito" em vez de "o render falhou". Colapsar os dois
    faria o operador procurar um defeito de produção que nunca aconteceu.
    """
    return {
        "trabalho_id": None,
        "estado": None,
        "terminal": False,
        "assets": [],
        "entrega": None,
        "recibo": None,
        "falha": None,
        "erro": {"codigo": codigo, "mensagem": mensagem},
    }


def _saidas_da_receita(receita, exigencia) -> tuple[SaidaPedida, ...]:
    """Uma saída por papel que a régua exige, com a geometria que ela declara.

    O `slot` é `"<ordem>-<tipo>"`. A ordem entra no nome porque uma receita pode
    pedir dois do mesmo papel, e dois slots iguais na mesma encomenda fariam o
    motor escrever no mesmo arquivo — o segundo apagando o primeiro, com o
    `cobertura_dos_slots` reprovando um pedido que na verdade foi atendido.
    """
    from volc_ads.criativo.adaptadores.png_local import dimensao_para

    saidas: list[SaidaPedida] = []
    for ordem, tipo in enumerate(_producao.papeis_da_receita(receita, exigencia)):
        largura, altura = dimensao_para(exigencia.de(tipo), tipo)
        saidas.append(SaidaPedida(
            slot=f"{ordem}-{tipo.value}",
            largura=largura,
            altura=altura,
            midia="imagem",
            mime="image/png",
        ))
    return tuple(saidas)


def _papel_de(canal: str, tipo: _TipoDeAsset) -> str | None:
    tabela = (
        _ponte.PAPEL_POR_TIPO_DEMAND_GEN
        if canal == _producao.CANAL_DEMAND_GEN
        else _ponte.PAPEL_POR_TIPO
    )
    return tabela.get(tipo)


def _instante(iso: str | None) -> datetime:
    """ISO-8601 → `datetime`. Sem relógio: quando o recibo não diz, `quando` é
    o epoch, e o `nota` da procedência declara isso. `datetime.now()` aqui
    inventaria um instante que ninguém apurou."""
    if iso:
        try:
            return datetime.fromisoformat(iso)
        except ValueError:
            pass
    return datetime.fromtimestamp(0, tz=timezone.utc)


def _assets_do_recibo(trabalho, motor) -> tuple[
    tuple[_Asset, ...], dict[str, bytes], tuple[str, ...]
]:
    """Os `Artefato` do recibo viram `Asset` medidos DO DISCO.

    ⚠️ A medida sai dos bytes lidos agora, e não dos campos do `Artefato`. O
    operário já conferiu bytes e hash contra o disco antes de gravar o recibo —
    mas o arquivo pode ter sumido depois, e um `Asset` construído a partir da
    declaração descreveria um arquivo que não existe mais. Aqui a ausência vira
    recusa nomeada, nunca um asset fantasma.
    """
    recibo = trabalho.recibo or {}
    parametros = trabalho.encomenda.parametros
    natureza = natureza_do_motor(motor)
    quando = _instante(recibo.get("terminado_em"))

    assets: list[_Asset] = []
    conteudo: dict[str, bytes] = {}
    perdidos: list[str] = []

    for artefato in recibo.get("artefatos") or []:
        slot = str(artefato.get("slot") or "")
        try:
            tipo = _TipoDeAsset(slot.split("-", 1)[1])
        except (IndexError, ValueError):
            perdidos.append(f"{slot}: slot fora do vocabulário de TipoDeAsset")
            continue
        try:
            dados = Path(str(artefato.get("caminho"))).read_bytes()
        except OSError as exc:
            perdidos.append(
                f"{slot}: o recibo aponta um arquivo que não pôde ser lido "
                f"({exc.__class__.__name__}) — asset não persistido não é asset "
                f"disponível"
            )
            continue

        medida = _medir.medir(dados)
        try:
            asset = _Asset(
                tipo=tipo,
                procedencia=_Procedencia(
                    motor=recibo.get("motor_slug") or MOTOR_LOCAL_SLUG,
                    versao_do_motor=recibo.get("motor_versao") or "",
                    insumo=str(parametros.get("insumo") or ""),
                    quando=quando,
                    pedido=trabalho.id,
                    custo_usd=recibo.get("custo_real_usd"),
                    nota=(
                        "`quando` é o `terminado_em` do recibo da bancada, não "
                        "um relógio lido aqui"
                    ),
                    natureza=natureza,
                ),
                conteudo_hash=_hash_de_conteudo(dados),
                origem=_Origem.GERADO,
                bytes_totais=medida.bytes_totais,
                mime=medida.mime,
                largura=medida.largura,
                altura=medida.altura,
                rotulo=slot,
            )
        except ValueError as exc:
            perdidos.append(f"{slot}: artefato não virou asset: {exc}")
            continue
        assets.append(asset)
        conteudo[asset.identidade] = dados

    return tuple(assets), conteudo, tuple(perdidos)


def _envelope(trabalho, operario, *, destino: str) -> dict[str, Any]:
    motor = operario.motores.get(trabalho.encomenda.motor_slug)
    natureza = natureza_do_motor(motor) if motor is not None else None
    recibo = trabalho.recibo or None
    parametros = trabalho.encomenda.parametros

    assets: tuple[_Asset, ...] = ()
    conteudo: dict[str, bytes] = {}
    perdidos: tuple[str, ...] = ()
    if trabalho.estado is EstadoDoTrabalho.RENDERED:
        assets, conteudo, perdidos = _assets_do_recibo(trabalho, motor)

    canal = str(parametros.get("canal") or "")
    envelope: dict[str, Any] = {
        "trabalho_id": trabalho.id,
        "tenant_id": trabalho.tenant_id,
        "receita_id": trabalho.encomenda.receita_id,
        "canal": canal or None,
        "intencao": parametros.get("intencao") or None,
        # ⚠️ O texto do briefing NAO sai pelo envelope. Estado e impressao
        # digital bastam para a tela dizer "houve insumo" sem devolve-lo.
        "insumo": fronteira_publica.resumo_do_insumo(parametros.get("insumo")),
        "seed": trabalho.encomenda.seed,
        "chave_de_idempotencia": trabalho.chave_idempotencia,
        "estado": trabalho.estado.value,
        "terminal": trabalho.estado in TERMINAIS,
        "tentativa": trabalho.tentativa,
        "max_tentativas": trabalho.max_tentativas,
        "criado_em": trabalho.criado_em.isoformat() if trabalho.criado_em else None,
        "motor": {
            "slug": trabalho.encomenda.motor_slug,
            "versao": getattr(motor, "versao", None),
            "natureza": natureza.value if natureza else None,
            "publicavel": bool(natureza and natureza.publicavel),
            "versoes": motor.versoes_congeladas() if motor is not None else None,
        },
        "falha": trabalho.falha,
        "erro": None,
        "recibo": recibo,
        "assinatura_determinista": (recibo or {}).get("assinatura_determinista"),
        "assets": [_asset_para_json(a, canal) for a in assets],
        # ⚠️ `None` enquanto a entrega não foi TENTADA. Um `{"ok": false}` aqui
        # diria que a ponte reprovou um lote que ela nunca viu, e a tela pintaria
        # de vermelho um trabalho que só está na fila.
        "entrega": None,
        "artefatos_perdidos": list(perdidos),
    }

    porta = _PORTA_DA_PONTE.get(canal)
    if trabalho.estado is EstadoDoTrabalho.RENDERED and porta is not None:
        envelope["entrega"] = _entrega_para_json(
            porta(
                _LoteDeAssets(
                    canal=canal,
                    assets=assets,
                    intencao=str(parametros.get("intencao") or ""),
                ),
                conteudo,
                destino=_DESTINOS[destino],
            ),
            destino=destino,
        )
    return envelope


def _asset_para_json(asset: _Asset, canal: str) -> dict[str, Any]:
    p = asset.procedencia
    return {
        "identidade": asset.identidade,
        "conteudo_hash": asset.conteudo_hash,
        "slot": asset.rotulo,
        "papel": _papel_de(canal, asset.tipo),
        "tipo": asset.tipo.value,
        "mime": asset.mime,
        "largura": asset.largura,
        "altura": asset.altura,
        "bytes_totais": asset.bytes_totais,
        "natureza": p.natureza.value,
        "publicavel": p.publicavel,
        "origem": asset.origem.value,
        "procedencia": {
            "motor": p.motor,
            "versao_do_motor": p.versao_do_motor,
            # Mesma fronteira da linha do envelope: a procedencia identifica
            # o insumo, nao o transcreve.
            "insumo": fronteira_publica.resumo_do_insumo(p.insumo),
            "insumo_hash": p.insumo_hash,
            "pedido": p.pedido,
            "quando": p.quando.isoformat(),
            # `None`, nunca `0.0`: o motor local não custa dinheiro e ainda
            # assim não afirma que a imagem saiu de graça.
            "custo_usd": p.custo_usd,
            "nota": p.nota,
        },
    }


def _entrega_para_json(entrega, *, destino: str) -> dict[str, Any]:
    v = entrega.veredito
    return {
        "tentada": True,
        "destino": destino,
        "ok": entrega.ok,
        "canal": v.canal,
        "veredito": {
            # ⚠️ Duas perguntas diferentes, e a tela precisa das duas: `ok` aqui
            # é "os arquivos são bons"; `ok` acima é "há payload montável". Um
            # lote aprovado cujos bytes a ponte recusou tem o primeiro `True` e
            # o segundo `False`, e o motivo está em `recusas`.
            "ok": v.ok,
            "aprovados": len(v.aprovados),
            "reprovados": len(v.reprovados),
            "provisorio": v.provisorio,
            "fonte": v.fonte or None,
            "violacoes": [str(x) for x in v.violacoes],
        },
        "linhagem": [ln.para_json() for ln in entrega.linhagem],
        "recusas": list(entrega.recusas),
        "avisos": list(entrega.avisos),
        "naturezas": dict(entrega.naturezas),
    }


def ambiente_da_bancada() -> dict[str, Any]:
    """Onde esta bancada está rodando, e se ela pode produzir dentro do request.

    A tela precisa disto para não oferecer um botão que a fronteira de despacho
    vai recusar. `duravel=False` é dito em voz alta: o despachante local não
    sobrevive à morte do processo.
    """
    try:
        despachante = escolher_despachante()
    except DespachoIndisponivel as exc:
        return {
            "ambiente": exc.ambiente,
            "pode_produzir": False,
            "motivo": exc.motivo,
            "despachante": None,
            "duravel": False,
            "sincrono": None,
        }
    return {
        "ambiente": ambiente_atual(),
        "pode_produzir": True,
        "motivo": None,
        "despachante": despachante.nome,
        "duravel": despachante.duravel,
        "sincrono": despachante.sincrono,
    }
