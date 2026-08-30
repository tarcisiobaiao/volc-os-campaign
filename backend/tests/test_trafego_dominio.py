"""Provas do núcleo do inventário — e da costura entre ele e o schema.

Três famílias de teste, com propósitos diferentes:

1. **Domínio puro.** As três regras (frescor, ausência é `None`, isolamento por
   conta) exercitadas sem banco e sem rede.
2. **Costura com o SQL.** Os vocabulários do Python comparados aos das CHECK
   constraints de `v9_01`. Existem por causa de [E-21]: o vocabulário de canal
   divergia em **cinco** lugares, e a divergência só apareceu quando `PMAX`
   chegou num `getattr` e explodiu.
3. **Gate de acoplamento (SPEC §9.4).** Nenhum termo de canal específico dentro
   do núcleo — a dependência aponta sempre canal → núcleo, nunca o contrário.

As provas do banco (imutabilidade, append-only, acesso negativo com `SET ROLE`)
**não** estão aqui: elas exigem um Postgres e vivem em
`scripts/testar_migration_descartavel.sh`, que sobe um cluster descartável.
Simular gatilho em Python provaria o simulador, não o banco.
"""
from __future__ import annotations

import ast
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.trafego.dominio import (
    APELIDOS_DE_CANAL,
    CANAIS_COM_CONSTRUTOR,
    ESTADOS_DE_PRESENCA,
    PROCEDENCIAS,
    VOCABULARIO_DE_CANAL,
    Entrega,
    IdentidadeInvalida,
    LeituraAusente,
    canal_canonico,
    frescor_da_conta,
    frescor_do_conjunto,
    leitura,
    normalizar_campaign_id,
    normalizar_customer_id,
    presenca,
    preservar_ultima_entrega,
    teto_de_cliques,
)

RAIZ = Path(__file__).resolve().parents[2]
MIGRATION = RAIZ / "supabase" / "migrations" / "v9_01_trafego_inventario.sql"
DOMINIO = RAIZ / "backend" / "app" / "trafego" / "dominio.py"

AGORA = datetime(2026, 8, 24, 18, 0, tzinfo=timezone.utc)


# ===========================================================================
# 1. Identidade — o vazio que atravessou o filtro de nulos ([E-02], [E-10])
# ===========================================================================


@pytest.mark.parametrize("vazio", ["", "   ", "\t\n"])
def test_customer_id_vazio_vira_none_e_nao_string(vazio):
    """Vazio e nulo não são a mesma coisa, e achatá-los foi o defeito medido."""
    assert normalizar_customer_id(vazio) is None


def test_customer_id_none_continua_none():
    assert normalizar_customer_id(None) is None


def test_customer_id_do_painel_com_hifens_e_aceito_normalizado():
    assert normalizar_customer_id("801-785-1692") == "8017851692"


def test_customer_id_com_espacos_em_volta_e_limpo():
    assert normalizar_customer_id("  8017851692  ") == "8017851692"


@pytest.mark.parametrize("lixo", ["abc", "8017-85a-1692", "12345", "1" * 13])
def test_customer_id_corrompido_levanta_em_vez_de_virar_none(lixo):
    """Devolver `None` aqui promoveria lixo a "conta desconhecida" em silêncio.

    A diferença importa: `None` é uma afirmação ("não sei qual conta"), e ela
    não pode ser produzida por um erro de digitação que ninguém viu.
    """
    with pytest.raises(IdentidadeInvalida):
        normalizar_customer_id(lixo)


def test_campaign_id_e_obrigatorio():
    assert normalizar_campaign_id("24155134757") == "24155134757"
    for ruim in ("", "  ", None, "abc"):
        with pytest.raises(IdentidadeInvalida):
            normalizar_campaign_id(ruim)


# ===========================================================================
# 2. Canal — ADR-18: PMAX é apelido de tela, nunca valor de contrato
# ===========================================================================


