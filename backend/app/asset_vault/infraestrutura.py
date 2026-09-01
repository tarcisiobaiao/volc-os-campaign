"""O adapter do Supabase — e o filtro que decide o que uma falha pode dizer.

## Por que a mensagem do Postgres NAO e repassada

Medido em 01/09/2026, num Postgres 15 descartavel: quando uma CHECK recusa a
linha, o servidor anexa

    DETAIL:  Failing row contains (1, asset:…, 1password, FB_PAGE_TOKEN,
             Tr0ub4dor&3, …)

— a LINHA INTEIRA, com o valor recusado. Repassar o corpo de erro do PostgREST
para o browser faria a tentativa de guardar uma senha no campo errado terminar
com a senha na tela. A recusa vazaria exatamente o que ela existe para impedir.

Daí o filtro deste arquivo, em tres camadas:

  1. `details` e `hint` do PostgREST NUNCA saem daqui. Sao os campos que
     carregam a linha.
  2. `message` sai apenas quando casa uma das FRASES QUE ESTE PROJETO ESCREVEU
     (`_FRASES_PROPRIAS`). Elas citam nome de campo, caminho no payload e forma
     esperada — nunca valor. Tudo o mais vira frase fechada por classe de erro:
     "new row for relation … violates check constraint …" nao chega a tela, e
     com ela nao chegam nome de tabela nem de constraint.
  3. Uma varredura final recusa qualquer mensagem que contenha marcador de
     linha crua ou formato de credencial, mesmo que ela tenha passado por (2).
     Defesa em profundidade: a lista de frases proprias envelhece, a varredura
     nao depende de alguem lembrar de atualiza-la.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.asset_vault import dominio as dom
from app.asset_vault.aplicacao import CofreIndisponivel, OperacaoRecusada

log = logging.getLogger("volc.cofre.infra")

#: SQLSTATEs que as funcoes governadas levantam de proposito, com o status HTTP
#: que cada um significa para quem chamou. Ver a secao 15 da v13_01.
_STATUS_POR_SQLSTATE: dict[str, tuple[int, str]] = {
    "22023": (400, "payload_invalido"),        # invalid_parameter_value
    "23001": (400, "campo_proibido"),          # restrict_violation (blocklist / append-only)
    "23514": (400, "regra_do_cofre"),          # check_violation
    "23503": (409, "referencia_inexistente"),  # foreign_key_violation
    "23505": (409, "conflito"),                # unique_violation (idempotencia divergente)
    "23502": (400, "campo_obrigatorio"),       # not_null_violation
    "P0002": (404, "nao_encontrado"),          # no_data_found
    "42501": (503, "sem_autorizacao_no_banco"),
}

#: Frase fechada por codigo. E o que a tela mostra quando a mensagem do banco
#: nao pode ser repetida.
_FRASE_FECHADA: dict[str, str] = {
    "payload_invalido": "O Cofre recusou este pedido: algum campo nao respeita o contrato.",
    "campo_proibido": "O Cofre recusou este pedido por conter um campo que ele nunca guarda.",
    "regra_do_cofre": "O Cofre recusou este pedido por violar uma regra do inventario.",
    "referencia_inexistente": "O pedido aponta para um ativo, tipo ou gaveta que nao existe.",
    "conflito": "Ja existe um registro em conflito com este pedido.",
    "campo_obrigatorio": "Falta um campo obrigatorio neste pedido.",
    "nao_encontrado": "Esse item nao existe no Cofre.",
    "sem_autorizacao_no_banco": "O Cofre esta sem autorizacao no banco para esta operacao.",
    "desconhecido": "O Cofre nao conseguiu concluir esta operacao.",
}

#: As frases que ESTE projeto escreveu, e por isso auditou. Todas citam nome de
#: campo, caminho ou forma esperada — nenhuma repete um valor recebido.
_FRASES_PROPRIAS: tuple[str, ...] = (
    "campo proibido no Cofre:",
    "recebeu campo(s) que este contrato nao conhece:",
    "referencia invalida para o provider",
    "esta chave de idempotencia ja foi usada",
    "e append-only:",
    "nao existe no Cofre",
    "nao existe ou ja estava desfeita",
    "nao existe ou ja estava aposentado",
    "nao existe ou nao estava aposentado",
    "reativar exige um estado diferente",
    "exige um objeto JSON",
    "provider de cofre desconhecido",
)

#: Marcadores de que a mensagem carrega linha crua ou material de credencial.
#: Se qualquer um aparecer, a mensagem e descartada por completo.
_MARCADOR_DE_VAZAMENTO = re.compile(
    r"Failing row contains"
    r"|DETAIL:"
    r"|Key \("
    r"|-----BEGIN"
    r"|eyJ[A-Za-z0-9_-]{20,}\."
    r"|\bop://",
    re.IGNORECASE,
)


def _mensagem_segura(bruta: str | None, codigo: str) -> str:
    if not bruta:
        return _FRASE_FECHADA.get(codigo, _FRASE_FECHADA["desconhecido"])
    uma_linha = " ".join(bruta.split())
    if _MARCADOR_DE_VAZAMENTO.search(uma_linha):
        log.warning("mensagem do banco descartada por conter marcador de vazamento (codigo=%s)", codigo)
        return _FRASE_FECHADA.get(codigo, _FRASE_FECHADA["desconhecido"])
    if any(frase in uma_linha for frase in _FRASES_PROPRIAS):
        return uma_linha[:400]
    return _FRASE_FECHADA.get(codigo, _FRASE_FECHADA["desconhecido"])


class RepositorioSupabase:
    """Fala com as funcoes governadas por `POST /rest/v1/rpc/<funcao>`.

    Nao existe um caminho de escrita direta em tabela porque nao existe
    privilegio para isso: a v13_01 revoga ALL de `service_role` nas nove
    tabelas. Se este arquivo tentasse `POST /rest/v1/cofre_ativo`, o banco
    responderia 403 — e essa e a intencao.
    """

    def __init__(self, supabase: Any, timeout_s: float = 15.0):
        self._supa = supabase
        self._timeout = timeout_s

    @property
    def configurado(self) -> bool:
        return bool(getattr(self._supa, "enabled", False))

    async def _rpc(self, funcao: str, argumentos: dict[str, Any]) -> Any:
        if not self.configurado:
            # Falha FECHADA. Um Cofre sem banco nao e um Cofre vazio.
            raise CofreIndisponivel("Supabase nao configurado neste ambiente.")
        try:
            return await self._supa.rpc(funcao, argumentos)
        except httpx.HTTPStatusError as exc:
            raise self._traduzir(exc) from exc
        except httpx.HTTPError as exc:
            log.warning("cofre: falha de rede em %s: %s", funcao, exc)
            raise CofreIndisponivel("Nao foi possivel falar com o Cofre agora.") from exc
        except ValueError as exc:
            # Corpo que nao e JSON: proxy no meio, gateway devolvendo HTML.
            log.warning("cofre: resposta ilegivel em %s: %s", funcao, exc)
            raise CofreIndisponivel("O Cofre respondeu em um formato inesperado.") from exc

    def _traduzir(self, exc: httpx.HTTPStatusError) -> Exception:
        """Erro HTTP do PostgREST -> excecao de dominio, com mensagem filtrada."""
        resposta = exc.response
        corpo: dict[str, Any] = {}
        try:
            lido = resposta.json()
            if isinstance(lido, dict):
                corpo = lido
        except Exception:  # noqa: BLE001 — corpo vazio ou HTML de proxy
            corpo = {}

        sqlstate = str(corpo.get("code") or "")
        status, codigo = _STATUS_POR_SQLSTATE.get(sqlstate, (0, ""))

        if not status:
            if resposta.status_code in (401, 403):
                status, codigo = 503, "sem_autorizacao_no_banco"
            elif resposta.status_code == 404:
                # Funcao ausente: a migration nao foi aplicada. Dizer o QUE
                # faltou evita que o proximo procure rede em vez de schema.
                log.error("cofre: RPC ausente no banco — a v13_01 nao foi aplicada")
                raise CofreIndisponivel(
                    "O Cofre ainda nao existe neste banco. A migration v13_01 nao foi aplicada."
                )
            elif 500 <= resposta.status_code < 600:
                raise CofreIndisponivel("O Cofre nao respondeu a esta operacao.")
            else:
                status, codigo = 400, "desconhecido"

        if status == 503:
            raise CofreIndisponivel(_FRASE_FECHADA["sem_autorizacao_no_banco"])

        # ⚠️ Somente `message`. `details` e `hint` sao os campos que carregam a
        # linha recusada, e eles morrem aqui — nem sequer sao lidos.
        mensagem = _mensagem_segura(corpo.get("message"), codigo)
        return OperacaoRecusada(mensagem, codigo=codigo, status=status)

    @staticmethod
    def _objeto(resposta: Any, o_que: str) -> dict[str, Any]:
        """PostgREST devolve o escalar puro para funcao que retorna jsonb.

        Uma resposta que nao e objeto NAO vira `{}`: vira indisponibilidade.
        Aceitar forma desconhecida como vazio e como o painel aprende a
        inventar 'nenhum ativo' a partir de um proxy mal configurado.
        """
        if isinstance(resposta, list):
            resposta = resposta[0] if resposta else None
        if isinstance(resposta, dict):
            return resposta
        log.warning("cofre: %s veio em forma inesperada: %s", o_que, type(resposta).__name__)
        raise CofreIndisponivel("O Cofre respondeu em um formato que esta API nao reconhece.")

    async def listar(self, **filtros: Any) -> dict[str, Any]:
        bruto = self._objeto(await self._rpc("cofre_listar_ativos", filtros), "inventario")
        if "gavetas" not in bruto or "ativos" not in bruto:
            raise CofreIndisponivel("O Cofre respondeu sem gavetas nem ativos.")
        return bruto

    async def detalhar(self, ativo_id: str) -> dict[str, Any] | None:
        bruto = await self._rpc("cofre_detalhar_ativo", {"p_ativo_id": ativo_id})
        if isinstance(bruto, list):
            bruto = bruto[0] if bruto else None
        if bruto is None:
            # Ativo inexistente e `null`, e isso e um FATO — nao uma falha.
            return None
        if not isinstance(bruto, dict):
            raise CofreIndisponivel("O Cofre respondeu em um formato que esta API nao reconhece.")
        return bruto

    async def engines(self) -> list[dict[str, Any]]:
        bruto = await self._rpc("cofre_engines_disponiveis", {})
        return self._lista(bruto, "engines")

    async def postura_credencial(self, ativo_id: str) -> list[dict[str, Any]]:
        bruto = await self._rpc("cofre_postura_credencial", {"p_ativo_id": ativo_id})
        return self._lista(bruto, "postura de credencial")

    @staticmethod
    def _lista(bruto: Any, o_que: str) -> list[dict[str, Any]]:
        """Uma lista com elemento estranho e resposta QUEBRADA, nao lista curta.

        ⚠️ Defeito medido por revisao adversarial em 01/09/2026: a versao
        anterior terminava em `[i for i in bruto if isinstance(i, dict)]`, e com
        `[None]` na resposta o filtro devolvia `[]` — a rota respondia
        `200 {"engines": []}` sobre um banco que respondeu errado. E o mesmo
        defeito que `_objeto` ja evitava, escrito de novo uma funcao abaixo:
        descartar o que nao se entende produz um vazio que parece verdade.
        """
        if isinstance(bruto, list) and len(bruto) == 1 and isinstance(bruto[0], list):
            bruto = bruto[0]
        if not isinstance(bruto, list):
            raise CofreIndisponivel(f"O Cofre respondeu {o_que} em forma inesperada.")
        if any(not isinstance(i, dict) for i in bruto):
            log.warning("cofre: %s trouxe elemento que nao e objeto", o_que)
            raise CofreIndisponivel(f"O Cofre respondeu {o_que} em forma inesperada.")
        return bruto

    async def executar(self, funcao: str, argumentos: dict[str, Any]) -> dict[str, Any]:
        recibo = self._objeto(await self._rpc(funcao, argumentos), f"recibo de {funcao}")
        # ⚠️ Ultima peneira antes de o recibo virar resposta HTTP. As funcoes
        # governadas nao colocam localizador em recibo nenhum — e esta linha e o
        # que garante que continue assim quando alguem adicionar um campo novo.
        dom.recusar_chave_sensivel(recibo, "recibo")
        return recibo
