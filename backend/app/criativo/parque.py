"""O parque criativo lido do banco — motores, modos, formatos, skins, vozes, gates.

## Por que este módulo existe

A `v11_02` colocou 11 tabelas de domínio em producao (28/08/2026) e **nenhuma rota
HTTP as alcancava**. Um catalogo que ninguem le nao arbitra nada: ele vira a quinta
copia, ao lado do manifesto JSON, do `requisitos.yaml`, do `dominio.py` e do
`criativos.ts`. Este modulo e a leitura que faz o banco valer.

## A decisao que este modulo NAO toma

`GET /formatos` continua servindo `dominio.FORMATOS`, e nao esta tabela.

Parece errado e e deliberado. O banco tem 7 slots; o executor conhece 4. Apontar
`/formatos` para o banco faria a tela oferecer `16x9`, `3x4` e `video-9x16` para o
motor recusar com `SlotDesconhecido` -> 400. Trocar "o operador nao ve um formato
que existe" por "o operador escolhe um formato que falha depois de clicar" e piorar.

Entao a divergencia vira DADO: `LeituraDoParque.divergencias` diz, com nome e numero,
o que o banco tem e o runtime nao executa. Quem consertar o executor apaga a linha;
enquanto ela existir, ela esta na tela.

## Ausencia nunca vira zero

Uma tabela que responde `[]` e diferente de uma tabela que nao respondeu. A primeira
e uma lista vazia; a segunda e `None` mais um erro nomeado em `falhas`. Uma tela que
tratasse as duas igual diria "nenhum motor cadastrado" quando o banco esta fora do ar.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.criativo import dominio
from app.criativo.persistencia import ErroDePersistencia, Repositorio

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# As tabelas, e a ordem em que cada uma se apresenta ao operador
# ─────────────────────────────────────────────────────────────────────────────

# (chave na resposta, tabela, colunas, ordenacao)
_TABELAS: tuple[tuple[str, str, str, str], ...] = (
    ("motores", "criativo_motor",
     "id,slug,nome,produz,runtime,cofre_asset_id,provider,modelo,versao_do_adaptador,"
     "custo_referencia_usd,custo_unidade,custo_fonte,capacidades,fonte,verificado_em,ativo",
     "slug"),
    ("modos", "criativo_modo_de_producao",
     "id,slug,nome,descricao,exige_provider_de_imagem,renderer,estado_de_prova,prova,"
     "saidas_no_snapshot,fonte,ordem",
     "ordem,slug"),
    ("formatos", "criativo_formato",
     "id,slot,rotulo,proporcao,largura,altura,tipo_de_asset,midia,descricao,"
     "destinos_tipicos,fonte,ativo,ordem",
     "ordem,slot"),
    ("finalidades", "criativo_finalidade",
     "id,slug,nome,descricao,classe,ativo,ordem", "ordem,slug"),
    ("skins", "criativo_skin",
     "id,slug,nicho,arco,papeis_obrigatorios,elementos,motor_id,fonte,ativo", "slug"),
    ("vozes", "criativo_voz",
     "id,slug,voice_id,fallbacks,estilo,idioma,provider,motor_id,fonte,ativo", "slug"),
    ("gates", "criativo_gate",
     "id,slug,motor_id,familia,midia,descricao,bloqueante,fonte", "familia,slug"),
    ("exigenciasDeCanal", "criativo_exigencia_de_canal",
     "id,canal,tipo_de_asset,quantidade_minima,quantidade_maxima,quantidade_recomendada,"
     "proporcao_alvo,tolerancia_proporcao,largura_minima,altura_minima,largura_recomendada,"
     "altura_recomendada,bytes_maximos,mimes_aceitos,duracao_minima_s,duracao_maxima_s,"
     "caracteres_maximos,caracteres_de_pelo_menos_um,provisorio,fonte_dos_numeros,verificado_em",
     "canal,tipo_de_asset"),
    ("tetosCombinados", "criativo_teto_combinado",
     "id,canal,rotulo,tipos,minimo,maximo,fonte", "canal,rotulo"),
)


@dataclass(frozen=True)
class Divergencia:
    """Um desacordo entre o catalogo do banco e o que o runtime executa.

    Isto e um FATO medido na hora da leitura, nao uma configuracao. Some sozinho
    quando alguem alinhar as duas pontas.
    """

    onde: str
    o_que: str
    banco: str | None
    runtime: str | None


@dataclass
class LeituraDoParque:
    itens: dict[str, list[dict[str, Any]] | None] = field(default_factory=dict)
    falhas: dict[str, str] = field(default_factory=dict)
    divergencias: list[Divergencia] = field(default_factory=list)
    lido_em: str = ""

    @property
    def completa(self) -> bool:
        return not self.falhas


class Parque:
    """Leitura somente-leitura do parque. Nao escreve, nao semeia, nao corrige."""

    def __init__(self, repo: Repositorio) -> None:
        self._repo = repo

    async def _uma(self, tabela: str, colunas: str, ordem: str) -> list[dict[str, Any]]:
        return await self._repo.listar_catalogo(tabela, colunas, ordem)

    async def ler(self) -> LeituraDoParque:
        # Nove tabelas pequenas em nove viagens sequenciais seriam nove RTTs ate
        # o Hetzner. Em paralelo e um.
        tarefas = [self._uma(t, c, o) for _, t, c, o in _TABELAS]
        resultados = await asyncio.gather(*tarefas, return_exceptions=True)

        leitura = LeituraDoParque(lido_em=datetime.now(timezone.utc).isoformat())
        for (chave, tabela, _, _), r in zip(_TABELAS, resultados, strict=True):
            if isinstance(r, BaseException):
                log.warning("criativo.parque: %s nao respondeu: %s", tabela, r)
                # A mensagem do PostgREST cita constraint e coluna: vai para o log,
                # nunca para o operador. O que sobe e o nome da tabela que faltou.
                leitura.itens[chave] = None
                leitura.falhas[chave] = tabela
            else:
                leitura.itens[chave] = r

        _marcar_executaveis(leitura.itens.get("formatos"))
        leitura.divergencias = _medir_divergencias(leitura.itens.get("formatos"))
        return leitura


def _marcar_executaveis(formatos: list[dict[str, Any]] | None) -> None:
    """Acrescenta a cada formato do banco se o EXECUTOR sabe produzi-lo.

    ⚠️ Esta e a informacao que faltava para o Laboratorio nao virar exatamente a
    tela que o comentario de `GET /parque` diz querer evitar. O banco declara 7
    slots; `dominio.FORMATOS` conhece 4. Sem esta marca, a tela oferece os 7 e o
    operador descobre a recusa depois de montar a receita inteira.

    Nao filtra e nao esconde: um slot que o banco declara continua aparecendo,
    com o motivo escrito. Esconder trocaria um problema visivel por um invisivel.
    """
    if formatos is None:
        return
    conhecidos = {f.slot for f in dominio.FORMATOS}
    for linha in formatos:
        slot = str(linha.get("slot"))
        pode = slot in conhecidos
        linha["executavel_agora"] = pode
        linha["motivo_se_nao"] = (
            None
            if pode
            else (
                "O catalogo declara este formato e o executor deste ambiente "
                "ainda nao sabe produzi-lo."
            )
        )


def _proporcao_declarada(texto: Any) -> float | None:
    """`"1.91:1"` -> 1.91. `None` quando a forma nao e legivel.

    `criativo_formato.proporcao` e `text` sem CHECK de forma. Nao adivinha: um
    valor ilegivel vira `None` e a comparacao correspondente sai como divergencia
    de forma, nao como aprovacao silenciosa.
    """
    if not isinstance(texto, str):
        return None
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*[:x]\s*(\d+(?:\.\d+)?)\s*$", texto)
    if not m:
        return None
    a, b = float(m.group(1)), float(m.group(2))
    return None if b == 0 else a / b


# Canvas nativo com que cada motor externo COMPOE, quando ele difere do canvas
# que o Estudio declara. Isto nao e coluna especulativa no banco: e conhecimento
# medido do legado, que vive aqui porque e do executor, nao do catalogo.
#
# ⚠️ G11. A PRENSA compoe `4x5` em 1088x1360 e `1x1` em 1200x1200 (execucao real
# de PMax); o Estudio declara 1080x1350 e 1080x1080. A PROPORCAO bate nos dois
# casos (1088/1360 = 1080/1350 = 0.8); o arquivo-base nao. Um adaptador que
# herdasse pixels da PRENSA sem renormalizar entregaria dimensao que o Google Ads
# recusa — e o `criativo_rendition.enquadramento` existe justamente para registrar
# a normalizacao quando ela acontecer.
CANVAS_NATIVO_EXTERNO: dict[str, dict[str, tuple[int, int]]] = {
    "prensa": {
        "4x5": (1088, 1360),
        "1x1": (1200, 1200),
    },
}


def canvas_a_renormalizar(motor_slug: str, slot: str, largura: int, altura: int
                          ) -> tuple[int, int] | None:
    """O canvas nativo do motor difere do que o Estudio pede para este slot?

    Devolve o canvas nativo quando ha diferenca, `None` quando nao ha. Quem
    consumir precisa registrar `enquadramento` na rendition; ignorar isto e como
    o G11 nasceu.
    """
    nativo = CANVAS_NATIVO_EXTERNO.get(motor_slug, {}).get(slot)
    if nativo is None or nativo == (largura, altura):
        return None
    return nativo


def _medir_divergencias(
    formatos_do_banco: list[dict[str, Any]] | None,
) -> list[Divergencia]:
    """Compara `criativo_formato` com `dominio.FORMATOS`, o catalogo que executa.

    Nao conserta nenhum dos dois. Descreve.

    ⚠️ Compara SETE coisas, nao duas. A primeira versao olhava so largura e
    altura, e por isso um slot que mudasse de midia (`imagem` -> `video`), de
    tipo de asset, ou que fosse desativado no banco passava despercebido — e a
    tela seguia oferecendo. Cada campo abaixo ja causou ou pode causar um pedido
    que falha depois do clique.
    """
    if formatos_do_banco is None:
        return []

    achados: list[Divergencia] = []
    no_runtime = {f.slot: f for f in dominio.FORMATOS}
    no_banco = {str(f.get("slot")): f for f in formatos_do_banco}

    for slot in sorted(set(no_banco) - set(no_runtime)):
        linha = no_banco[slot]
        achados.append(
            Divergencia(
                onde="formato",
                o_que=(
                    f"O banco declara o slot `{slot}` e o executor nao o conhece. "
                    "Um pedido nesse slot seria recusado com 400."
                ),
                banco=f"{linha.get('largura')}x{linha.get('altura')} ({linha.get('midia')})",
                runtime=None,
            )
        )

    for slot in sorted(set(no_runtime) - set(no_banco)):
        f = no_runtime[slot]
        achados.append(
            Divergencia(
                onde="formato",
                o_que=f"O executor conhece o slot `{slot}` e o banco nao o declara.",
                banco=None,
                runtime=f"{f.largura}x{f.altura}",
            )
        )

    for slot in sorted(set(no_banco) & set(no_runtime)):
        b, r = no_banco[slot], no_runtime[slot]

        # 1 e 2. dimensao
        if b.get("largura") != r.largura or b.get("altura") != r.altura:
            achados.append(
                Divergencia(
                    onde="formato",
                    o_que=f"O slot `{slot}` tem dimensao diferente nas duas pontas.",
                    banco=f"{b.get('largura')}x{b.get('altura')}",
                    runtime=f"{r.largura}x{r.altura}",
                )
            )

        # 3. proporcao declarada x proporcao real do proprio banco
        declarada = _proporcao_declarada(b.get("proporcao"))
        largura, altura = b.get("largura"), b.get("altura")
        if isinstance(largura, int) and isinstance(altura, int) and altura:
            real = largura / altura
            if declarada is None and b.get("proporcao"):
                achados.append(
                    Divergencia(
                        onde="formato",
                        o_que=(
                            f"O slot `{slot}` declara a proporcao como "
                            f"\"{b.get('proporcao')}\", forma que nao da para ler. "
                            "A proporcao nao foi conferida."
                        ),
                        banco=str(b.get("proporcao")),
                        runtime=None,
                    )
                )
            elif declarada is not None and abs(declarada - real) > 0.01:
                achados.append(
                    Divergencia(
                        onde="formato",
                        o_que=(
                            f"O slot `{slot}` diz ser {b.get('proporcao')} e os "
                            "proprios pixels do banco dizem outra coisa."
                        ),
                        banco=f"{b.get('proporcao')} declarado",
                        runtime=f"{largura}x{altura} = {real:.4f}",
                    )
                )

        # 4. proporcao do banco x proporcao do runtime
        prop_runtime = _proporcao_declarada(r.proporcao)
        if declarada is not None and prop_runtime is not None:
            if abs(declarada - prop_runtime) > 0.01:
                achados.append(
                    Divergencia(
                        onde="formato",
                        o_que=f"O slot `{slot}` tem proporcao diferente nas duas pontas.",
                        banco=str(b.get("proporcao")),
                        runtime=r.proporcao,
                    )
                )

        # 5. midia
        midia_runtime = "imagem"  # `dominio.FORMATOS` so descreve imagem hoje
        if b.get("midia") != midia_runtime:
            achados.append(
                Divergencia(
                    onde="formato",
                    o_que=(
                        f"O slot `{slot}` e `{b.get('midia')}` no banco e o executor "
                        f"so sabe produzir `{midia_runtime}`."
                    ),
                    banco=str(b.get("midia")),
                    runtime=midia_runtime,
                )
            )

        # 6. tipo de asset — e o que o validador de canal usa para achar a regra
        if b.get("tipo_de_asset") != r.tipo.value:
            achados.append(
                Divergencia(
                    onde="formato",
                    o_que=(
                        f"O slot `{slot}` tem tipo de peca diferente nas duas pontas. "
                        "A exigencia de canal e procurada por este campo: divergir "
                        "aqui faz a peca ser conferida contra a regra errada."
                    ),
                    banco=str(b.get("tipo_de_asset")),
                    runtime=r.tipo.value,
                )
            )

        # 7. ativo — o catalogo pode aposentar um slot que o executor ainda produz
        if b.get("ativo") is False:
            achados.append(
                Divergencia(
                    onde="formato",
                    o_que=(
                        f"O slot `{slot}` foi desativado no catalogo e o executor "
                        "continua sabendo produzi-lo."
                    ),
                    banco="inativo",
                    runtime=f"{r.largura}x{r.altura}",
                )
            )

    return achados


# ─────────────────────────────────────────────────────────────────────────────
# Resolvedor slug -> id
# ─────────────────────────────────────────────────────────────────────────────


class Resolvedor:
    """Traduz o nome que o codigo usa para o `id` que a FK exige.

    `criativo_job.motor_id`, `criativo_briefing.modo_id` e
    `criativo_aprovacao.finalidade_id` nasceram nullable na `v11_02` e nunca foram
    preenchidas: nao existia quem traduzisse `"gemini-imagem"` em uuid.

    ## Por que devolver `None` em vez de levantar

    Um job que nasce sem `motor_id` e um job com procedencia mais fraca. Um job que
    NAO NASCE porque o catalogo estava fora do ar e um pedido perdido. A coluna e
    nullable exatamente para que a segunda situacao nao aconteca — e `None` aqui
    significa "nao consegui resolver", que e diferente de "resolvi para nada".
    """

    def __init__(self, repo: Repositorio) -> None:
        self._repo = repo
        self._cache: dict[tuple[str, str], str] = {}

    def usar(self, repo: Repositorio) -> None:
        """Troca o repositorio, e esvazia o cache se a origem mudou.

        ⚠️ O `Executor` vive por processo e tem `repo` trocado a cada requisicao
        (ele depende de `settings`). O `Resolvedor` nasceu segurando a referencia
        da PRIMEIRA requisicao — numa rotacao de credencial, o job seguiria
        resolvendo slug pelo repositorio de chave velha, falharia calado e
        gravaria `motor_id` nulo indefinidamente.
        """
        if getattr(repo, "base", None) != getattr(self._repo, "base", None):
            self._cache.clear()
        self._repo = repo

    async def _id_por_slug(self, tabela: str, coluna: str, valor: str) -> str | None:
        if not valor:
            return None
        chave = (tabela, valor)
        if chave in self._cache:
            return self._cache[chave]
        # ⚠️ S3. A versao anterior fazia `except (ErroDePersistencia, AttributeError)`.
        # Um `AttributeError` REAL de dentro do `Repositorio` — regressao de codigo,
        # nao dublê reduzido — virava `motor_id` nulo silencioso, sem log. A
        # ausencia do metodo e uma pergunta que se responde ANTES de chamar; o erro
        # de dentro da chamada nao pode ser confundido com ela.
        if not hasattr(self._repo, "id_por_slug"):
            log.info(
                "criativo.parque: repositorio %s nao implementa o catalogo; "
                "o vinculo nascera nulo",
                type(self._repo).__name__,
            )
            return None
        try:
            achado = await self._repo.id_por_slug(tabela, coluna, valor)
        except ErroDePersistencia:
            # Nao cacheia a falha: o banco pode voltar na proxima chamada, e um
            # `None` gravado aqui tornaria a falha permanente ate o processo morrer.
            # Sem catalogo, sem vinculo — e o job nasce mesmo assim, com
            # `motor_id` nulo e honesto. A falha NAO e cacheada.
            log.warning(
                "criativo.parque: banco nao respondeu ao resolver %s=%s", coluna, valor
            )
            return None
        # ⚠️ So o ACHADO entra em cache. Guardar `None` aqui era um defeito real:
        # um processo que subisse antes do seed do parque cachearia "nao existe"
        # e TODO job daquele processo nasceria com `motor_id` nulo ate o deploy
        # seguinte — e o nulo passaria despercebido, porque o proprio desenho o
        # declara legitimo. O comentario acima dizia que a falha nao era cacheada
        # e a linha seguinte cacheava a ausencia. Nao mais.
        if achado is not None:
            self._cache[chave] = achado
        return achado

    async def motor(self, slug: str) -> str | None:
        return await self._id_por_slug("criativo_motor", "slug", slug)

    async def modo(self, slug: str) -> str | None:
        return await self._id_por_slug("criativo_modo_de_producao", "slug", slug)

    async def finalidade(self, slug: str) -> str | None:
        return await self._id_por_slug("criativo_finalidade", "slug", slug)