def test_pmax_e_traduzido_para_o_nome_canonico():
    assert canal_canonico("PMAX") == "PERFORMANCE_MAX"
    assert canal_canonico("pmax") == "PERFORMANCE_MAX"


def test_canal_desconhecido_levanta_com_a_lista_do_que_existe():
    with pytest.raises(IdentidadeInvalida) as erro:
        canal_canonico("SEARCH_DINAMICO")
    assert "SEARCH" in str(erro.value)


def test_canal_ausente_e_none_e_nao_um_palpite():
    assert canal_canonico(None) is None
    assert canal_canonico("") is None


def test_so_search_tem_construtor():
    """[E-21]: existe um único construtor de grafo. O resto é declaração de estado."""
    assert CANAIS_COM_CONSTRUTOR == {"SEARCH"}
    assert CANAIS_COM_CONSTRUTOR < VOCABULARIO_DE_CANAL


# ===========================================================================
# 3. Frescor — regra A
# ===========================================================================


def test_nunca_lido_e_diferente_de_vazio_confirmado():
    """"Não perguntei" e "perguntei e não há nada" levam a ações opostas."""
    nunca = frescor_da_conta(
        resultado=None, lido_em=None, campanhas=None, agora=AGORA
    )
    vazio = frescor_da_conta(
        resultado="ok", lido_em=AGORA, campanhas=0, agora=AGORA
    )
    assert nunca == "nunca_lido"
    assert vazio == "vazio_confirmado"
    assert nunca != vazio


def test_leitura_boa_recente_e_velha():
    recente = frescor_da_conta(
        resultado="ok", lido_em=AGORA - timedelta(minutes=6), campanhas=2, agora=AGORA
    )
    velho = frescor_da_conta(
        resultado="ok", lido_em=AGORA - timedelta(hours=9), campanhas=2, agora=AGORA
    )
    assert (recente, velho) == ("recente", "velho")


def test_a_conta_e_o_conjunto_ordenam_os_estados_da_MESMA_forma():
    """As duas funções respondem à mesma pergunta em escalas diferentes.

    Se discordassem, uma conta sozinha apareceria com um rótulo e o envelope de
    uma conta só com outro — o sistema discordando de si mesmo na mesma tela.
    A ordem é: `parcial` antes de `velho`, `velho` antes de `vazio_confirmado`.
    """
    # Uma conta parcial E velha: `parcial` manda nas duas escalas.
    da_conta = frescor_da_conta(
        resultado="ok", lido_em=AGORA - timedelta(hours=9), campanhas=2,
        motivo="entrega(LAST_30_DAYS) não voltou", agora=AGORA)
    assert da_conta == "parcial"
    assert frescor_do_conjunto(["parcial", "velho"]) == "parcial"

    # Vazia E velha: `velho` manda nas duas.
    assert frescor_da_conta(
        resultado="ok", lido_em=AGORA - timedelta(hours=9), campanhas=0,
        agora=AGORA) == "velho"
    assert frescor_do_conjunto(["vazio_confirmado", "velho"]) == "velho"


def test_parcial_e_derivado_do_motivo_e_nao_de_um_terceiro_resultado():
    """`tentativa_resultado` tem DUAS palavras no banco; a varredura tem três.

    Numa tentativa `ok`, motivo preenchido só pode significar "deu certo, MENOS
    isto" — uma tentativa que deu certo inteira não tem o que explicar. Derivar
    evita uma coluna nova e, principalmente, evita duas fontes da mesma verdade.
    """
    sem_motivo = frescor_da_conta(resultado="ok", lido_em=AGORA, campanhas=2,
                                  agora=AGORA)
    com_motivo = frescor_da_conta(resultado="ok", lido_em=AGORA, campanhas=2,
                                  motivo="filhas(DISPLAY) sem adaptador",
                                  agora=AGORA)
    assert (sem_motivo, com_motivo) == ("recente", "parcial")
    # Motivo em branco não é motivo.
    assert frescor_da_conta(resultado="ok", lido_em=AGORA, campanhas=2,
                            motivo="   ", agora=AGORA) == "recente"


