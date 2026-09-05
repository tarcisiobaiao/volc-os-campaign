"""O portão: da inspeção para a decisão, e da decisão para o recibo assinado.

## As quatro regras, em ordem

1. Detector obrigatório que não rodou  → `GATE_UNAVAILABLE` (bloqueia).
2. Direitos/procedência insuficientes  → `BLOCKED_BY_POLICY` (bloqueia).
3. Achado sem autorização que o cubra  → `THIRD_PARTY_IDENTITY_UNVERIFIED`.
4. Todo achado coberto                 → `THIRD_PARTY_IDENTITY_AUTHORIZED`.
   Nenhum achado                       → `CLEAR`.

A ordem importa: um portão indisponível não pode ser "limpo por falta de
achado", e uma peça sem direitos não deixa de ser bloqueada por não citar
ninguém.

## Aprovação humana não limpa estado

Só um recibo NOVO limpa — reavaliação depois de uma autorização registrada, ou
uma peça diferente. Um botão "eu confirmo" no formulário devolveria ao operador
a responsabilidade de reparar na marca, que é exatamente a responsabilidade que
este portão existe para tirar dele.

## Autorização vem do Cofre, por referência

`autorizacao_ref` é uma referência resolvida no Cofre, com dono, marca coberta,
escopo e validade. Texto livre é recusado: seria a mesma parte interessada
declarando a própria licença.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from . import inspecao as insp
from . import recibo as rec
from .lexico import Achado


class PoliticaCriativaRecusou(ValueError):
    """A peça não pode ir para mídia paga. Carrega o código e o próximo ato."""

    def __init__(self, codigo: str, mensagem: str,
                 *, recibo_emitido: "rec.ReciboDePolitica | None" = None) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.recibo = recibo_emitido


@dataclass(frozen=True)
class AutorizacaoDeTerceiro:
    """Uma autorização do Cofre, já resolvida. Cobre os termos que LISTA."""

    autorizacao_ref: str
    classes: tuple[str, ...]
    termos: tuple[str, ...]
    expira_em: datetime
    canais: tuple[str, ...] = ()

    def vigente(self, agora: datetime) -> bool:
        return self.expira_em > agora

    def cobre(self, achado: Achado, *, canal: str | None) -> bool:
        if achado.classe not in self.classes:
            return False
        if self.canais and canal is not None and canal not in self.canais:
            return False
        from .lexico import normalizar

        alvo = normalizar(achado.termo)
        return any(normalizar(t) == alvo for t in self.termos)


#: A trava que decide se um portão INCOMPLETO bloqueia.
#:
#: ## Por que ela existe, e por que o default é fechado
#:
#: A metade determinística do portão — o léxico sobre copy, nome de arquivo e
#: prompt — roda sempre e sozinha já barra a maior parte das afirmações de
#: vínculo. A metade de PIXEL (OCR e classificador de logotipo) precisa de um
#: motor externo, e este servidor não tem um registrado.
#:
#: A pergunta não é se falta cobertura: falta, e o recibo declara isso em todo
#: caso, com o detector marcado `ERROR`. A pergunta é se a falta BLOQUEIA.
#:
#: `"1"` (o padrão) diz que sim: não conseguir olhar a imagem não pode virar
#: "olhei e não tem nada" — foi essa confusão que deixou o envelope com marca
#: de banco ir para mídia paga. `"0"` aceita a lacuna POR ESCRITO: a decisão
#: passa a sair só dos detectores de texto, e o recibo continua carregando
#: `PIXEL_DETECTOR_NOT_REGISTERED` para que ninguém leia CLEAR como "a imagem
#: foi inspecionada".
#:
#: ⚠️ Ela nunca afrouxa um ACHADO. Marca encontrada bloqueia com a trava em
#: qualquer valor; o que a trava governa é só a ausência de detector.
FLAG_ESTRITO = "CRIATIVO_POLICY_GATE_STRICT"


def modo_estrito() -> bool:
    """Fechado por padrão: ausente ou vazio significa estrito."""
    return os.environ.get(FLAG_ESTRITO, "1") != "0"


#: Procedências que NUNCA vão a mídia paga sem uma licença declarada.
#: Espelha POLICY-04 do contrato Fable.
_SEM_DIREITO_PROVADO = {
    "HUMAN_UPLOAD": "RIGHTS_UNKNOWN",
    "OBSERVED_EXTERNAL": "NOT_INSPECTABLE",
}


def avaliar(
    *,
    asset_ref: str,
    content_sha256: str,
    bytes_da_peca: bytes | None,
    mime: str,
    copy: Mapping[str, Any] | None,
    nome_do_arquivo: str | None,
    prompt: str | None,
    identity_ref: str,
    identidade_propria: Iterable[str] | None,
    procedencia: str,
    licenca_ref: str | None = None,
    autorizacoes: Sequence[AutorizacaoDeTerceiro] = (),
    canal: str | None = None,
    natureza: str = "producao",
    exigir_pixel: bool = True,
    agora: datetime | None = None,
) -> rec.ReciboDePolitica:
    """Inspeciona, decide e assina. SEMPRE devolve recibo — inclusive ao bloquear.

    ⚠️ O recibo do bloqueio é tão importante quanto o da liberação: é ele que a
    tela lê para dizer QUAL marca foi encontrada e ONDE, e é dele que sai o
    próximo ato (registrar autorização no Cofre, ou refazer a peça).
    """
    quando = agora or datetime.now(timezone.utc)
    copy_sha = insp.sha256_da_copy(copy)

    leitura = insp.inspecionar(
        bytes_da_peca=bytes_da_peca, mime=mime, copy=copy,
        nome_do_arquivo=nome_do_arquivo, prompt=prompt,
        identidade_propria=identidade_propria, exigir_pixel=exigir_pixel,
    )

    motivos = list(leitura.motivos)
    achados = list(leitura.achados)

    # 1. Portão indisponível bloqueia — sob a trava. "Não consegui olhar" ≠
    #    "não tem nada". Com a trava aberta a lacuna continua NO RECIBO, e a
    #    decisão passa a sair dos detectores que de fato rodaram.
    if leitura.portao_indisponivel and modo_estrito():
        decisao = rec.GATE_UNAVAILABLE
    # 2. Direitos e natureza, antes de qualquer coisa sobre marcas.
    elif natureza != "producao":
        decisao = rec.BLOCKED_BY_POLICY
        motivos.append("NATURE_NOT_PRODUCTION")
    elif procedencia in _SEM_DIREITO_PROVADO and not licenca_ref:
        decisao = rec.BLOCKED_BY_POLICY
        motivos.append(_SEM_DIREITO_PROVADO[procedencia])
    elif procedencia == "STOCK" and not licenca_ref:
        decisao = rec.BLOCKED_BY_POLICY
        motivos.append("STOCK_LICENSE_MISSING")
    else:
        vigentes = [a for a in autorizacoes if a.vigente(quando)]
        cobertos: list[Achado] = []
        descobertos: list[Achado] = []
        for achado in achados:
            coberto = any(a.cobre(achado, canal=canal) for a in vigentes)
            registro = Achado(
                classe=achado.classe, termo=achado.termo, origem=achado.origem,
                posicao=achado.posicao, peso=achado.peso,
                coberto_por_autorizacao=coberto,
            )
            (cobertos if coberto else descobertos).append(registro)
        achados = cobertos + descobertos
        # 3/4. Qualquer achado descoberto mantém o estado UNVERIFIED.
        if descobertos:
            decisao = rec.THIRD_PARTY_IDENTITY_UNVERIFIED
            motivos.extend(sorted({
                f"THIRD_PARTY_{a.classe}" for a in descobertos}))
        elif cobertos:
            decisao = rec.THIRD_PARTY_IDENTITY_AUTHORIZED
        else:
            decisao = rec.CLEAR

    return rec.emitir(
        asset_ref=asset_ref,
        content_sha256=content_sha256,
        copy_sha256=copy_sha,
        identity_ref=identity_ref,
        lexico_versao=__import__(
            "app.criativo.politica.lexico", fromlist=["versao"]).versao(),
        decisao=decisao,
        detectores=leitura.detectores,
        achados=tuple(sorted(
            achados, key=lambda a: (a.origem, a.classe, a.termo, a.posicao))),
        motivos=tuple(dict.fromkeys(motivos)),
        autorizacoes_consultadas=tuple(
            a.autorizacao_ref for a in autorizacoes),
        avaliado_em=quando,
    )


def exigir_liberacao(
    recibo_da_peca: rec.ReciboDePolitica,
    *,
    asset_ref: str,
    content_sha256: str,
    copy: Mapping[str, Any] | None,
    agora: datetime | None = None,
) -> None:
    """O portão do lado de quem COMPILA. Levanta antes de qualquer rede.

    É esta função que as rotas de mídia paga chamam. Ela reconfere a assinatura,
    a peça, a copy, a expiração e o veredito — nessa ordem — e traduz a recusa
    em algo que o operador consegue agir.
    """
    try:
        rec.conferir(
            recibo_da_peca, asset_ref=asset_ref, content_sha256=content_sha256,
            copy_sha256=insp.sha256_da_copy(copy), agora=agora,
        )
    except rec.ReciboInvalido as exc:
        raise PoliticaCriativaRecusou(
            exc.codigo, _frase(exc.codigo, recibo_da_peca),
            recibo_emitido=recibo_da_peca,
        ) from None


_FRASES: Mapping[str, str] = {
    "POLICY_RECEIPT_SIGNATURE_INVALID": (
        "o recibo de política desta peça não foi emitido por este servidor. "
        "Reavalie a peça antes de usá-la em mídia paga."
    ),
    "POLICY_RECEIPT_ASSET_DIVERGED": (
        "o recibo de política pertence a outra peça."
    ),
    "POLICY_RECEIPT_CONTENT_DIVERGED": (
        "os bytes da peça mudaram depois da inspeção. Uma peça nova precisa de "
        "um recibo novo — a autorização anterior não descreve estes bytes."
    ),
    "POLICY_RECEIPT_COPY_DIVERGED": (
        "a copy mudou depois da inspeção. O recibo cobre peça E texto, porque "
        "a mesma imagem com outro texto pode afirmar outra coisa."
    ),
    "POLICY_RECEIPT_EXPIRED": (
        "o recibo de política desta peça expirou. Reavalie antes de subir."
    ),
    "POLICY_RECEIPT_SUPERSEDED": (
        "este recibo foi substituído por uma reavaliação mais recente."
    ),
    f"POLICY_{rec.THIRD_PARTY_IDENTITY_UNVERIFIED}": (
        "a peça traz identidade de terceiro sem autorização que a cubra. "
        "Registre a autorização no Cofre ou gere outra peça — confirmar no "
        "formulário não limpa este estado."
    ),
    f"POLICY_{rec.BLOCKED_BY_POLICY}": (
        "a procedência ou os direitos desta peça não permitem mídia paga."
    ),
    f"POLICY_{rec.GATE_UNAVAILABLE}": (
        "a inspeção de pixel da peça não pôde ser executada neste servidor, e "
        "não conseguir olhar não é o mesmo que a peça estar limpa. Mídia paga "
        "fica bloqueada até o detector estar disponível."
    ),
}


def _frase(codigo: str, recibo_da_peca: rec.ReciboDePolitica) -> str:
    base = _FRASES.get(codigo, "a peça não está liberada para mídia paga.")
    marcas = sorted({
        f"{a.classe}:{a.termo}" for a in recibo_da_peca.achados
        if not a.coberto_por_autorizacao
    })
    return f"{base} Marcas encontradas: {', '.join(marcas)}." if marcas else base
