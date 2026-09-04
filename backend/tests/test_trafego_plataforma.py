"""O manifesto de canal: o que o Hub sabe fazer, contra o que ele de fato faz.

Um manifesto que declara capacidade sem consumidor é código morto com nome
bonito (ADR-19). Um que declara capacidade que o engine não tem é pior: a tela
oferece, o operador monta o pedido inteiro, e a ausência aparece como erro 500.

Por isso as provas aqui comparam a DECLARAÇÃO com a REALIDADE do repositório —
não com outra declaração.
"""
from __future__ import annotations

import ast
import os
import pathlib
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.trafego import dominio as dom  # noqa: E402
from app.trafego import plataforma as plat  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parents[2]


# ═══════════════════════════════════════════════════════════════════════════
# 1. VOCABULÁRIO
# ═══════════════════════════════════════════════════════════════════════════


def test_as_duas_plataformas_e_nada_alem():
    """Uma terceira entra quando houver conta, credencial e leitura."""
    assert plat.PLATAFORMAS == ("GOOGLE_ADS", "META_ADS")


def test_os_quatro_canais_google_com_o_nome_canonico():
    canais = {m.canal for m in plat.manifestos_de(plat.GOOGLE_ADS)}
    assert canais == {"SEARCH", "DISPLAY", "DEMAND_GEN", "PERFORMANCE_MAX"}


def test_pmax_nao_e_valor_de_contrato_em_lugar_nenhum():
    """`PMAX` é apelido de tela e nunca valor de contrato (ADR-18).

    Ele não existe no enum do Google nem no engine — um pedido com esse valor
    falharia no `getattr`, tarde e com mensagem ruim.
    """
    assert all(m.canal != "PMAX" for m in plat._MANIFESTOS.values())
    # E o apelido continua sendo traduzido na fronteira, não recusado: um link
    # antigo com `PMAX` na URL precisa abrir.
    assert plat.manifesto(plat.GOOGLE_ADS, "PMAX") is plat.PERFORMANCE_MAX
    assert plat.manifesto(plat.GOOGLE_ADS, "pmax") is plat.PERFORMANCE_MAX


def test_o_nivel_do_meta_e_conjunto_e_nao_grupo():
    """Traduzir o vocabulário do Meta para o do Google faria o operador procurar
    no painel do Meta uma palavra que não existe lá."""
    assert plat.CONJUNTO in plat.META.hierarquia
    assert plat.GRUPO not in plat.META.hierarquia
    assert plat.GRUPO in plat.SEARCH.hierarquia


# ═══════════════════════════════════════════════════════════════════════════
# 2. O MANIFESTO CONTRA O ENGINE
# ═══════════════════════════════════════════════════════════════════════════


def test_canais_de_mutacao_real_batem_com_o_engine():
    """Search e Display podem chegar ao executor; Demand Gen só pode provar.

    Se alguém acrescentar um construtor sem atualizar o manifesto, a tela
    continuará escondendo uma capacidade que passou a existir. Se atualizar o
    manifesto sem o construtor, a tela oferecerá o que não existe. As duas
    direções derrubam este teste.
    """
    sabem_criar = {m.canal for m in plat._MANIFESTOS.values() if m.sabe_criar}

    # O registro REAL de quem sabe construir vive no engine
    # (`volc_ads/subir.py:CONSTRUTORES_POR_CANAL`), e é ele que a porta de
    # criação consulta. O manifesto é a mesma verdade dita para a TELA — e duas
    # verdades sobre o mesmo fato é o defeito, não a solução.
    #
    # Lido por árvore sintática e não por import: `volc_ads/subir.py` importa o
    # SDK do Google no topo, e uma prova de arquitetura não pode depender de a
    # máquina ter a biblioteca instalada. Um teste que pula por falta de
    # dependência é um teste que não protege nada.
    fonte = (RAIZ / "volc_ads" / "subir.py").read_text(encoding="utf-8")
    registro = None
    for no in ast.walk(ast.parse(fonte)):
        if (isinstance(no, ast.Assign)
                and any(getattr(a, "id", "") == "CONSTRUTORES_POR_CANAL"
                        for a in no.targets)
                and isinstance(no.value, ast.Dict)):
            registro = {k.value for k in no.value.keys
                        if isinstance(k, ast.Constant)}
    assert registro is not None, (
        "não achei `CONSTRUTORES_POR_CANAL` em volc_ads/subir.py — se ele mudou "
        "de nome, este teste precisa acompanhar ou deixa de proteger")

    assert sabem_criar == registro, (
        f"o manifesto diz que {sorted(sabem_criar)} sabem criar e o engine "
        f"registra {sorted(registro)}. Se o manifesto sobrar, a tela oferece o "
        f"que não existe; se faltar, ela esconde uma capacidade real")