def test_resultado_ilegivel_degrada_para_velho_em_vez_de_derrubar_a_pagina():
    """Uma linha corrompida não pode custar o inventário inteiro.

    Levantar aqui seria o instinto — e o efeito seria o operador ficar sem
    NENHUMA conta na tela por causa de uma. `velho` faz ele conferir; `recente`
    faria ele confiar, que é o único desfecho inaceitável.
    """
    assert frescor_da_conta(resultado="quase", lido_em=AGORA, campanhas=1,
                            agora=AGORA) == "velho"


def test_ok_sem_carimbo_levanta_em_vez_de_virar_recente():
    """Regra A na origem: número sem data não sai do backend."""
    with pytest.raises(LeituraAusente):
        frescor_da_conta(resultado="ok", lido_em=None, campanhas=1, agora=AGORA)


# ---------------------------------------------------------------------------
# A TABELA COMPLETA DO FRESCOR DE CONJUNTO
#
# ⚠️ Havia DUAS regras para esta pergunta: esta função e `inventario.pior_frescor`,
# que era um `min` por gravidade. Para `{falhou, recente}` uma respondia `falhou`
# e a outra `parcial` — a diferença entre "o sistema caiu" e "uma conta de duas
# caiu", que são telas e ações opostas. `pior_frescor` foi removido.
#
# Um teste por amostra não teria pego a divergência: as amostras que existiam
# passavam nas duas. Por isso a tabela abaixo é EXAUSTIVA — os 2⁶ = 64
# subconjuntos do vocabulário, sem exceção. O resultado depende só do conjunto
# (nunca da ordem nem da repetição), e há um teste que prova isso também.
#
# A tabela é escrita pelo AVESSO, e a economia não é de espaço: 53 dos 64
# subconjuntos respondem `parcial`, e listá-los esconderia os 11 que importam
# no meio do ruído. O que está enumerado é a exceção; a regra geral é o resto.
# ---------------------------------------------------------------------------

FRESCORES_DO_VOCABULARIO = (
    "recente", "velho", "parcial", "falhou", "nunca_lido", "vazio_confirmado",
)

#: Os ÚNICOS subconjuntos que não respondem `parcial`. Cada linha é uma decisão
#: de produto, e o comentário diz qual.
NAO_PARCIAL: dict[frozenset[str], str] = {
    # Ninguém tentou.
    frozenset(): "nunca_lido",
    frozenset({"nunca_lido"}): "nunca_lido",
    # Todas tentaram e nenhuma respondeu. `falhou` domina `nunca_lido`: tentamos.
    frozenset({"falhou"}): "falhou",
    frozenset({"falhou", "nunca_lido"}): "falhou",
    # Todas responderam, e a resposta mais velha manda.
    frozenset({"velho"}): "velho",
    frozenset({"recente", "velho"}): "velho",
    frozenset({"velho", "vazio_confirmado"}): "velho",
    frozenset({"recente", "velho", "vazio_confirmado"}): "velho",
    # Todas responderam e nenhuma tinha campanha.
    frozenset({"vazio_confirmado"}): "vazio_confirmado",
    # Todas responderam e estão novas. `vazio_confirmado` junto de `recente` não
    # rebaixa: as duas contas foram lidas agora, uma tinha campanha e a outra não.
    frozenset({"recente"}): "recente",
    frozenset({"recente", "vazio_confirmado"}): "recente",
}


def _subconjuntos() -> list[frozenset[str]]:
    import itertools

    saida = []
    for n in range(len(FRESCORES_DO_VOCABULARIO) + 1):
        for combo in itertools.combinations(FRESCORES_DO_VOCABULARIO, n):
            saida.append(frozenset(combo))
    return saida


