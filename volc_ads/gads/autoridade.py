"""A autoridade única de NASCIMENTO de campanha — a capacidade, não o conselho.

## Por que este módulo existe

Até 03/09/2026 os portões do nascimento moravam todos na rota
`POST /api/trafego/subir`: escopo da conta, canário, destino pago com recibo
vigente, conjunto de keywords aprovado e selado, plano de mensuração, portão de
lance, idempotência remota e ledger com recibo `em_voo` antes da rede. A rota
faz tudo isso, e faz bem.

O problema é que nada disso era exigido pelo **executor**. `volc_ads.subir.subir`
é uma função pública, importável de qualquer lugar do processo, e cobrava quatro
portas: selo, canal, motivo e trava. Reproduzido com adapter falso e contador em
03/09/2026 (`docs/closure/hermes-p09-t17-campaign-birth-authority-v1/contraprova-vermelha-bypass.py`):

    conta 9999999999 · MCC 1111111111 · status ENABLED no payload
    ledger AUSENTE · identidade AUSENTE · destino AUSENTE · conjunto AUSENTE
    validate_only NUNCA rodado (o `Selo` foi forjado com a função pública que o
    próprio executor reconfere)
    → chamadas no adapter: 1 · recibo: ACEITO

Ou seja: os portões da rota eram **convenções da rota**, e não propriedades de
quem escreve. Qualquer módulo, script, worker, rota nova ou produtor n8n que
importasse o executor nascia com a capacidade de criar campanha em qualquer
conta, com qualquer verba, sem recibo.

Este módulo troca isso por uma **capacidade**: escrever exige uma
`Autorizacao` assinada, e emiti-la exige nomear cada prova. A ausência de uma
prova não é neutra — é recusa.

## O que a assinatura consegue, e o que ela não consegue

O segredo do HMAC é gerado no import, por processo, e nunca sai daqui. Isso
compra três coisas concretas:

1. uma `Autorizacao` **não pode ser construída à mão** e passar: sem
   `emitir()`, `assinatura` não confere;
2. uma `Autorizacao` **não pode ser reaproveitada** de um log, arquivo, fila ou
   corpo HTTP: o segredo morre com o processo;
3. uma `Autorizacao` **vale uma vez só** (`exigir_e_consumir`), então repetir a
   mesma autorização — por retry cego, por timeout, por replay — não cria a
   segunda campanha.

O que ela **não** consegue, e é preciso dizer: dentro do mesmo processo, quem lê
este arquivo pode chamar `emitir()` com strings inventadas. Nenhuma criptografia
in-process resolve isso. O que fecha esse resto é estrutural e está fora daqui:
`scripts/gate_autoridade_de_nascimento.py` derruba o build se qualquer arquivo
de produção fora da allowlist canônica referenciar `emitir`, `mutar` ou
`subir.subir`. A garantia honesta é: **nenhum caminho novo alcança a escrita por
acidente, e um caminho novo deliberado é uma falha de gate, não uma descoberta
de auditoria.**
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from typing import Any

#: O único emissor legítimo. Não é enfeite de log: `emitir()` recusa qualquer
#: outro valor, então um produtor alternativo que queira escrever precisa
#: MENTIR explicitamente sobre quem é — e a mentira fica no ledger, ao lado do
#: recibo, onde a reconciliação a encontra.
AUTORIDADE_CANONICA = "http:POST /api/trafego/subir"

#: Campanha nasce PAUSED, sempre. Não há valor alternativo aceito, e isso é o
#: portão — não a boa vontade de `campanha/comum.py`, que é onde o literal
#: mora hoje e que um payload montado à mão não atravessa.
ESTADO_INICIAL_PERMITIDO = "PAUSED"

#: Os canais que podem NASCER. Vista literal de propósito: importar
#: `campanha.perfil` daqui fecharia um ciclo (`campanha` já importa `gads`).
#: `volc_ads/subir.py` derruba o import se esta lista divergir do perfil.
CANAIS_QUE_NASCEM = frozenset({"SEARCH", "DISPLAY"})

#: O vocabulário FECHADO do veredito de mensuração. Espelha
#: `app.trafego.prontidao.ESTADOS`; um veredito fora dele é recusa, porque um
#: estado que esta camada não sabe classificar não pode ser lido como permissão.
VEREDITOS_DE_MENSURACAO = frozenset({
    "PRONTO", "PARCIAL", "NAO_PRONTO", "INDETERMINADO", "NAO_APLICAVEL",
})

#: As estratégias que NÃO aprendem de conversão e por isso não dependem da
#: medição. Espelha `app.trafego.prontidao.ESTRATEGIAS_SEM_APRENDIZADO`, e a
#: igualdade é guardada por
#: `backend/tests/test_p09_t17_autoridade_de_nascimento.py`: uma guarda que
#: discorda da guarda que ela replica é pior que nenhuma.
ESTRATEGIAS_SEM_MENSURACAO = frozenset({"MANUAL_CPC"})

_SO_DIGITOS = re.compile(r"^[0-9]{6,}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

#: Segredo do processo. `token_bytes` e não uma constante: uma chave literal no
#: arquivo tornaria a assinatura reproduzível por quem lê o repositório, e uma
#: assinatura reproduzível fora do processo é uma assinatura que não assina.
_SEGREDO = secrets.token_bytes(32)

_TRAVA = threading.Lock()
_CONSUMIDAS: set[str] = set()

#: Versão do material assinado. Muda quando um campo entra ou sai, para que uma
#: `Autorizacao` de outra safra não confira por coincidência de campos.
VERSAO_MATERIAL = "volc.nascimento.autorizacao.v1"


class AutorizacaoInvalida(RuntimeError):
    """A autorização apresentada não autoriza esta escrita."""


class AutorizacaoAusente(AutorizacaoInvalida):
    """Nenhuma autorização foi apresentada. Ausência não é aprovação."""


class AutorizacaoJaUsada(AutorizacaoInvalida):
    """Esta autorização já escreveu. Repetir não cria a segunda campanha."""


#: A frase que toda recusa desta camada carrega. Ela não é cortesia: quem lê a
#: recusa precisa saber, na mesma linha, se ainda existe alguma coisa na conta
#: para conferir. "Faltou o recibo" sem ela deixa a pergunta aberta.
NADA_FOI_ENVIADO = "Nada foi enviado ao Google."


class EmissaoRecusada(ValueError):
    """Faltou prova para emitir. A recusa nomeia qual.

    ⚠️ A garantia de que TODA recusa afirma "nada foi enviado" mora aqui, e não
    em cada `raise`. Doze cópias da mesma frase é como uma delas fica de fora —
    e foi exatamente o que a contraprova de emissão pegou na primeira execução:
    oito das trinta e quatro recusas não diziam.
    """

    def __init__(self, mensagem: str):
        texto = str(mensagem).strip()
        if "Google" not in texto:
            texto = f"{texto} {NADA_FOI_ENVIADO}"
        super().__init__(texto)


@dataclass(frozen=True)
class Autorizacao:
    """A capacidade de criar UMA campanha, nesta conta, com ESTE payload.

    Frozen e assinada: mexer em qualquer campo depois de emitida invalida a
    assinatura, então `replace()` produz um objeto que não escreve. É a mesma
    doutrina do `Selo` — só que o `Selo` prova o PAYLOAD e esta prova a
    AUTORIDADE.
    """

    autoridade: str
    conta: str
    mcc: str
    canal: str
    plano_impressao: str
    estado_inicial: str
    #: O recibo `em_voo` que já existe no ledger quando isto é emitido.
    recibo_id: str
    item_id: str
    idempotency_key: str
    #: Quem autorizou, de verdade — não o processo, a pessoa.
    aprovador_sub: str
    aprovador_email: str
    #: O destino pago aprovado, e a impressão do veredito que o aprovou.
    destino_url: str
    destino_recibo: str
    #: O conjunto de keywords positivas aprovado e selado, e quem o selou.
    conjunto_pago_autoridade: str
    conjunto_pago_impressao: str
    #: A mensuração medida e a estratégia que ela precisa sustentar.
    estrategia_lance: str
    mensuracao_veredito: str
    #: Os limites aprovados, em micros — a unidade que o Google usa.
    orcamento_diario_micros: int
    cpc_micros: int
    motivo: str
    emitida_em: str
    assinatura: str = ""

    def resumo(self) -> str:
        """O que pode aparecer em log e em recibo. Sem assinatura, sem e-mail."""
        return (
            f"{self.autoridade} · conta {self.conta} sob MCC {self.mcc} · "
            f"{self.canal} · plano {self.plano_impressao[:12]} · "
            f"recibo {self.recibo_id} · nasce {self.estado_inicial}"
        )

    def para_json(self) -> dict:
        """Projeção para o recibo. A ASSINATURA NÃO VAI, e isso é o ponto.

        Vazar a assinatura num recibo, log ou resposta HTTP daria a quem a lesse
        uma autorização reaproveitável enquanto o processo vivesse. O que
        interessa a quem audita é o conteúdo — e ele está todo aqui.
        """
        d = asdict(self)
        d.pop("assinatura", None)
        return d


def _material(a: Autorizacao) -> bytes:
    d = asdict(a)
    d.pop("assinatura", None)
    d["_versao"] = VERSAO_MATERIAL
    return json.dumps(
        d, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _assinar(a: Autorizacao) -> str:
    return hmac.new(_SEGREDO, _material(a), hashlib.sha256).hexdigest()


def _texto(valor, campo: str) -> str:
    v = str(valor or "").strip()
    if not v:
        raise EmissaoRecusada(
            f"{campo} está ausente ou vazio. Emitir autorização com {campo} em "
            "branco seria tratar ausência de prova como prova — nada foi "
            "enviado ao Google."
        )
    return v


def _inteiro(valor, campo: str, *, minimo: int) -> int:
    try:
        n = int(valor)
    except (TypeError, ValueError) as exc:
        raise EmissaoRecusada(
            f"{campo} não é um inteiro de micros: {valor!r}. Nada foi enviado "
            "ao Google."
        ) from exc
    if n < minimo:
        raise EmissaoRecusada(
            f"{campo} = {n} micros é menor que o mínimo aceito ({minimo}). "
            "Nada foi enviado ao Google."
        )
    return n


def emitir(
    *,
    autoridade: str,
    conta: str,
    mcc: str,
    canal: str,
    plano_impressao: str,
    recibo_id: str,
    item_id: str,
    idempotency_key: str,
    aprovador_sub: str,
    aprovador_email: str,
    destino_url: str,
    destino_recibo: str,
    conjunto_pago_autoridade: str,
    conjunto_pago_impressao: str,
    estrategia_lance: str,
    mensuracao_veredito: str,
    orcamento_diario_micros,
    cpc_micros,
    motivo: str,
    estado_inicial: str = ESTADO_INICIAL_PERMITIDO,
) -> Autorizacao:
    """Emite a capacidade de escrever, e recusa nomeando a prova que falta.

    Só a rota canônica chama isto — `scripts/gate_autoridade_de_nascimento.py`
    derruba o build se outro arquivo de produção o referenciar.
    """
    quem = _texto(autoridade, "autoridade")
    if quem != AUTORIDADE_CANONICA:
        raise EmissaoRecusada(
            f"{quem!r} não é a autoridade canônica de nascimento "
            f"({AUTORIDADE_CANONICA!r}). Este sistema tem UMA porta de criação "
            "de campanha; uma segunda autoridade paralela é exatamente o que "
            "P09-T17 fechou. Nada foi enviado ao Google."
        )

    estado = _texto(estado_inicial, "estado_inicial").upper()
    if estado != ESTADO_INICIAL_PERMITIDO:
        raise EmissaoRecusada(
            f"estado inicial {estado!r} não é aceito: campanha nasce "
            f"{ESTADO_INICIAL_PERMITIDO}, sempre. Ativar é outro ato, com outra "
            "autorização, e ele não existe neste fluxo. Nada foi enviado ao "
            "Google."
        )

    canal_normal = _texto(canal, "canal").upper()
    if canal_normal not in CANAIS_QUE_NASCEM:
        raise EmissaoRecusada(
            f"{canal_normal} não é um canal que nasce por esta autoridade "
            f"(nascem: {', '.join(sorted(CANAIS_QUE_NASCEM))}). Reconhecer um "
            "canal no inventário nunca autorizou criá-lo. Nada foi enviado ao "
            "Google."
        )

    conta_normal = _texto(conta, "conta")
    mcc_normal = _texto(mcc, "mcc")
    for rotulo, valor in (("conta", conta_normal), ("mcc", mcc_normal)):
        if not _SO_DIGITOS.fullmatch(valor):
            raise EmissaoRecusada(
                f"{rotulo} {valor!r} não é um customer id de dígitos. Uma "
                "identidade de conta ambígua morre aqui, antes da rede."
            )

    impressao = _texto(plano_impressao, "plano_impressao").lower()
    if not _SHA256.fullmatch(impressao):
        raise EmissaoRecusada(
            "plano_impressao não é um sha256 de 64 hex. A autorização precisa "
            "apontar EXATAMENTE o payload aprovado; sem isso ela autorizaria "
            "qualquer coisa."
        )

    conjunto_impressao = _texto(conjunto_pago_impressao, "conjunto_pago_impressao").lower()
    if not _SHA256.fullmatch(conjunto_impressao):
        raise EmissaoRecusada(
            "conjunto_pago_impressao não é um sha256 de 64 hex. Sem o selo do "
            "conjunto aprovado não há como dizer QUAIS keywords foram "
            "autorizadas."
        )

    destino = _texto(destino_url, "destino_url")
    if not destino.lower().startswith("https://"):
        raise EmissaoRecusada(
            f"destino {destino!r} não é HTTPS. O destino pago aprovado é parte "
            "da autorização, e um destino que não se sabe ler não foi aprovado."
        )

    veredito = _texto(mensuracao_veredito, "mensuracao_veredito").upper()
    if veredito not in VEREDITOS_DE_MENSURACAO:
        raise EmissaoRecusada(
            f"veredito de mensuração {veredito!r} está fora do vocabulário "
            f"conhecido ({', '.join(sorted(VEREDITOS_DE_MENSURACAO))}). Um "
            "estado que esta camada não sabe classificar não pode ser lido "
            "como permissão."
        )

    estrategia = _texto(estrategia_lance, "estrategia_lance").upper()
    # ⚠️ A REGRA REPETE `prontidao.exigir_para_criacao` DE PROPÓSITO, e a
    # repetição só se paga porque é FIEL: `ESTRATEGIAS_SEM_MENSURACAO` é
    # comparada com `prontidao.ESTRATEGIAS_SEM_APRENDIZADO` por teste. Sem esta
    # linha, a coerência entre lance e medição continuaria sendo uma propriedade
    # da rota — e a rota é justamente o que esta autorização deixa de assumir.
    if estrategia not in ESTRATEGIAS_SEM_MENSURACAO and veredito != "PRONTO":
        raise EmissaoRecusada(
            f"{estrategia} aprende de conversão e a mensuração está "
            f"{veredito}. Nascer aprendendo o que ninguém mede gasta o "
            "orçamento inteiro descobrindo que não há sinal. Suba em "
            f"{'/'.join(sorted(ESTRATEGIAS_SEM_MENSURACAO))} ou conserte a "
            "medição. Nada foi enviado ao Google."
        )

    autorizacao = Autorizacao(
        autoridade=quem,
        conta=conta_normal,
        mcc=mcc_normal,
        canal=canal_normal,
        plano_impressao=impressao,
        estado_inicial=estado,
        recibo_id=_texto(recibo_id, "recibo_id"),
        item_id=_texto(item_id, "item_id"),
        idempotency_key=_texto(idempotency_key, "idempotency_key"),
        aprovador_sub=_texto(aprovador_sub, "aprovador_sub"),
        aprovador_email=_texto(aprovador_email, "aprovador_email"),
        destino_url=destino,
        destino_recibo=_texto(destino_recibo, "destino_recibo"),
        conjunto_pago_autoridade=_texto(
            conjunto_pago_autoridade, "conjunto_pago_autoridade"),
        conjunto_pago_impressao=conjunto_impressao,
        estrategia_lance=estrategia,
        mensuracao_veredito=veredito,
        orcamento_diario_micros=_inteiro(
            orcamento_diario_micros, "orcamento_diario_micros", minimo=1),
        cpc_micros=_inteiro(cpc_micros, "cpc_micros", minimo=0),
        motivo=_motivo(motivo),
        emitida_em=datetime.now(timezone.utc).isoformat(),
    )
    return replace(autorizacao, assinatura=_assinar(autorizacao))


def _motivo(valor: str) -> str:
    motivo = str(valor or "").strip()
    if len(motivo) < 10:
        raise EmissaoRecusada(
            "o motivo da autorização precisa ter ao menos 10 caracteres além "
            "de espaços. Ele vai para o recibo e é a única explicação que "
            "sobra quando alguém pergunta, semanas depois, por que essa "
            "campanha existe."
        )
    return motivo


def _conferir_assinatura(autorizacao) -> Autorizacao:
    if autorizacao is None:
        raise AutorizacaoAusente(
            "esta escrita não apresentou autorização de nascimento. A criação "
            "de campanha passa exclusivamente pela autoridade canônica "
            f"({AUTORIDADE_CANONICA}), que é quem emite a autorização. "
            "Ausência de autorização nunca foi permissão — nada foi enviado ao "
            "Google."
        )
    if not isinstance(autorizacao, Autorizacao):
        raise AutorizacaoInvalida(
            f"{type(autorizacao).__name__} não é uma Autorizacao de "
            "nascimento. Um objeto parecido não autoriza: nada foi enviado ao "
            "Google."
        )
    esperada = _assinar(autorizacao)
    if not autorizacao.assinatura or not hmac.compare_digest(
            str(autorizacao.assinatura), esperada):
        raise AutorizacaoInvalida(
            "a assinatura da autorização não confere. Ou ela foi construída à "
            "mão, ou algum campo mudou depois da emissão, ou ela vem de outro "
            "processo — e nos três casos ela não descreve esta escrita. Nada "
            "foi enviado ao Google."
        )
    return autorizacao


def _bytes_da_operacao(op: Any) -> bytes:
    alvo = getattr(op, "_pb", op)
    serializar = getattr(alvo, "SerializeToString", None)
    if serializar is not None:
        try:
            return serializar(deterministic=True)
        except TypeError:
            return serializar()
    return repr(op).encode("utf-8", "replace")


def tipo_da_operacao(op: Any) -> str:
    """Tipo externo + verbo interno, ambos vindos dos oneofs do proto."""
    externo = qual_oneof(op, "operation")
    if not externo:
        raise AutorizacaoInvalida(
            "MutateOperation sem ramo do oneof `operation`. Nada foi enviado ao Google."
        )
    interna = getattr(op, externo, None)
    verbo = qual_oneof(interna, "operation") if interna is not None else ""
    if not verbo:
        raise AutorizacaoInvalida(
            f"{externo} sem create/update/remove selecionado. Nada foi enviado ao Google."
        )
    return f"{externo}.{verbo}"


def _hash_da_operacao(op: Any) -> str:
    return hashlib.sha256(_bytes_da_operacao(op)).hexdigest()


def impressao_das_operacoes(operacoes) -> str:
    """sha256 canônico do tipo + conteúdo de cada operação, em ordem.

    Esta função mora na autoridade, e não só no executor, porque o writer direto
    recebe `operacoes`. Se ele apenas aceitasse uma `plano_impressao` declarada
    pelo chamador, compararia a autorização contra uma string escolhida pelo
    próprio atacante. Aqui a fronteira recalcula a impressão dos bytes que vão
    para o request antes de consumir a capacidade.
    """
    ops = tuple(operacoes)
    if not ops:
        raise AutorizacaoInvalida(
            "grafo sem operações não tem plano autorizado. Nada foi enviado ao Google."
        )
    tipos = tuple(tipo_da_operacao(op) for op in ops)
    hashes = tuple(_hash_da_operacao(op) for op in ops)
    material = {
        "versao": "volc.google_ads.operacoes.v2",
        "operacoes": [
            {"indice": i, "tipo": tipo, "sha256": resumo}
            for i, (tipo, resumo) in enumerate(zip(tipos, hashes))
        ],
    }
    bruto = json.dumps(
        material, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(bruto).hexdigest()


def conferir(
    autorizacao,
    *,
    conta: str,
    mcc: str,
    canal: str,
    plano_impressao: str,
) -> Autorizacao:
    """Verifica sem consumir. Levanta `AutorizacaoInvalida` ao menor desencaixe.

    Quem consome é `exigir_e_consumir`, na fronteira de escrita. Separar as duas
    deixa o executor conferir cedo — antes de gravar pré-recibo e antes de abrir
    a trava — sem queimar a autorização num caminho que ainda pode recusar.
    """
    a = _conferir_assinatura(autorizacao)

    for rotulo, autorizado, pedido in (
        ("conta", a.conta, str(conta or "").strip()),
        ("MCC", a.mcc, str(mcc or "").strip()),
        ("canal", a.canal, str(canal or "").strip().upper()),
        ("plano", a.plano_impressao, str(plano_impressao or "").strip().lower()),
    ):
        if autorizado != pedido:
            raise AutorizacaoInvalida(
                f"a autorização é para {rotulo} {autorizado!r} e esta escrita "
                f"pede {pedido!r}. Uma autorização não migra de conta, de MCC, "
                "de canal nem de plano. Nada foi enviado ao Google."
            )

    if a.estado_inicial != ESTADO_INICIAL_PERMITIDO:
        raise AutorizacaoInvalida(
            f"a autorização declara estado inicial {a.estado_inicial!r}; só "
            f"{ESTADO_INICIAL_PERMITIDO} nasce por aqui. Nada foi enviado ao "
            "Google."
        )
    with _TRAVA:
        ja_usada = a.assinatura in _CONSUMIDAS
    if ja_usada:
        raise AutorizacaoJaUsada(
            f"a autorização do recibo {a.recibo_id} já foi usada para escrever. "
            "Repetir a mesma autorização não cria a segunda campanha: peça uma "
            "nova pela autoridade canônica, depois de reconciliar. Nada foi "
            "enviado ao Google."
        )
    return a


def exigir_e_consumir(
    autorizacao,
    *,
    conta: str,
    mcc: str,
    canal: str,
    plano_impressao: str,
) -> Autorizacao:
    """A fronteira. Confere e QUEIMA a autorização, atomicamente.

    ⚠️ O consumo acontece ANTES de a requisição partir, e é assim que ele
    protege: se marcássemos depois, um timeout deixaria a autorização válida e
    um retry cego criaria a segunda campanha — exatamente o desfecho que
    `INDETERMINADO` existe para não deixar acontecer em silêncio.
    """
    a = conferir(
        autorizacao, conta=conta, mcc=mcc, canal=canal,
        plano_impressao=plano_impressao,
    )
    with _TRAVA:
        if a.assinatura in _CONSUMIDAS:
            raise AutorizacaoJaUsada(
                f"a autorização do recibo {a.recibo_id} foi consumida por outra "
                "chamada concorrente. Nada foi enviado ao Google por esta."
            )
        _CONSUMIDAS.add(a.assinatura)
    return a


# ── o estado inicial, lido do PAYLOAD e não do rótulo ──────────────────────


class NascimentoAtivo(AutorizacaoInvalida):
    """O payload manda a campanha nascer fora de `PAUSED`."""


def qual_oneof(mensagem, nome: str) -> str:
    """`WhichOneof` mora no pb2; proto-plus o esconde atrás de `_pb`.

    As duas formas aparecem de verdade: o objeto devolvido por
    `client.get_type()` responde direto, e o que sai de dentro de um campo
    repetido às vezes vem embrulhado. Tentar as duas custa nada e evita um
    `AttributeError` no meio do único caminho que escreve.

    Vive aqui, e não em `subir.py`, porque agora são DOIS leitores de payload
    na fronteira de escrita — o executor e a capacidade — e duas cópias de um
    leitor de oneof é como uma delas passa a aceitar o que a outra recusa.
    """
    for alvo in (mensagem, getattr(mensagem, "_pb", None)):
        which = getattr(alvo, "WhichOneof", None)
        if which is None:
            continue
        try:
            campo = which(nome)
        except Exception:  # noqa: BLE001 — objeto sem esse oneof
            continue
        if campo:
            return str(campo)
    return ""


def _nome_do_enum(mensagem, campo: str) -> str:
    """O nome do enum, pelo descriptor do proto — nunca por tabela copiada.

    Com ``use_proto_plus=True`` o campo costuma voltar como Enum; com o cliente
    real usado pelo harness v25 ele pode voltar como inteiro. A tradução sai do
    descriptor do próprio proto, que é a única autoridade que não desatualiza.
    """
    valor = getattr(mensagem, campo, None)
    nome = str(getattr(valor, "name", "") or "").strip().upper()
    if nome:
        return nome
    pb = getattr(mensagem, "_pb", mensagem)
    descritor = getattr(pb, "DESCRIPTOR", None)
    definicao = (descritor.fields_by_name.get(campo)
                 if descritor is not None else None)
    enum_descritor = getattr(definicao, "enum_type", None)
    try:
        numero = int(getattr(pb, campo))
    except (AttributeError, TypeError, ValueError):
        return ""
    item = (enum_descritor.values_by_number.get(numero)
            if enum_descritor is not None else None)
    return str(getattr(item, "name", "") or "").strip().upper()


def estados_de_nascimento(operacoes) -> tuple[str, ...]:
    """O `status` de cada `campaign_operation.create` do lote, lido do payload.

    Devolve string vazia na posição em que o status não é legível — e quem
    chama trata vazio como recusa, nunca como PAUSED.
    """
    saida: list[str] = []
    for op in operacoes:
        if qual_oneof(op, "operation") != "campaign_operation":
            continue
        if qual_oneof(op.campaign_operation, "operation") != "create":
            continue
        saida.append(_nome_do_enum(op.campaign_operation.create, "status"))
    return tuple(saida)


def exigir_nascimento_pausado(operacoes) -> None:
    """Recusa o lote cujo payload não manda a campanha nascer PAUSED.

    ⚠️ Esta é a única guarda de estado inicial que NÃO depende de quem monta o
    payload. `campanha/comum.py` põe `PAUSED` por literal, e isso é bom — mas é
    uma propriedade do construtor, e o construtor não é o único jeito de chegar
    a um `MutateOperation`. A contraprova vermelha de P09-T17 montou o payload à
    mão com `status = ENABLED` e o executor não olhou.

    ⚠️ `UNSPECIFIED`/ilegível é RECUSA, não PAUSED. `status` ausente num create
    deixa o default para a plataforma decidir, e "a plataforma decide" é o
    oposto de "nasce pausada".
    """
    estados = estados_de_nascimento(operacoes)
    if not estados:
        raise NascimentoAtivo(
            "o lote não tem nenhuma `campaign_operation.create` com status "
            "legível. Uma escrita autorizada como nascimento precisa conter o "
            "nascimento; nada foi enviado ao Google."
        )
    fora = [e or "(ilegível)" for e in estados if e != ESTADO_INICIAL_PERMITIDO]
    if fora:
        raise NascimentoAtivo(
            f"o payload manda a campanha nascer {', '.join(fora)} e só "
            f"{ESTADO_INICIAL_PERMITIDO} nasce por aqui. Ativar é outro ato, "
            "com outra autorização, e ele não existe neste fluxo. Nada foi "
            "enviado ao Google."
        )


def usada(autorizacao) -> bool:
    """Só para prova e diagnóstico: esta autorização já escreveu?"""
    assinatura = str(getattr(autorizacao, "assinatura", "") or "")
    if not assinatura:
        return False
    with _TRAVA:
        return assinatura in _CONSUMIDAS


def estado() -> dict:
    """Estado agregado, sem vazar assinatura nem identidade."""
    with _TRAVA:
        return {
            "autoridade_canonica": AUTORIDADE_CANONICA,
            "estado_inicial_permitido": ESTADO_INICIAL_PERMITIDO,
            "canais_que_nascem": sorted(CANAIS_QUE_NASCEM),
            "autorizacoes_consumidas": len(_CONSUMIDAS),
            "versao_material": VERSAO_MATERIAL,
        }