def test_canais_de_prova_batem_com_a_vista_separada_do_engine():
    sabem_provar = {m.canal for m in plat._MANIFESTOS.values() if m.sabe_provar}
    fonte = (RAIZ / "volc_ads" / "subir.py").read_text(encoding="utf-8")
    registro = None
    for no in ast.walk(ast.parse(fonte)):
        if (isinstance(no, ast.Assign)
                and any(getattr(a, "id", "") == "PROVADORES_POR_CANAL"
                        for a in no.targets)
                and isinstance(no.value, ast.Dict)):
            registro = {k.value for k in no.value.keys
                        if isinstance(k, ast.Constant)}
    assert registro is not None
    assert sabem_provar == registro == {"SEARCH", "DISPLAY", "DEMAND_GEN"}
    assert plat.DEMAND_GEN.sabe_provar is True
    assert plat.DEMAND_GEN.sabe_criar is False
    assert plat.exigir_provador(plat.GOOGLE_ADS, "DEMAND_GEN") is plat.DEMAND_GEN
    with pytest.raises(ValueError):
        plat.exigir_construtor(plat.GOOGLE_ADS, "DEMAND_GEN")


def test_manifesto_json_nao_colapsa_prova_em_criacao():
    corpo = plat.DEMAND_GEN.json()
    assert corpo["sabe_provar"] is True
    assert corpo["sabe_criar"] is False
    assert "intencoes" in corpo["campos_do_pedido"]
    assert "exclusoes_de_audiencia" in corpo["campos_do_pedido"]


def test_nenhum_canal_declara_escrita():
    """Nenhuma regra de bidding, graduação ou automação está aprovada (ADR-11).

    O degrau existe no vocabulário para que a porta de escrita, quando existir,
    seja recusada por ausência DECLARADA em vez de por um `if` esquecido.
    """
    for m in plat._MANIFESTOS.values():
        assert not m.pode(plat.ESCREVER), f"{m.canal} declara escrita"


def test_escrever_sem_propor_e_recusado_na_construcao():
    """Escrever sem propor é escrever sem antes/depois, validação e autorização.

    A escada não é sugestão: ela é a diferença entre uma mudança que alguém
    autorizou e uma que apareceu na conta.
    """
    with pytest.raises(ValueError, match="escada"):
        plat.ManifestoDeCanal(
            plataforma=plat.GOOGLE_ADS, canal="SEARCH", rotulo="x",
            hierarquia=(plat.CAMPANHA,),
            capacidades=(plat.LER, plat.ESCREVER))


def test_meta_nao_declara_nem_leitura():
    """`capacidades=()` impede a tela de mostrar "0 campanhas" para o Meta.

    Zero afirmaria uma leitura que ninguém fez. Não há credencial, não há
    adaptador, não há conta ligada.
    """
    assert plat.META.capacidades == ()
    assert plat.META.indisponibilidades


def test_recusa_de_canal_sem_construtor_diz_o_que_existe():
    """A diferença entre "não deu certo" e uma recusa que ensina."""
    with pytest.raises(ValueError) as exc:
        plat.exigir_construtor(plat.GOOGLE_ADS, "PERFORMANCE_MAX")
    mensagem = str(exc.value)
    assert "Search" in mensagem, "a recusa não diz o que existe"
    assert "HTTP" in mensagem

    with pytest.raises(ValueError) as exc2:
        plat.exigir_construtor(plat.GOOGLE_ADS, "TIKTOK")
    assert "SEARCH" in str(exc2.value)


def test_search_passa_pela_porta_de_criacao():
    m = plat.exigir_construtor(plat.GOOGLE_ADS, "SEARCH")
    assert m.sabe_criar
    assert "selo" in m.provas_obrigatorias, (
        "sem `validate_only` na conta real, montar o pedido não é ter o direito "
        "de gastar")


