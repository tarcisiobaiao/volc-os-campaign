"""O parque criativo: leitura, divergência medida e vínculo slug → id.

Estas provas existem porque a `v11_02` colocou 11 tabelas em produção e o backend
não as lia. Um catálogo sem leitor não arbitra nada — vira a quinta cópia, ao lado
do manifesto, do `requisitos.yaml`, do `dominio.py` e do `criativos.ts`.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.criativo import apresentacao, dominio
from app.criativo.parque import Parque, Resolvedor
from app.criativo.persistencia import ErroDePersistencia, Repositorio


class CatalogoFalso:
    """Dublê que responde como o PostgREST responde: lista de dicionários."""

    def __init__(self, tabelas: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.tabelas = tabelas if tabelas is not None else {}
        self.consultas: list[tuple[str, str, str]] = []

    async def listar_catalogo(
        self, tabela: str, colunas: str, ordem: str
    ) -> list[dict[str, Any]]:
        self.consultas.append((tabela, colunas, ordem))
        if tabela in self.tabelas:
            return self.tabelas[tabela]
        return []

    async def id_por_slug(self, tabela: str, coluna: str, valor: str) -> str | None:
        for linha in self.tabelas.get(tabela, []):
            if linha.get(coluna) == valor:
                return str(linha["id"])
        return None


class CatalogoQueCai(CatalogoFalso):
    async def listar_catalogo(self, tabela: str, colunas: str, ordem: str) -> Any:
        if tabela == "criativo_motor":
            raise ErroDePersistencia("o banco não respondeu")
        return await super().listar_catalogo(tabela, colunas, ordem)

    async def id_por_slug(self, tabela: str, coluna: str, valor: str) -> str | None:
        raise ErroDePersistencia("o banco não respondeu")


class RepoSemCatalogo:
    """Repositório que não conhece o parque — como o dublê de `test_criativo_execucao`."""


# ═══════════════════════════════════════════════════════════════════════════
# 1. Ausência de tabela ≠ tabela vazia
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_tabela_vazia_e_tabela_que_nao_respondeu_nao_se_confundem():
    """Uma tela que tratasse as duas igual diria "nenhum motor cadastrado" com o
    banco fora do ar — e o operador cadastraria um motor que já existe."""
    leitura = await Parque(CatalogoQueCai()).ler()

    assert leitura.itens["motores"] is None, "tabela que falhou não pode virar []"
    assert leitura.falhas == {"motores": "criativo_motor"}
    assert leitura.itens["skins"] == [], "tabela que respondeu vazia é []"
    assert leitura.completa is False

    dto = apresentacao.parque_dto(leitura)
    assert dto["motores"] is None
    assert dto["skins"] == []
    assert dto["naoLidas"] == ["motores"]


@pytest.mark.anyio
async def test_leitura_carimba_a_hora_em_que_leu():
    """Medida sem carimbo de frescor é medida que envelhece em silêncio."""
    leitura = await Parque(CatalogoFalso()).ler()
    assert leitura.lido_em, "toda leitura declara quando aconteceu"
    assert apresentacao.parque_dto(leitura)["lidoEm"] == leitura.lido_em


@pytest.mark.anyio
async def test_as_nove_tabelas_sao_lidas_em_uma_rodada():
    catalogo = CatalogoFalso()
    await Parque(catalogo).ler()
    tabelas = {t for t, _, _ in catalogo.consultas}
    assert len(catalogo.consultas) == 9
    assert "criativo_motor" in tabelas and "criativo_teto_combinado" in tabelas


# ═══════════════════════════════════════════════════════════════════════════
# 2. A divergência entre banco e runtime é DADO, não silêncio
# ═══════════════════════════════════════════════════════════════════════════


# Os tipos de asset reais, para a fixture não inventar um vocabulário próprio.
_TIPO_DO_SLOT = {
    "1x1": "imagem_marketing_quadrada",
    "4x5": "imagem_marketing_retrato",
    "9x16": "imagem_marketing_retrato_alto",
    "1.91x1": "imagem_marketing",
    "16x9": "imagem_marketing",
    "3x4": "imagem_marketing_retrato",
    "video-9x16": "video",
}


def _formato(
    slot: str,
    largura: int,
    altura: int,
    midia: str = "imagem",
    **extra: Any,
) -> dict[str, Any]:
    """Linha de `criativo_formato` com os campos que a divergência compara.

    ⚠️ A primeira versão desta fixture tinha só slot/largura/altura/mídia. Com a
    divergência olhando sete campos, uma fixture pobre gera achado falso — e a
    tentação seria afrouxar a regra em vez de enriquecer o dublê. O dublê é que
    estava errado: linha de produção tem `proporcao`, `tipo_de_asset` e `ativo`.
    """
    from math import gcd

    d = gcd(largura, altura) or 1
    linha: dict[str, Any] = {
        "slot": slot,
        "largura": largura,
        "altura": altura,
        "midia": midia,
        "proporcao": f"{largura // d}:{altura // d}",
        "tipo_de_asset": _TIPO_DO_SLOT.get(slot, "imagem_marketing"),
        "ativo": True,
    }
    linha.update(extra)
    return linha


@pytest.mark.anyio
async def test_slot_que_o_banco_declara_e_o_executor_nao_conhece_vira_divergencia():
    """Este é o estado REAL de produção em 28/08/2026: 7 slots no banco, 4 no
    `dominio.FORMATOS`. `16x9`, `3x4` e `video-9x16` existem e não executam."""
    catalogo = CatalogoFalso(
        {
            "criativo_formato": [
                _formato("1x1", 1080, 1080),
                _formato("4x5", 1080, 1350),
                _formato("9x16", 1080, 1920),
                _formato("1.91x1", 1200, 628),
                _formato("16x9", 1920, 1080),
                _formato("3x4", 1080, 1440),
                _formato("video-9x16", 1080, 1920, midia="video"),
            ]
        }
    )
    leitura = await Parque(catalogo).ler()

    orfaos = {d.banco for d in leitura.divergencias if d.runtime is None}
    assert len(leitura.divergencias) == 3, [d.o_que for d in leitura.divergencias]
    assert "1920x1080 (imagem)" in orfaos
    assert "1080x1920 (video)" in orfaos
    for d in leitura.divergencias:
        assert "recusado" in d.o_que or "não o declara" in d.o_que


@pytest.mark.anyio
async def test_mesma_dimensao_nos_dois_lados_nao_gera_ruido():
    catalogo = CatalogoFalso(
        {
            "criativo_formato": [
                _formato(f.slot, f.largura, f.altura) for f in dominio.FORMATOS
            ]
        }
    )
    leitura = await Parque(catalogo).ler()
    assert leitura.divergencias == []


@pytest.mark.anyio
async def test_dimensao_diferente_para_o_mesmo_slot_e_denunciada():
    """A PRENSA compõe `4x5` em 1088×1360 e o Estúdio declara 1080×1350. Mesma
    proporção, arquivo-base diferente — um adaptador que herdasse pixels sem
    renormalizar entregaria dimensão que o Google Ads recusa."""
    catalogo = CatalogoFalso({"criativo_formato": [_formato("4x5", 1088, 1360)]})
    leitura = await Parque(catalogo).ler()

    troca = [d for d in leitura.divergencias if d.banco == "1088x1360"]
    assert len(troca) == 1
    assert troca[0].runtime == "1080x1350"


class FormatoQueCai(CatalogoFalso):
    async def listar_catalogo(self, tabela: str, colunas: str, ordem: str):
        if tabela == "criativo_formato":
            raise ErroDePersistencia("o banco não respondeu")
        return await super().listar_catalogo(tabela, colunas, ordem)


@pytest.mark.anyio
async def test_sem_leitura_de_formato_nao_inventa_divergencia():
    """Banco fora do ar não é "os catálogos divergem".

    ⚠️ Distinção que a primeira versão deste teste errou: um `criativo_formato`
    que responde `[]` é uma tabela VAZIA, e aí "o executor conhece 4 slots que o
    banco não declara" é verdade e deve aparecer. O silêncio só é correto quando
    a tabela **não respondeu** — que é o caso coberto aqui.
    """
    leitura = await Parque(FormatoQueCai()).ler()
    assert leitura.itens["formatos"] is None
    assert leitura.divergencias == []


@pytest.mark.anyio
async def test_catalogo_vazio_denuncia_os_slots_orfaos_do_runtime():
    """Tabela vazia é medida, não ausência: os 4 slots do executor viram divergência."""
    leitura = await Parque(CatalogoFalso({"criativo_formato": []})).ler()
    assert len(leitura.divergencias) == len(dominio.FORMATOS)
    assert all(d.banco is None for d in leitura.divergencias)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Vínculo slug → id
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_resolve_motor_modo_e_finalidade_pelos_slugs_reais():
    catalogo = CatalogoFalso(
        {
            "criativo_motor": [{"id": "m-1", "slug": "gemini-imagem"}],
            "criativo_modo_de_producao": [{"id": "d-1", "slug": "full_llm"}],
            "criativo_finalidade": [{"id": "f-1", "slug": "google_display"}],
        }
    )
    r = Resolvedor(catalogo)
    assert await r.motor("gemini-imagem") == "m-1"
    assert await r.modo("full_llm") == "d-1"
    assert await r.finalidade("google_display") == "f-1"


@pytest.mark.anyio
async def test_slug_ausente_devolve_none_e_nao_levanta():
    """A coluna é nullable de propósito: um job com procedência mais fraca é pior
    que um job perfeito e MELHOR que um pedido perdido."""
    r = Resolvedor(CatalogoFalso({"criativo_motor": []}))
    assert await r.motor("motor-que-nao-existe") is None
    assert await r.motor("") is None


@pytest.mark.anyio
async def test_banco_fora_do_ar_nao_impede_o_job_de_nascer():
    r = Resolvedor(CatalogoQueCai())
    assert await r.motor("gemini-imagem") is None


@pytest.mark.anyio
async def test_repositorio_sem_catalogo_nao_quebra_a_criacao():
    """Um adaptador reduzido (dublê, migração) não pode derrubar a criação de job
    só por não conhecer as tabelas de apoio."""
    r = Resolvedor(RepoSemCatalogo())
    assert await r.motor("gemini-imagem") is None


@pytest.mark.anyio
async def test_falha_nao_e_cacheada_mas_sucesso_e():
    """Cachear a falha tornaria o banco fora do ar um defeito permanente até o
    processo morrer."""
    catalogo = CatalogoFalso({"criativo_motor": [{"id": "m-1", "slug": "gemini-imagem"}]})
    r = Resolvedor(catalogo)
    assert await r.motor("gemini-imagem") == "m-1"
    catalogo.tabelas["criativo_motor"] = []
    assert await r.motor("gemini-imagem") == "m-1", "o achado fica em cache"

    caindo = CatalogoQueCai()
    r2 = Resolvedor(caindo)
    assert await r2.motor("gemini-imagem") is None
    assert ("criativo_motor", "gemini-imagem") not in r2._cache


# ═══════════════════════════════════════════════════════════════════════════
# 4. O motor declara a própria identidade
# ═══════════════════════════════════════════════════════════════════════════


def test_o_slug_do_motor_nao_e_o_nome_do_motor():
    """`nome` carrega o modelo e muda quando o modelo muda; `slug` é a identidade
    no registro e não pode mudar. Resolver por `nome` devolveria `None` para
    sempre, e `criativo_job.motor_id` nunca sairia de nulo sem ninguém notar."""
    from services.creative_engine.motores.gemini_imagem import MotorGeminiImagem

    motor = MotorGeminiImagem()
    assert motor.slug == "gemini-imagem"
    assert motor.nome.startswith("gemini:")
    assert motor.slug != motor.nome


# ═══════════════════════════════════════════════════════════════════════════
# 5. Achados da auditoria adversarial de 28/08/2026
# ═══════════════════════════════════════════════════════════════════════════


class RepoEspiao(Repositorio):
    """Repositório real, com o transporte trocado por um espião.

    ⚠️ Os nove testes de `Resolvedor` acima usam `CatalogoFalso.id_por_slug`, que
    reimplementa a busca CORRETAMENTE. Isso deixava `Repositorio.id_por_slug` —
    o único código que traduz slug→id de verdade — sem nenhuma prova. Apagar o
    filtro `eq.` de lá faria o PostgREST devolver a PRIMEIRA linha de
    `criativo_motor`, e `criativo_job.motor_id` passaria a apontar para o motor
    errado, com aparência de sucesso. A suíte inteira ficava verde.
    """

    def __init__(self) -> None:
        super().__init__("https://exemplo.invalido", "chave-de-teste")
        self.chamadas: list[tuple[str, dict[str, Any]]] = []
        self.responder: list[dict[str, Any]] = []

    async def _get(self, alvo: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        self.chamadas.append((alvo, params))
        return self.responder


@pytest.mark.anyio
async def test_id_por_slug_filtra_pelo_slug_pedido():
    repo = RepoEspiao()
    repo.responder = [{"id": "m-1"}]
    achado = await repo.id_por_slug("criativo_motor", "slug", "gemini-imagem")

    assert achado == "m-1"
    alvo, params = repo.chamadas[0]
    assert alvo == "criativo_motor"
    assert params.get("slug") == "eq.gemini-imagem", (
        "sem o filtro `eq.`, o PostgREST devolve a primeira linha da tabela e o "
        "vínculo aponta para o motor errado, com cara de sucesso"
    )
    assert params.get("limit") == "1"


@pytest.mark.anyio
async def test_id_por_slug_sem_linha_devolve_none():
    repo = RepoEspiao()
    repo.responder = []
    assert await repo.id_por_slug("criativo_motor", "slug", "inexistente") is None


@pytest.mark.anyio
async def test_listar_catalogo_pede_ordem_estavel():
    """Sem `order`, o PostgREST devolve em ordem de heap e a tela embaralha
    entre leituras sem nada ter mudado."""
    repo = RepoEspiao()
    await repo.listar_catalogo("criativo_formato", "id,slot", "ordem,slot")
    _, params = repo.chamadas[0]
    assert params.get("order") == "ordem,slot"
    assert params.get("select") == "id,slot"


@pytest.mark.anyio
async def test_ausencia_nao_e_cacheada_como_achado():
    """Um processo que suba antes do seed do parque cachearia "não existe" e
    TODO job daquele processo nasceria com `motor_id` nulo até o próximo deploy.
    O comentário do código dizia que a falha não era cacheada; a linha seguinte
    cacheava a ausência."""
    catalogo = CatalogoFalso({"criativo_motor": []})
    r = Resolvedor(catalogo)
    assert await r.motor("gemini-imagem") is None

    catalogo.tabelas["criativo_motor"] = [{"id": "m-1", "slug": "gemini-imagem"}]
    assert await r.motor("gemini-imagem") == "m-1", (
        "a ausência não pode virar resposta permanente do processo"
    )


@pytest.mark.anyio
async def test_trocar_o_repositorio_esvazia_o_cache_quando_a_origem_muda():
    """O `Executor` vive por processo e tem `repo` trocado a cada requisição. O
    `Resolvedor` nascia segurando a referência da PRIMEIRA — numa rotação de
    credencial, todo slug→id seguiria saindo pelo repositório antigo."""
    velho = CatalogoFalso({"criativo_motor": [{"id": "m-velho", "slug": "gemini-imagem"}]})
    velho.base = "https://antigo.invalido"
    r = Resolvedor(velho)
    assert await r.motor("gemini-imagem") == "m-velho"

    novo = CatalogoFalso({"criativo_motor": [{"id": "m-novo", "slug": "gemini-imagem"}]})
    novo.base = "https://novo.invalido"
    r.usar(novo)
    assert await r.motor("gemini-imagem") == "m-novo"


# ── executabilidade do formato ───────────────────────────────────────────────


@pytest.mark.anyio
async def test_formato_do_banco_declara_se_o_executor_o_produz():
    """A tela precisa desta marca para não oferecer o que o motor recusa."""
    catalogo = CatalogoFalso(
        {
            "criativo_formato": [
                _formato("1x1", 1080, 1080),
                _formato("16x9", 1920, 1080),
            ]
        }
    )
    leitura = await Parque(catalogo).ler()
    por_slot = {f["slot"]: f for f in leitura.itens["formatos"] or []}

    assert por_slot["1x1"]["executavel_agora"] is True
    assert por_slot["1x1"]["motivo_se_nao"] is None
    assert por_slot["16x9"]["executavel_agora"] is False
    assert "nao sabe produzi-lo" in por_slot["16x9"]["motivo_se_nao"]


@pytest.mark.anyio
async def test_o_dto_leva_a_executabilidade_em_camelCase():
    catalogo = CatalogoFalso({"criativo_formato": [_formato("16x9", 1920, 1080)]})
    dto = apresentacao.parque_dto(await Parque(catalogo).ler())
    assert dto["formatos"][0]["executavelAgora"] is False
    assert dto["formatos"][0]["motivoSeNao"] is not None


# ── o ponto de escrita, não só o resolvedor ─────────────────────────────────
# ⚠️ As provas acima cobrem o `Resolvedor`. Elas NÃO cobriam a chamada dentro do
# `Executor` — e a auditoria mediu isso: trocar `slug` por `nome` no ponto de
# escrita deixava a suíte inteira verde, apesar de o commit afirmar justamente
# que resolver por `nome` "devolveria None para sempre e a coluna nunca sairia
# de nula sem ninguém notar". Ninguém notava.


class RepoComCatalogo:
    """O dublê de `test_criativo_execucao`, acrescido do parque."""

    def __init__(self) -> None:
        from test_criativo_execucao import RepoFalso  # noqa: PLC0415

        self._base = RepoFalso()
        self.base = "https://exemplo.invalido"
        self.tabelas: dict[str, list[dict[str, Any]]] = {
            # Duas linhas de propósito: uma com o SLUG do motor, outra com o
            # NOME. Resolver pela coluna errada acha a linha errada em vez de
            # não achar nada, e o defeito passa a ter cara de sucesso.
            "criativo_motor": [
                {"id": "id-do-slug", "slug": "falso-teste"},
                {"id": "id-do-nome", "slug": "falso:teste"},
            ],
            "criativo_modo_de_producao": [{"id": "id-do-modo", "slug": "full_llm"}],
        }

    def __getattr__(self, nome: str) -> Any:
        return getattr(self._base, nome)

    async def listar_catalogo(self, tabela: str, colunas: str, ordem: str) -> Any:
        return self.tabelas.get(tabela, [])

    async def id_por_slug(self, tabela: str, coluna: str, valor: str) -> str | None:
        for linha in self.tabelas.get(tabela, []):
            if linha.get(coluna) == valor:
                return str(linha["id"])
        return None


@pytest.mark.anyio
async def test_o_executor_grava_motor_id_resolvido_pelo_SLUG(tmp_path):
    from test_criativo_execucao import PEDIDO, MotorFalso  # noqa: PLC0415

    from app.criativo.armazenamento import ArmazenamentoLocal, Assinador  # noqa: PLC0415
    from app.criativo.execucao import Executor  # noqa: PLC0415

    motor = MotorFalso()
    motor.slug = "falso-teste"  # `nome` é "falso:teste"; os dois existem no catálogo
    repo = RepoComCatalogo()
    executor = Executor(repo, ArmazenamentoLocal(tmp_path), motor, Assinador("s" * 32))

    job, criado = await executor.criar_job_de_imagem(PEDIDO, "usuario-1")

    assert criado is True
    assert job["motor_id"] == "id-do-slug", (
        "resolver por `nome` acharia `id-do-nome` — a linha errada, com cara de sucesso"
    )
    briefing = repo.briefings[job["briefing_id"]]
    assert briefing["modo_id"] == "id-do-modo"


@pytest.mark.anyio
async def test_catalogo_fora_do_ar_nao_impede_o_job_de_nascer(tmp_path):
    from test_criativo_execucao import PEDIDO, MotorFalso, RepoFalso  # noqa: PLC0415

    from app.criativo.armazenamento import ArmazenamentoLocal, Assinador  # noqa: PLC0415
    from app.criativo.execucao import Executor  # noqa: PLC0415

    # `RepoFalso` puro não conhece o parque: é o adaptador reduzido.
    executor = Executor(
        RepoFalso(), ArmazenamentoLocal(tmp_path), MotorFalso(), Assinador("s" * 32)
    )
    job, criado = await executor.criar_job_de_imagem(PEDIDO, "usuario-1")

    assert criado is True
    assert job["motor_id"] is None, "sem catálogo o vínculo é nulo e honesto"


# ═══════════════════════════════════════════════════════════════════════════
# 6. S1/S2/S3 e a divergência ampliada
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.anyio
async def test_coluna_nova_do_banco_nao_vaza_sozinha_para_a_api():
    """S2. O docstring de `apresentacao.py` promete montagem campo a campo; a
    compreensão de dicionário desfazia a promessa em uma linha."""
    catalogo = CatalogoFalso(
        {
            "criativo_motor": [
                {
                    "id": "m-1",
                    "slug": "gemini-imagem",
                    "nome": "Gemini",
                    "produz": ["imagem"],
                    "runtime": "volc_os",
                    "ativo": True,
                    # coluna que ninguém declarou publicar
                    "chave_secreta_interna": "nao-deve-sair",
                }
            ]
        }
    )
    dto = apresentacao.parque_dto(await Parque(catalogo).ler())
    publicado = dto["motores"][0]
    assert "chaveSecretaInterna" not in publicado
    assert "chave_secreta_interna" not in publicado
    assert publicado["slug"] == "gemini-imagem"


@pytest.mark.anyio
async def test_coluna_pedida_e_nao_devolvida_vira_none_e_nao_erro():
    catalogo = CatalogoFalso({"criativo_motor": [{"id": "m-1", "slug": "x"}]})
    dto = apresentacao.parque_dto(await Parque(catalogo).ler())
    assert dto["motores"][0]["custoReferenciaUsd"] is None


@pytest.mark.anyio
async def test_repositorio_sem_o_metodo_e_registrado_e_nao_confundido_com_falha(caplog):
    """S3. Ausência do método é pergunta que se responde ANTES de chamar; erro de
    dentro da chamada não pode ser confundido com ela."""
    import logging

    with caplog.at_level(logging.INFO):
        assert await Resolvedor(RepoSemCatalogo()).motor("gemini-imagem") is None
    assert any("nao implementa o catalogo" in r.message for r in caplog.records)


@pytest.mark.anyio
async def test_erro_de_dentro_do_repositorio_nao_e_silencioso(caplog):
    import logging

    class RepoQueQuebraPorDentro:
        base = "https://x.invalido"

        async def id_por_slug(self, *_: Any) -> str | None:
            raise AttributeError("regressão real dentro do repositório")

    # ⚠️ `AttributeError` de DENTRO não é mais engolido: sobe, porque é defeito.
    with pytest.raises(AttributeError):
        await Resolvedor(RepoQueQuebraPorDentro()).motor("gemini-imagem")


# ── divergência: os sete campos ─────────────────────────────────────────────


@pytest.mark.anyio
async def test_divergencia_pega_midia_diferente():
    catalogo = CatalogoFalso({"criativo_formato": [_formato("1x1", 1080, 1080, midia="video")]})
    leitura = await Parque(catalogo).ler()
    assert any("so sabe produzir `imagem`" in d.o_que for d in leitura.divergencias)


@pytest.mark.anyio
async def test_divergencia_pega_tipo_de_asset_diferente():
    """A exigência de canal é procurada por este campo: divergir aqui faz a peça
    ser conferida contra a regra errada, e passar."""
    catalogo = CatalogoFalso(
        {"criativo_formato": [_formato("1x1", 1080, 1080, tipo_de_asset="video")]}
    )
    leitura = await Parque(catalogo).ler()
    assert any("regra errada" in d.o_que for d in leitura.divergencias)


@pytest.mark.anyio
async def test_divergencia_pega_slot_desativado_que_o_executor_ainda_produz():
    catalogo = CatalogoFalso({"criativo_formato": [_formato("1x1", 1080, 1080, ativo=False)]})
    leitura = await Parque(catalogo).ler()
    assert any(d.banco == "inativo" for d in leitura.divergencias)


@pytest.mark.anyio
async def test_divergencia_pega_proporcao_que_mente_sobre_os_proprios_pixels():
    catalogo = CatalogoFalso(
        {"criativo_formato": [_formato("1x1", 1200, 628, proporcao="1:1")]}
    )
    leitura = await Parque(catalogo).ler()
    assert any("proprios pixels" in d.o_que for d in leitura.divergencias)


@pytest.mark.anyio
async def test_divergencia_pega_proporcao_ilegivel():
    catalogo = CatalogoFalso(
        {"criativo_formato": [_formato("1x1", 1080, 1080, proporcao="quadrado")]}
    )
    leitura = await Parque(catalogo).ler()
    assert any("nao da para ler" in d.o_que for d in leitura.divergencias)


# ── G11: o canvas nativo da PRENSA ──────────────────────────────────────────


def test_canvas_nativo_da_prensa_difere_e_precisa_de_renormalizacao():
    """G11. A PRENSA compõe `4x5` em 1088×1360 e o Estúdio declara 1080×1350.

    A PROPORÇÃO bate (1088/1360 = 1080/1350 = 0.8); o arquivo-base não. Um
    adaptador que herdasse pixels sem renormalizar entregaria dimensão que o
    Google Ads recusa.
    """
    from app.criativo.parque import canvas_a_renormalizar

    assert canvas_a_renormalizar("prensa", "4x5", 1080, 1350) == (1088, 1360)
    assert canvas_a_renormalizar("prensa", "1x1", 1080, 1080) == (1200, 1200)
    assert abs(1088 / 1360 - 1080 / 1350) < 1e-9, "a proporção é a mesma; o canvas não"


def test_motor_sem_canvas_proprio_nao_pede_renormalizacao():
    from app.criativo.parque import canvas_a_renormalizar

    assert canvas_a_renormalizar("gemini-imagem", "4x5", 1080, 1350) is None
    assert canvas_a_renormalizar("prensa", "9x16", 1080, 1920) is None