def test_tabela_de_frescor_do_conjunto():
    """Os 64 subconjuntos do vocabulário, um por um. Sem amostragem."""
    todos = _subconjuntos()
    assert len(todos) == 64, "o vocabulário mudou e a tabela não acompanhou"

    for conjunto in todos:
        esperado = NAO_PARCIAL.get(conjunto, "parcial")
        obtido = frescor_do_conjunto(sorted(conjunto))
        assert obtido == esperado, (
            f"{sorted(conjunto)} → {obtido!r}, esperado {esperado!r}")


def test_toda_chave_da_tabela_e_um_subconjunto_real():
    """A tabela não pode ganhar uma linha morta que ninguém exercita."""
    todos = set(_subconjuntos())
    assert set(NAO_PARCIAL) <= todos, set(NAO_PARCIAL) - todos


def test_a_resposta_depende_do_conjunto_e_nao_da_ordem_nem_da_repeticao():
    """É o que torna a tabela de 64 linhas uma cobertura COMPLETA.

    Se a função passasse a olhar quantas contas estão em cada estado — "duas de
    três falharam" —, a tabela deixaria de ser exaustiva no mesmo instante, e
    este teste é o que avisa.
    """
    for conjunto in _subconjuntos():
        base = sorted(conjunto)
        assert frescor_do_conjunto(base) == frescor_do_conjunto(list(reversed(base)))
        assert frescor_do_conjunto(base) == frescor_do_conjunto(base + base)


def test_nenhum_conjunto_com_conta_sem_resposta_sai_recente():
    """A invariante que o operador sente: nunca dizer "novo" sobre o que não veio."""
    for conjunto in _subconjuntos():
        if conjunto & {"falhou", "nunca_lido"}:
            assert frescor_do_conjunto(sorted(conjunto)) != "recente"


def test_falha_de_uma_conta_nao_derruba_o_conjunto():
    """Regra C. Três contas, uma falhou: a resposta é `parcial`, não `falhou`.

    Medido em 24/08: hoje três contas falhando é visualmente idêntico a "tudo
    bem" ([E-07]). O conserto não pode ser o extremo oposto — dizer que tudo
    caiu quando duas contas responderam apaga dado bom.
    """
    assert frescor_do_conjunto(["recente", "falhou", "vazio_confirmado"]) == "parcial"


def test_todas_as_contas_falharam():
    assert frescor_do_conjunto(["falhou", "falhou"]) == "falhou"


def test_nenhuma_conta_foi_lida():
    assert frescor_do_conjunto(["nunca_lido", "nunca_lido"]) == "nunca_lido"
    assert frescor_do_conjunto([]) == "nunca_lido"


def test_conta_nunca_lida_no_meio_de_contas_boas_tambem_e_parcial():
    assert frescor_do_conjunto(["recente", "nunca_lido"]) == "parcial"


def test_o_conjunto_nao_parece_mais_fresco_que_a_sua_parte_mais_velha():
    assert frescor_do_conjunto(["recente", "velho"]) == "velho"


def test_leitura_carrega_a_idade_calculada():
    lida = leitura(AGORA - timedelta(minutes=6), AGORA)
    assert lida is not None and lida.idade_s == 360
    assert leitura(None, AGORA) is None


# ===========================================================================
# 4. Presença — ADR-13, e a lacuna do vocabulário
# ===========================================================================


def test_linha_de_fevereiro_nasce_legado_nao_reconciliado():
    """[E-02]: sem conta, não sabemos onde procurar. Afirmar ausência inventaria
    uma medição que ninguém fez."""
    assert (
        presenca(
            customer_id=None,
            resultado_da_conta=None,
            encontrada_na_conta=None,
            nunca_reconciliada=True,
        )
        == "legado_nao_reconciliado"
    )


def test_sem_conta_depois_de_reconciliada_e_conta_nao_identificada():
    assert (
        presenca(
            customer_id=None,
            resultado_da_conta="ok",
            encontrada_na_conta=False,
            nunca_reconciliada=False,
        )
        == "conta_nao_identificada"
    )