# ═══════════════════════════════════════════════════════════════════════════
# 3. IDENTIDADE
# ═══════════════════════════════════════════════════════════════════════════


def test_a_identidade_externa_inclui_a_plataforma():
    """Ids externos são numéricos nas duas plataformas, e nada impede que Google
    e Meta emitam o mesmo número.

    Sem a plataforma na trinca, duas campanhas diferentes viveriam sob a mesma
    identidade externa e a atribuição de receita de uma iria para a outra — sem
    nada denunciando.
    """
    google = plat.IdentidadeDeCampanha(
        volc_campaign_id="gads-8017851692-1", plataforma=plat.GOOGLE_ADS,
        conta_externa="8017851692", id_externo="1")
    meta = plat.IdentidadeDeCampanha(
        volc_campaign_id="meta-999-1", plataforma=plat.META_ADS,
        conta_externa="999", id_externo="1")
    assert google.chave_externa != meta.chave_externa


def test_conta_externa_nula_e_estado_real_e_nao_erro():
    """Há linhas legadas sem conta declarada. Afirmar uma seria inventar."""
    i = plat.IdentidadeDeCampanha(
        volc_campaign_id="legado-1", plataforma=plat.GOOGLE_ADS,
        conta_externa=None, id_externo="23518009650")
    assert i.chave_externa == (plat.GOOGLE_ADS, None, "23518009650")


def test_identidade_recusa_plataforma_inventada():
    with pytest.raises(ValueError, match="plataforma"):
        plat.IdentidadeDeCampanha(
            volc_campaign_id="x", plataforma="TIKTOK_ADS",
            conta_externa="1", id_externo="1")


def test_identidade_nao_tem_nome():
    """Nome muda, é editável por qualquer pessoa no painel, e é a primeira coisa
    que alguém renomeia."""
    campos = plat.IdentidadeDeCampanha.__dataclass_fields__
    assert "nome" not in campos and "name" not in campos


# ═══════════════════════════════════════════════════════════════════════════
# 4. A REGRA DE ACOPLAMENTO — o gate mecânico do SPEC §9.4
# ═══════════════════════════════════════════════════════════════════════════


#: Os módulos que SÃO o núcleo. Nenhum deles pode manipular tipo de canal.
NUCLEO = (
    "app/trafego/dominio.py",
    "app/trafego/inventario.py",
    "app/trafego/sincronizador.py",
    "app/trafego/persistencia.py",
    "app/trafego/reconciliacao.py",
    "app/trafego/plataforma.py",
)

#: As palavras que denunciam vazamento de canal para dentro do núcleo.
CONCEITOS_DE_CANAL = ("asset_group", "placement", "audience", "ad_set",
                      "match_type", "listing_group")


@pytest.mark.parametrize("relativo", NUCLEO)
def test_o_nucleo_nao_manipula_conceito_de_canal(relativo):
    """"Procurar `keyword`, `asset_group`, `placement`, `audience` nos módulos
    do núcleo deve dar zero. Se der, o núcleo vazou." (SPEC §9.4)

    A prova roda sobre o CÓDIGO, com as docstrings removidas pela árvore
    sintática: explicar por que o núcleo não conhece asset group é o oposto de
    conhecê-lo, e um teste que confunde as duas coisas obriga a documentação a
    mentir por omissão.
    """
    caminho = pathlib.Path(__file__).resolve().parents[1] / relativo
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))

    for no in ast.walk(arvore):
        if isinstance(no, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                           ast.ClassDef)):
            corpo = getattr(no, "body", [])
            if (corpo and isinstance(corpo[0], ast.Expr)
                    and isinstance(corpo[0].value, ast.Constant)
                    and isinstance(corpo[0].value.value, str)):
                corpo.pop(0)

    codigo = ast.unparse(arvore)
    for conceito in CONCEITOS_DE_CANAL:
        # `plataforma.py` NOMEIA os níveis como rótulos de tela — é o registro
        # que diz que Performance Max desce por asset group. Nomear não é
        # manipular: ele nunca importa, constrói ou lê a entidade.
        if relativo.endswith("plataforma.py") and conceito == "asset_group":
            continue
        assert conceito.upper() not in codigo.upper(), (
            f"{relativo} manipula {conceito!r}: o núcleo vazou para dentro de "
            f"um canal, e um canal novo passa a exigir varredura pelo produto "
            f"inteiro")


