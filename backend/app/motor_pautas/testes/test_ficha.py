"""A derivação: contagem entra, eixo sai, e o portão é consequência.

O que estes testes protegem não é a escala — é a PROPRIEDADE que a troca
comprou: dada a mesma contagem, o nível é sempre o mesmo. A instabilidade que
sobrar depois disso é da contagem, e contagem sobre um texto escrito é
verificável de um jeito que rótulo sobre sentimento não é.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from app.validacao.ficha import Ficha, comparar, derivar


def f(**kw):
    base = dict(condicoes_pessoais=0, ramos_de_acao=1, fontes_oficiais=1,
                decisao_apos_resposta=False, oficial_fecha_sozinho=False,
                regra_mudou_recentemente=False, stake=True, descobre_que_existe=False)
    return Ficha(**{**base, **kw})


# ── o portão, que agora é aritmética ───────────────────────────────────────

def test_portao_e_consequencia_das_contagens():
    """`Registrato`: um caminho, nada da situação dela, nada a decidir depois.

    MEDIDO no desenho anterior: o formulário de nove eixos perdia este caso em
    4 de 5 execuções, chamando de `sequencial` porque descrevia os PASSOS da
    consulta. Aqui não há o que perder de vista — os passos de UM caminho são
    um ramo, e um ramo com zero condições é o portão.
    """
    assert derivar(f())["engajamento"] == "dado_unico"
    # passos do mesmo caminho continuam sendo um ramo
    assert derivar(f(fontes_oficiais=3))["engajamento"] == "dado_unico"


def test_o_que_tira_do_portao():
    """Só duas coisas tiram: ramificar, ou sobrar decisão."""
    assert derivar(f(ramos_de_acao=2))["engajamento"] != "dado_unico"
    assert derivar(f(decisao_apos_resposta=True))["engajamento"] != "dado_unico"


def test_pre_requisito_de_acesso_nao_tira_do_portao():
    """`Registrato`, medido: a ficha contou 1 condição pessoal.

    "faça login com sua conta Gov.br nível prata ou ouro" É um fato da situação
    dela, então a contagem estava certa. Mas é PRÉ-REQUISITO DE ACESSO, não
    ramificação: a resposta continua se esgotando em segundos, que é o mecanismo
    inteiro. A regra exigia `condicoes == 0` e perdia o arquétipo mais limpo do
    lote nas duas passadas.
    """
    assert derivar(f(condicoes_pessoais=1))["engajamento"] == "dado_unico"
    assert derivar(f(condicoes_pessoais=3))["engajamento"] == "dado_unico"


def test_sem_stake_e_portao_de_ignorancia():
    """Hiato máximo e nada em jogo não paga: quem busca a novela não lê o resto."""
    assert derivar(f(stake=False, descobre_que_existe=True))["ignorancia"] == "nao_preciso_de_nada"


# ── cada eixo sai de observáveis DISTINTOS ────────────────────────────────

def test_eixos_nao_se_sobrepoem():
    """Era a sobreposição que obrigava o prompt antigo a proibir combinações.

    `fontes_oficiais` move `opacidade` e não toca em `engajamento`;
    `ramos_de_acao` move `engajamento` e não toca em `opacidade`.
    """
    a, b = derivar(f(fontes_oficiais=1)), derivar(f(fontes_oficiais=3))
    assert a["opacidade"] != b["opacidade"]
    assert a["engajamento"] == b["engajamento"]

    c, d = derivar(f(ramos_de_acao=1)), derivar(f(ramos_de_acao=3))
    assert c["engajamento"] != d["engajamento"]
    assert c["opacidade"] == d["opacidade"]


def test_regra_recem_mudada_vence_canal_limpo():
    """O site oficial pode estar límpido e desatualizado."""
    assert derivar(f(oficial_fecha_sozinho=True,
                     regra_mudou_recentemente=True))["opacidade"] == "regra_mudou"


# ── a ficha recusa o que não é observável ─────────────────────────────────

def test_booleano_entre_aspas_invalida_a_ficha_inteira():
    """`"false"` é verdadeiro em Python: uma ficha assim seria lida ao contrário."""
    bom = {"condicoes_pessoais": 1, "ramos_de_acao": 2, "fontes_oficiais": 1,
           "decisao_apos_resposta": True, "oficial_fecha_sozinho": False,
           "regra_mudou_recentemente": False, "stake": True, "descobre_que_existe": False}
    assert Ficha.de_json(bom) is not None
    assert Ficha.de_json({**bom, "stake": "false"}) is None
    assert Ficha.de_json({**bom, "condicoes_pessoais": "duas"}) is None
    assert Ficha.de_json({k: v for k, v in bom.items() if k != "ramos_de_acao"}) is None


def test_contagem_satura_em_tres():
    assert Ficha.de_json({"condicoes_pessoais": 9, "ramos_de_acao": 1, "fontes_oficiais": 1,
                          "decisao_apos_resposta": False, "oficial_fecha_sozinho": False,
                          "regra_mudou_recentemente": False, "stake": True,
                          "descobre_que_existe": False}).condicoes_pessoais == 3


# ── duas passadas comparam CONTAGEM, não prosa ────────────────────────────

def test_comparacao_ignora_a_prosa_e_olha_os_numeros():
    """Duas passadas podem escrever a mesma resposta com outras palavras."""
    a = f(resposta_literal="O prazo é 31 de outubro.")
    b = f(resposta_literal="Vai até 31/10.")
    c = comparar(a, b)
    assert c["contagens_iguais"] and c["eixos_iguais"]
    assert c["portao_passada_1"] and c["portao_passada_2"]


def test_divergencia_de_contagem_aparece_nomeada():
    c = comparar(f(ramos_de_acao=1), f(ramos_de_acao=3))
    assert not c["contagens_iguais"]
    assert c["divergencias"] == {"ramos_de_acao": [1, 3]}
    # e ela muda o portão: um lado dispara, o outro não -> limítrofe
    assert c["portao_passada_1"] and not c["portao_passada_2"]


# ── a entidade não tem UMA pergunta ────────────────────────────────────────

def test_uma_pergunta_de_data_nao_mata_a_entidade():
    """`DIRPF`, medido: congelado em "Quando libera a declaração de 2026?" a
    ficha devolveu uma DATA, o portão disparou, e a entidade mais rica do lote
    morreu. A contagem estava certa; o objeto é que era outro.
    """
    from app.validacao.ficha import agregar, veredito_do_portao

    dirpf = {
        "Quando libera a declaração de 2026?": f(),                       # data
        "Quem precisa declarar?": f(condicoes_pessoais=3, ramos_de_acao=2),
        "Simplificada ou completa?": f(ramos_de_acao=2, condicoes_pessoais=2,
                                       decisao_apos_resposta=True),
    }
    e = agregar(dirpf)
    assert e.share_dado_unico < 0.5
    assert veredito_do_portao(e.share_dado_unico, len(e.fichas)) == "sem_portao"
    # e os eixos vêm da pergunta mais rica, que é a página que se escreveria.
    # Com a escala em dois estados quem escolhe é a CONTAGEM CRUA: "Quem
    # precisa declarar?" soma 5 (3 condições + 2 ramos) e "Simplificada ou
    # completa?" soma 6 (2 + 2 + decisão). Sem inventar ordinalidade.
    assert e.niveis["engajamento"] == "sustenta"
    assert e.pergunta_mais_rica == "Simplificada ou completa?"


def test_entidade_que_so_tem_lookup_morre():
    """`Registrato`: todas as perguntas do PAA se esgotam. Aí sim é portão."""
    from app.validacao.ficha import agregar, veredito_do_portao

    reg = {"Como olhar se meu nome está?": f(condicoes_pessoais=1),
           "O que é o Registrato?": f(),
           "Como acessar?": f(fontes_oficiais=2)}
    e = agregar(reg)
    assert e.share_dado_unico == 1.0
    assert veredito_do_portao(e.share_dado_unico, len(e.fichas)) == "portao"


def test_metade_esgotando_pede_humano():
    from app.validacao.ficha import agregar, veredito_do_portao

    meio = {"a": f(), "b": f(), "c": f(ramos_de_acao=2), "d": f(decisao_apos_resposta=True)}
    e = agregar(meio)
    assert e.share_dado_unico == 0.5
    assert veredito_do_portao(e.share_dado_unico, len(e.fichas)) == "limitrofe"


def test_uma_pergunta_so_nao_dispara_o_portao():
    """`consultar CPF`: a SERP voltou SEM bloco de PAA numa rodada (tinha 2 na
    anterior), a entidade caiu no fallback do próprio termo, e `1/1 = 1,0`
    satisfez a regra de unanimidade — que a n=1 não exige nada.

    Uma SERP sem PAA não pode ter a mesma consequência que uma entidade medida
    e reprovada. Abaixo do piso o teto é `limitrofe`: humano olha.
    """
    from app.validacao.ficha import (N_MINIMO_PARA_PORTAO, agregar,
                                     veredito_do_portao)

    seca = f()  # 1 ramo, 0 condições, nada a decidir depois
    uma = agregar({"consultar CPF situação cadastral": seca})
    assert uma.share_dado_unico == 1.0
    assert veredito_do_portao(uma.share_dado_unico, 1) == "limitrofe"

    # com o PAA inteiro esgotando, aí sim é a entidade e não a SERP
    n = N_MINIMO_PARA_PORTAO
    muitas = agregar({f"pergunta {i}": f() for i in range(n)})
    assert muitas.share_dado_unico == 1.0
    assert veredito_do_portao(muitas.share_dado_unico, n) == "portao"


# ── a citação, e a assimetria dela ─────────────────────────────────────────

def test_citacao_que_nao_esta_no_texto_e_detectada():
    """A ideia inteira: trecho é RECORTE, e recorte se confere com `in`.

    Paráfrase e invenção caem no mesmo lado — não estão no texto — e é isso que
    separa contagem conferível de contagem que ninguém pode contestar.
    """
    from app.validacao.ficha import Ficha

    f = Ficha(
        resposta_literal="Você pode sacar se optou pelo saque-aniversário "
                         "e se já passou a carência de 90 dias.",
        trechos_citados={
            "condicoes_pessoais": "se optou pelo saque-aniversário",   # literal
            "ramos_de_acao": "o texto menciona duas condições",        # paráfrase
            "stake": "",                                               # vazio
        })
    conf = f.citacoes_conferem()
    assert conf["condicoes_pessoais"] is True
    assert conf["ramos_de_acao"] is False
    assert conf["stake"] is False
    # normalização de espaço não pode produzir falso negativo
    g = Ficha(resposta_literal="O prazo   é 31\nde outubro.",
              trechos_citados={"stake": "o prazo é 31 de outubro"})
    assert g.citacoes_conferem()["stake"] is True


def test_regra_mudou_sem_ancora_cai_e_stake_sem_ancora_nao():
    """A assimetria é deliberada, e ela existe porque os dois erram para lados
    de custo diferentes.

    `regra_mudou_recentemente` é o TOPO de `opacidade`: sem âncora, rebaixar é
    conservador. `stake=False` é PORTÃO: rebaixar por falta de citação mataria
    o tema por ausência de prova, e ausência de prova não é prova.
    """
    from app.validacao.ficha import Ficha, derivar

    base = dict(resposta_literal="O prazo é 31 de outubro.",
                condicoes_pessoais=0, ramos_de_acao=1, fontes_oficiais=1,
                decisao_apos_resposta=False, oficial_fecha_sozinho=False,
                stake=True, descobre_que_existe=False, tensao="nenhuma")

    sem_ancora = Ficha.de_json({**base, "regra_mudou_recentemente": True})
    assert sem_ancora.regra_mudou_recentemente is False
    assert derivar(sem_ancora)["opacidade"] != "regra_mudou"

    com_ancora = Ficha.de_json({
        **base, "regra_mudou_recentemente": True,
        "trechos_citados": {"regra_mudou": "O prazo é 31 de outubro."}})
    assert com_ancora.regra_mudou_recentemente is True
    assert derivar(com_ancora)["opacidade"] == "regra_mudou"

    # o stake NÃO cai por falta de citação — senão a ausência de prova viraria
    # portão, que é o erro mais caro deste motor
    assert Ficha.de_json({**base, "regra_mudou_recentemente": False}).stake is True


def test_booleano_como_string_recusa_a_ficha_mas_numero_como_string_nao():
    """Os dois casos NÃO são simétricos, e a diferença é o que se perde.

    A auditoria externa propôs `bool(d.get(...))` para os booleanos. Em Python
    `bool("false")` é `True`: a ficha seria lida ao contrário, em silêncio. Por
    isso booleano fora de tipo derruba a ficha inteira.

    Já `int("2")` devolve `2` — o valor certo, só mal embrulhado. Recusar aí
    jogaria fora medição boa por questão de aspas. O que a conversão pega é o
    lixo de verdade (`int("dois")` levanta e a ficha cai), e é isso que ela
    precisa pegar.
    """
    from app.validacao.ficha import Ficha

    base = dict(resposta_literal="x", condicoes_pessoais=0, ramos_de_acao=1,
                fontes_oficiais=1, decisao_apos_resposta=False,
                oficial_fecha_sozinho=False, regra_mudou_recentemente=False,
                stake=True, descobre_que_existe=False)
    assert Ficha.de_json(base) is not None
    # booleano em string INVERTE o sentido -> recusa
    assert Ficha.de_json({**base, "stake": "false"}) is None
    assert Ficha.de_json({**base, "decisao_apos_resposta": "true"}) is None
    # número em string PRESERVA o sentido -> aceita, com o valor certo
    assert Ficha.de_json({**base, "condicoes_pessoais": "2"}).condicoes_pessoais == 2
    # número que não é número é lixo -> recusa
    assert Ficha.de_json({**base, "condicoes_pessoais": "dois"}) is None


def test_agregar_mede_a_taxa_de_citacao_da_entidade():
    from app.validacao.ficha import Ficha, agregar

    boa = Ficha(resposta_literal="paga à vista ou parcela em cinco vezes",
                ramos_de_acao=2,
                trechos_citados={"ramos_de_acao": "paga à vista ou parcela"})
    ruim = Ficha(resposta_literal="o prazo é 31 de outubro",
                 ramos_de_acao=2,
                 trechos_citados={"ramos_de_acao": "existem dois caminhos"})
    e = agregar({"q1": boa, "q2": ruim})
    assert e.n_citacoes == 2
    assert e.citacoes_conferidas == 0.5
    # sem citação nenhuma é DIFERENTE de citar e errar
    vazia = agregar({"q1": Ficha(resposta_literal="x", ramos_de_acao=2)})
    assert vazia.citacoes_conferidas is None


# ── a trava que a auditoria externa desenhou depois de errar duas vezes ─────

def test_todo_nivel_derivavel_e_alcancavel():
    """SOBREJETIVIDADE DA DERIVAÇÃO: nenhum nível de escala pode ficar órfão.

    Este teste existe porque o mesmo defeito aconteceu três vezes, duas delas
    numa auditoria externa e uma na nossa própria proposta:

      1. tirar `ramos_de_acao` do prompt — o portão saía dele, e ficou
         incomputável;
      2. tirar `oficial_fecha_sozinho`, `regra_mudou_recentemente` e
         `descobre_que_existe` — cada um era a ÚNICA porta para um nível, e a
         remoção deixou 4 de 12 inalcançáveis, incluindo o TOPO de `ignorancia`
         e o topo E o piso de `opacidade`;
      3. rebaixar contagem ao piso quando a citação falha — `ramos_de_acao = 1`
         dispara `dado_unico`, que zera o índice. A trava de citação mataria
         tema por erro de pontuação.

    Nos três casos a derivação mudou e ninguém varreu a consequência. Aqui a
    varredura é exaustiva: todo o espaço de observáveis, todo nível de toda
    escala derivada. Nível inalcançável é escala mutilada em silêncio, e um eixo
    que não consegue atingir o próprio topo mente sobre o que mede.
    """
    import itertools
    from app.motor_pautas import espaco as E
    from app.validacao.ficha import Ficha, derivar

    alcancados = {eixo: set() for eixo in ("ignorancia", "engajamento", "opacidade")}
    for cond, ramos, fontes, dec, ofic, regra, stk, desc in itertools.product(
            range(4), range(1, 4), range(1, 4), (False, True),
            (False, True), (False, True), (False, True), (False, True)):
        f = Ficha(condicoes_pessoais=cond, ramos_de_acao=ramos, fontes_oficiais=fontes,
                  decisao_apos_resposta=dec, oficial_fecha_sozinho=ofic,
                  regra_mudou_recentemente=regra, stake=stk, descobre_que_existe=desc)
        for eixo, nivel in derivar(f).items():
            if eixo in alcancados:
                alcancados[eixo].add(nivel)

    for eixo, vistos in alcancados.items():
        declarados = set(getattr(E, eixo.upper()))
        orfaos = declarados - vistos
        assert not orfaos, (
            f"{eixo}: {sorted(orfaos)} declarados em espaco.py e INALCANÇÁVEIS "
            f"pela derivação. Ou a derivação perdeu um observável, ou a escala "
            f"tem nível que não significa nada.")
        assert not (vistos - declarados), (
            f"{eixo}: a derivação produz {sorted(vistos - declarados)}, que não "
            f"existe na escala.")


def test_trava_de_citacao_nunca_pode_rebaixar_contagem():
    """A auditoria externa propôs, no mesmo documento em que alertava contra
    falso-kill, rebaixar contagens ao piso quando a citação falhasse.

    `ramos_de_acao = 1` com `decisao_apos_resposta = False` É o portão. Rebaixar
    ao piso por erro de citação mataria o tema exatamente pelo motivo que ela
    própria dizia ser o erro mais caro. Este teste guarda a fronteira: citação
    reprovada não pode mexer em contagem.
    """
    from app.validacao.ficha import Ficha, derivar

    rica = Ficha(resposta_literal="paga à vista com desconto ou parcela em 5x",
                 ramos_de_acao=2, condicoes_pessoais=2,
                 trechos_citados={"ramos_de_acao": "isto não está no texto"})
    assert rica.citacoes_conferem()["ramos_de_acao"] is False
    # a citação reprovou, e a contagem NÃO mudou
    assert rica.ramos_de_acao == 2
    assert derivar(rica)["engajamento"] == "sustenta"


# ── os dois portões não podem mais discordar ───────────────────────────────

def test_eixo_e_veredito_nunca_discordam():
    """ERA O BUG MAIS GRAVE DO MOTOR, e ele era invisível porque os dois lados
    tinham nomes diferentes.

    O `veredito` foi blindado com três passadas e unanimidade — e governava uma
    STRING na tela. Quem zerava o índice era o eixo `engajamento`, que saía de
    `derivados[pergunta_mais_rica]`: UMA pergunta, UMA passada, AC1 0,64.

    E a eleição é enviesada CONTRA a pergunta em forma de calculadora, porque
    `carga_de_leitura` soma `condicoes_pessoais`. Medido: entidade que ramifica
    em 3 das 4 perguntas saía `indice=0,0 · descartar` enquanto o veredito da
    MESMA entidade dizia `sem_portao`.

    Aqui a concordância é varrida sobre todas as distribuições possíveis de 1 a
    6 perguntas. Se alguém voltar a tirar nível de portão de uma pergunta
    eleita, este teste cai.
    """
    import itertools
    from app.motor_pautas import espaco as E
    from app.validacao.ficha import agregar, veredito_do_portao

    seca = f()                                  # esgota
    rica = f(ramos_de_acao=2, condicoes_pessoais=3)   # sustenta E ganharia a eleição

    for n in range(1, 7):
        for k in range(n + 1):                  # k perguntas que esgotam
            ent = {f"seca{i}": seca for i in range(k)}
            ent.update({f"rica{i}": rica for i in range(n - k)})
            e = agregar(ent)
            veredito = veredito_do_portao(e.share_dado_unico, n)
            eixo_mata = e.niveis["engajamento"] in E.PORTOES["engajamento"]
            assert eixo_mata == (veredito == "portao"), (
                f"n={n} k={k} share={e.share_dado_unico}: veredito={veredito} "
                f"mas eixo={e.niveis['engajamento']} — os dois portões discordam")


def test_uma_pergunta_de_calculadora_nao_mata_a_entidade():
    """O caso concreto que foi reproduzido no código vivo, congelado."""
    from app.motor_pautas import espaco as E
    from app.validacao.ficha import agregar

    e = agregar({
        "Como calculo o valor?":     f(condicoes_pessoais=3, ramos_de_acao=1),
        "Quais as opções de saque?": f(ramos_de_acao=2),
        "Posso mudar depois?":       f(ramos_de_acao=2),
        "Simplificada ou completa?": f(ramos_de_acao=2, decisao_apos_resposta=True),
    })
    # a eleição continua elegendo a calculadora — e isso deixou de ser fatal
    assert e.pergunta_mais_rica == "Como calculo o valor?"
    assert e.niveis["engajamento"] == "sustenta"

    # com as duas famílias preenchidas: sem os eixos medidos o índice é `None`
    # por desenho (uma família vazia não vira média), e o teste não veria nada.
    pos = E.posicionar("x", pais="BR", escopo=E.ESCOPO_PAUTADOR,
                       medidos=["volume", "reposicao", "vacuo",
                                "formato_consumo", "densidade"],
                       volume="alto", reposicao="anual", vacuo="virgem",
                       formato_consumo="texto_busca", densidade="densa",
                       **e.niveis)
    assert "engajamento" not in pos.portoes_disparados()
    assert pos.indice > 0
    assert pos.perfil() != "descartar"


def test_portao_de_ignorancia_exige_TODAS_sem_stake():
    """Uma pergunta de curiosidade no PAA não pode matar a entidade — é a mesma
    lição do `DIRPF`, no outro eixo que carrega portão."""
    from app.validacao.ficha import agregar

    # a sem-stake é a mais rica e venceria a eleição
    e = agregar({"curiosa": f(stake=False, condicoes_pessoais=3),
                 "a": f(ramos_de_acao=2), "b": f(ramos_de_acao=2)})
    assert e.niveis["ignorancia"] != "nao_preciso_de_nada"

    # todas sem stake: aí sim
    t = agregar({f"q{i}": f(stake=False) for i in range(3)})
    assert t.niveis["ignorancia"] == "nao_preciso_de_nada"


# ── o roteador de formato ──────────────────────────────────────────────────

def test_roteador_nao_pode_matar_nem_ressuscitar():
    """O invariante que torna o roteador seguro por construção.

        formato_da_pergunta(f) == ARTIGO  <=>  nivel_engajamento(f) == "sustenta"

    As duas leem a mesma condição, então o roteador não pode matar o que hoje
    vive nem ressuscitar nada sozinho — ele só NOMEIA o que já morreu. É essa
    equivalência que permite ligá-lo sem tocar em `posicionar()`.
    """
    import itertools
    from app.validacao.ficha import ARTIGO, formato_da_pergunta, nivel_engajamento

    for c, r, d, o, s in itertools.product(range(4), range(1, 4),
                                           (False, True), (False, True), (False, True)):
        x = Ficha(condicoes_pessoais=c, ramos_de_acao=r, decisao_apos_resposta=d,
                  oficial_fecha_sozinho=o, stake=s)
        assert (formato_da_pergunta(x) == ARTIGO) == (nivel_engajamento(x) == "sustenta")


def test_o_balcao_oficial_veta_antes_do_discriminador():
    """`consultar IPVA pela placa` conta 2 condições (estado, ano) e SERIA
    roteado para ferramenta — o vazamento que um crítico apontou.

    Quem o barra é `oficial_fecha_sozinho`, e por isso ele vem ANTES da contagem
    na cascata. Quando o portal do estado de fato resolve, nenhum formato salva.
    """
    from app.validacao.ficha import FERRAMENTA, NAO_PRODUZIR, formato_da_pergunta

    ipva_no_portal = f(condicoes_pessoais=2, ramos_de_acao=1, oficial_fecha_sozinho=True)
    assert formato_da_pergunta(ipva_no_portal) == NAO_PRODUZIR

    # e quando o canal oficial NÃO resolve, dois dropdowns são um widget legítimo
    ipva_sem_portal = f(condicoes_pessoais=2, ramos_de_acao=1, oficial_fecha_sozinho=False)
    assert formato_da_pergunta(ipva_sem_portal) == FERRAMENTA


def test_uma_condicao_nao_faz_ferramenta():
    """Pré-requisito de acesso não é campo de formulário. O `Registrato` conta 1
    condição — "conta Gov.br nível prata ou ouro" — que é porta de entrada, e
    formulário de um campo não cruza o limiar de refresh."""
    from app.validacao.ficha import NAO_PRODUZIR, formato_da_pergunta

    assert formato_da_pergunta(f(condicoes_pessoais=1)) == NAO_PRODUZIR
    assert formato_da_pergunta(f(condicoes_pessoais=0)) == NAO_PRODUZIR


def test_prescricao_traz_os_campos_de_graca():
    """A especificação do widget sai de `trechos_citados`, sem segunda chamada."""
    from app.validacao.ficha import formatos_da_entidade

    calc = Ficha(condicoes_pessoais=2, ramos_de_acao=1,
                 resposta_literal="depende se optou pelo saque-aniversário e da carência",
                 trechos_citados={"condicoes_pessoais": "se optou pelo saque-aniversário e da carência"})
    r = formatos_da_entidade({"Quanto vou receber?": calc, "Quais as opções?": f(ramos_de_acao=2)})
    assert r["n_ferramenta"] == 1 and r["n_artigo"] == 1
    assert r["prescricao"][0]["campos"].startswith("se optou")
    assert r["prescricao"][0]["n_campos"] == 2