def test_leitura_que_falhou_nao_vira_ausencia():
    """Não dá para afirmar presença nem ausência — e o vocabulário diz isso."""
    assert (
        presenca(
            customer_id="8017851692",
            resultado_da_conta="falhou",
            encontrada_na_conta=None,
        )
        == "sincronizacao_falhou"
    )


def test_conta_lida_e_campanha_ausente_e_nao_encontrada():
    assert (
        presenca(
            customer_id="8017851692",
            resultado_da_conta="ok",
            encontrada_na_conta=False,
        )
        == "nao_encontrada"
    )


def test_campanha_removida_pela_propria_conta():
    assert (
        presenca(
            customer_id="8017851692",
            resultado_da_conta="ok",
            encontrada_na_conta=True,
            estado_externo="REMOVED",
        )
        == "removida"
    )


def test_conta_fora_do_mcc_da_casa():
    assert (
        presenca(
            customer_id="5838529870",
            resultado_da_conta=None,
            encontrada_na_conta=None,
            conta_no_escopo=False,
        )
        == "fora_de_escopo"
    )


def test_campanha_presente_e_sem_ressalva_nao_tem_estado():
    """Os seis estados nomeiam exceções; nenhum nomeia o caso normal.

    É lacuna registrada, não descuido — inventar um sétimo termo aqui seria
    decidir sozinho um vocabulário que o contrato congelou.
    """
    assert (
        presenca(
            customer_id="8017851692",
            resultado_da_conta="ok",
            encontrada_na_conta=True,
            estado_externo="ENABLED",
        )
        is None
    )


def test_sem_leitura_nenhuma_a_presenca_levanta_em_vez_de_dizer_que_esta_tudo_bem():
    """A trava que impede "não perguntei" de virar "está tudo bem"."""
    with pytest.raises(LeituraAusente):
        presenca(
            customer_id="8017851692",
            resultado_da_conta=None,
            encontrada_na_conta=None,
        )


def test_nao_existe_sumiu_da_conta():
    assert "sumiu_da_conta" not in ESTADOS_DE_PRESENCA
    assert len(ESTADOS_DE_PRESENCA) == 6


# ===========================================================================
# 5. Entrega — regra B (ausência é None, nunca zero) e regra C
# ===========================================================================


def test_zero_medido_e_diferente_de_nao_medido():
    """[E-01]: as duas campanhas vivas tinham R$ 0,00 gastos. Esse zero é um
    fato, e ele só significa alguma coisa enquanto não puder ser confundido com
    falha de leitura."""
    medida = Entrega(impressoes=1, cliques=0, custo_micros=0, moeda="BRL", lida_em=AGORA)
    nao_medida = Entrega()
    assert medida.custo_micros == 0
    assert nao_medida.custo_micros is None
    assert medida.foi_medida and not nao_medida.foi_medida


def test_numero_de_entrega_sem_carimbo_e_recusado_na_construcao():
    with pytest.raises(LeituraAusente):
        Entrega(impressoes=1, cliques=0, custo_micros=0)


def test_falha_nova_nao_apaga_a_ultima_entrega_boa():
    boa = Entrega(
        impressoes=4, cliques=0, custo_micros=0, moeda="BRL",
        lida_em=AGORA - timedelta(minutes=40),
    )
    falhou = Entrega()
    preservada = preservar_ultima_entrega(falhou, boa)
    assert preservada.impressoes == 4
    assert preservada.lida_em == boa.lida_em, "o carimbo tem de viajar junto do número"


def test_medida_nova_substitui_a_antiga():
    antiga = Entrega(impressoes=1, custo_micros=0, lida_em=AGORA - timedelta(hours=2))
    nova = Entrega(impressoes=9, custo_micros=1200, lida_em=AGORA)
    assert preservar_ultima_entrega(nova, antiga).impressoes == 9


def test_medida_atrasada_nao_sobrescreve_a_mais_nova():
    nova = Entrega(impressoes=9, lida_em=AGORA)
    atrasada = Entrega(impressoes=1, lida_em=AGORA - timedelta(hours=3))
    assert preservar_ultima_entrega(atrasada, nova).impressoes == 9