def test_o_nucleo_nao_importa_modulo_de_canal():
    """A dependência aponta SEMPRE canal → núcleo (ADR-17).

    O import tardio dentro de `resolver_perfil` é a única exceção, e ela existe
    justamente para o núcleo não citar Search em tempo de carga.
    """
    for relativo in NUCLEO:
        caminho = pathlib.Path(__file__).resolve().parents[1] / relativo
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        for no in arvore.body:          # só o nível de módulo
            if isinstance(no, (ast.Import, ast.ImportFrom)):
                alvos = [a.name for a in no.names] + [getattr(no, "module", "") or ""]
                for alvo in alvos:
                    assert "adaptador_" not in alvo, (
                        f"{relativo} importa {alvo!r} no topo — a dependência "
                        f"inverteu")


def test_o_manifesto_nao_importa_o_engine():
    """Ele DESCREVE o que o engine faz; descrever não é depender.

    A prova é sobre os imports, e não sobre o texto: citar
    `volc_ads/campanha/search.py` numa docstring é exatamente o rastro que
    permite conferir a declaração contra a realidade. Proibir a citação
    obrigaria o manifesto a afirmar capacidades sem dizer onde conferi-las.
    """
    arvore = ast.parse((pathlib.Path(__file__).resolve().parents[1]
                        / "app/trafego/plataforma.py").read_text(encoding="utf-8"))
    importados = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            importados += [a.name for a in no.names]
        elif isinstance(no, ast.ImportFrom):
            importados.append(no.module or "")
    assert not [i for i in importados if "volc_ads" in i], importados
    # E ele também não alcança o engine por caminho de arquivo em tempo de
    # execução — o único uso da raiz do repositório está nos TESTES.
    codigo = ast.unparse(arvore)
    assert "importlib" not in codigo and "__import__" not in codigo


# ═══════════════════════════════════════════════════════════════════════════
# 5. COSTURA COM O VOCABULÁRIO QUE JÁ EXISTIA
# ═══════════════════════════════════════════════════════════════════════════


def test_o_canal_do_manifesto_existe_no_vocabulario_do_dominio():
    """Um canal declarado aqui e desconhecido lá seria recusado pela CHECK do
    banco na primeira gravação."""
    for m in plat.manifestos_de(plat.GOOGLE_ADS):
        assert m.canal in dom.VOCABULARIO_DE_CANAL, m.canal


def test_o_tipo_Canal_do_front_bate_com_o_que_a_api_emite():
    """A docstring de `CANAIS_DO_CONTRATO` diz que ela É o tipo `Canal` do TS.

    Ela dizia isso e as duas discordavam: o backend emitia seis valores e o tipo
    declarava quatro. Quem tipasse a resposta veria `canal: 'VIDEO'` num campo
    que o TypeScript jura ser um dos quatro — o compilador não acusa, porque a
    mentira está na fronteira do `fetch`.

    Ter manifesto é outra coisa, e são quatro. A assimetria é deliberada: o
    inventário espelha o que a conta responde, e esconder uma campanha de Vídeo
    seria mentir sobre o que está gastando.
    """
    import re

    ts = (RAIZ / "src" / "types" / "trafego.ts").read_text(encoding="utf-8")

    def _lista(nome: str) -> set:
        i = ts.index(f"export const {nome}")
        return set(re.findall(r"'([A-Z_]+)'", ts[i:ts.index("];", i)]))

    assert _lista("CANAIS") == set(dom.CANAIS_DO_CONTRATO)
    assert _lista("CANAIS_COM_MANIFESTO") == {
        m.canal for m in plat.manifestos_de(plat.GOOGLE_ADS)}


def test_o_canal_do_meta_nao_polui_o_vocabulario_do_google():
    """`VOCABULARIO_DE_CANAL` é o enum do Google, e o Meta não está nele.

    Misturar os dois faria a CHECK do espelho aceitar um valor que a conta do
    Google nunca responde — e o espelho existe para registrar honestamente o que
    a conta respondeu.
    """
    assert plat.META.canal not in dom.VOCABULARIO_DE_CANAL