def test_entrega_serializada_carrega_a_leitura():
    saida = Entrega(impressoes=1, lida_em=AGORA - timedelta(minutes=6)).como_dicionario(AGORA)
    assert saida["leitura"] == {"lido_em": "2026-08-24T17:54:00Z", "idade_s": 360}
    assert Entrega().como_dicionario(AGORA)["leitura"] is None


# ===========================================================================
# 6. Teto de cliques — o número só existe quando a premissa existe
# ===========================================================================


def test_teto_de_cliques_com_lance_manual():
    """[E-01]: verba R$ 10, lance R$ 0,12 → 83 cliques por dia."""
    assert teto_de_cliques(
        verba_diaria_micros=10_000_000, lance_micros=120_000, estrategia="MANUAL_CPC"
    ) == 83


def test_teto_de_cliques_nao_existe_com_lance_automatico():
    """Com lance automático o CPC varia leilão a leilão; verba ÷ lance seria
    um número de aparência precisa sobre uma premissa falsa."""
    assert teto_de_cliques(
        verba_diaria_micros=10_000_000,
        lance_micros=120_000,
        estrategia="MAXIMIZE_CONVERSIONS",
    ) is None


@pytest.mark.parametrize(
    "verba,lance", [(None, 120_000), (10_000_000, None), (10_000_000, 0)]
)
def test_teto_de_cliques_exige_os_dois_valores(verba, lance):
    assert teto_de_cliques(
        verba_diaria_micros=verba, lance_micros=lance, estrategia="MANUAL_CPC"
    ) is None


# ===========================================================================
# 7. Costura com o SQL — a divergência de vocabulário que [E-21] mediu
# ===========================================================================


def _lista_da_check(nome_da_constraint: str) -> set[str]:
    """Extrai os literais de uma CHECK ... IN (...) da migration."""
    sql = MIGRATION.read_text(encoding="utf-8")
    inicio = sql.index(f"CONSTRAINT {nome_da_constraint}")
    trecho = sql[inicio : sql.index("),", sql.index("IN (", inicio))]
    return set(re.findall(r"'([^']+)'", trecho[trecho.index("IN (") :]))


def test_vocabulario_de_presenca_igual_no_banco_e_no_dominio():
    assert _lista_da_check("trafego_espelho_presenca_conhecida") == set(
        ESTADOS_DE_PRESENCA
    )


def test_vocabulario_de_procedencia_igual_no_banco_e_no_dominio():
    assert _lista_da_check("trafego_campanha_procedencia_conhecida") == set(PROCEDENCIAS)


def test_vocabulario_de_canal_igual_no_banco_e_no_dominio():
    """Se estes dois divergirem, uma varredura legítima vira `sincronizacao_falhou`."""
    assert _lista_da_check("trafego_espelho_canal_canonico") == set(VOCABULARIO_DE_CANAL)


def test_apelido_de_tela_nao_e_valor_do_banco():
    """`PMAX` não pode existir no schema — ele não existe no enum do Google."""
    do_banco = _lista_da_check("trafego_espelho_canal_canonico")
    for apelido in APELIDOS_DE_CANAL:
        assert apelido not in do_banco


def test_toda_tabela_criada_passa_pelo_bloco_de_seguranca():
    """A tabela nova que esquecer o REVOKE nasce escrivel por `anon`.

    Medido em 24/08 (achado H da v8_07): `pg_default_acl` de `public` concede
    `arwdDxt` a `anon` em toda tabela nova. Uma tabela fora do laço de
    segurança não é um descuido de estilo — é uma tabela aberta ao navegador.
    """
    sql = MIGRATION.read_text(encoding="utf-8")
    criadas = set(re.findall(r"CREATE TABLE public\.(trafego_\w+)", sql))
    bloco = sql[sql.index("DO $seguranca$") : sql.index("$seguranca$;")]
    protegidas = set(re.findall(r"'(trafego_\w+)'", bloco))
    assert criadas, "nenhuma tabela encontrada — o regex ficou desatualizado"
    assert criadas <= protegidas, f"fora do bloco de segurança: {criadas - protegidas}"


def test_nenhum_delete_e_concedido_no_sql():
    """Não há caminho de apagamento no domínio: presença substitui exclusão."""
    sql = MIGRATION.read_text(encoding="utf-8")
    grants = re.findall(r"GRANT ([A-Z, ]+?) ON TABLE", sql)
    assert grants
    assert not any("DELETE" in g or "TRUNCATE" in g for g in grants)


# ===========================================================================
# 8. Gate de acoplamento — SPEC §9.4, verificação mecânica
# ===========================================================================


def _codigo_sem_prosa(arquivo: Path) -> str:
    """O arquivo sem comentários e sem docstrings.

    O gate do SPEC §9.4 mede **código**, não prosa. Um `grep` cru reprovaria
    este próprio módulo, que cita os termos proibidos exatamente para explicar
    que não os usa — e um gate que castiga a documentação da regra ensina a
    apagar a documentação.
    """
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        corpo = getattr(no, "body", None)
        if not isinstance(corpo, list) or not corpo:
            continue
        primeiro = corpo[0]
        if (
            isinstance(primeiro, ast.Expr)
            and isinstance(primeiro.value, ast.Constant)
            and isinstance(primeiro.value.value, str)
        ):
            corpo.pop(0)
    return ast.unparse(arvore).lower()


def test_nucleo_nao_conhece_semantica_de_canal():
    """"Nenhum tipo do núcleo importa um tipo de canal." O teste é mecânico.

    Se este teste falhar, o núcleo vazou — e o conserto é no núcleo, não no
    canal que o fez vazar.
    """
    proibidos = ("keyword", "asset_group", "placement", "audience", "match_type")
    codigo = _codigo_sem_prosa(DOMINIO)
    encontrados = [p for p in proibidos if p in codigo]
    assert not encontrados, f"vocabulário de canal dentro do núcleo: {encontrados}"


def test_dominio_nao_importa_framework_nem_io():
    """Domínio puro: sem FastAPI, sem httpx, sem Supabase, sem pydantic."""
    texto = DOMINIO.read_text(encoding="utf-8")
    importados = set(re.findall(r"^\s*(?:from|import)\s+([\w.]+)", texto, re.M))
    permitidos = {"__future__", "dataclasses", "datetime", "typing"}
    assert importados <= permitidos, f"import indevido no domínio: {importados - permitidos}"


def test_frescor_desconhecido_nao_vira_recente():
    """Valor fora do vocabulário não pode sair como o estado mais otimista.

    O `return "recente"` era o ramo PADRÃO de `frescor_do_conjunto`, não um ramo
    condicional: um typo, uma coluna nova ou um valor vindo de uma versão futura
    do snapshot saíam como "recente" — a promessa de que o número na tela é
    novo, emitida por omissão.

    Frescor errado para o lado otimista é o pior erro que este sistema pode
    cometer, porque ele não parece erro: a tela fica igual, e a decisão de gasto
    acontece em cima de um número velho com cara de fresco.
    """
    from app.trafego.dominio import frescor_do_conjunto

    assert frescor_do_conjunto(["recente", "recente"]) == "recente"
    # Um valor que ninguém reconhece não pode arrastar o conjunto para cima.
    assert frescor_do_conjunto(["recente", "estado_do_futuro"]) == "velho"
    assert frescor_do_conjunto(["Recente"]) == "velho", (
        "diferença de caixa não é reconhecimento — 'Recente' não está no vocabulário"
    )
    # E o caminho conhecido continua intacto.
    assert frescor_do_conjunto(["recente", "falhou"]) == "parcial"
    assert frescor_do_conjunto(["falhou", "falhou"]) == "falhou"
    assert frescor_do_conjunto([]) == "nunca_lido"
