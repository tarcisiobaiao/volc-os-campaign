"""As cinco capacidades, e a inversão da reconciliação.

Duas perguntas que a tela passou a fazer ao servidor, e que antes ela respondia
sozinha — mal, nos dois casos:

1. **"o que eu posso?"** era derivado de `role === 'ADMIN'`, e ADMIN de produto
   virava botão de gasto que a trava do servidor recusa no clique;
2. **"de quem é esta campanha?"** não era feita por ninguém: o write-path de
   `POST /vinculos` existe desde 26/08 e `trafego_vinculo` continua com zero
   linhas, porque nenhuma superfície chegava até ele.

⚠️ Nenhum teste aqui toca no Google Ads nem no Supabase. As capacidades são
função pura de (papel, trava), e a inversão é função pura de (campanha, funis,
universo).
"""
from __future__ import annotations

import pytest

from app.trafego import capacidades as cap
from app.trafego import reconciliacao as rec


# ═══════════════════════════════════════════════════════════════════════════
# AS CAPACIDADES
# ═══════════════════════════════════════════════════════════════════════════


def test_admin_de_produto_nao_ganha_o_direito_de_gastar():
    """A separação que esta entrega existe para fazer.

    Se esta prova cair, voltamos ao estado em que promover alguém a
    administrador do VOLC O.S. o autoriza a criar campanha na conta do cliente —
    duas decisões de tamanhos muito diferentes tomadas por um clique só.
    """
    c = cap.de_identidade(papel="ADMIN", escrita_permitida=False)

    assert c.is_admin is True
    assert c.google_mutate is False
    # E a recusa ENSINA: botão cinza sem frase é o que faz o operador procurar
    # contorno em vez de permissão.
    assert c.porque_sem_mutacao
    assert "permissão operacional" in c.porque_sem_mutacao


def test_provar_nao_espera_a_trava_de_escrita():
    """`validate_only` é leitura, e a escada depende disso.

    `volc_ads/gads/client.py:validar_mutacoes` não chama
    `exigir_leitura_apenas` — deliberadamente. Se a tela tratasse a prova como
    escrita, a única etapa que separa "montei um pedido" de "tenho o direito de
    gastar" ficaria do lado fechado da porta, e o operador aprenderia a subir
    sem provar por ser o caminho aberto.
    """
    c = cap.de_identidade(papel="ADMIN", escrita_permitida=False)

    assert c.google_validate_only is True
    assert c.google_mutate is False


def test_prova_demand_gen_nasce_desligada_e_nao_herda_validate_only(monkeypatch):
    """A capacidade geral não abre a superfície experimental por acidente."""
    monkeypatch.delenv(cap.ENV_DEMAND_GEN_VALIDATE_ONLY, raising=False)

    c = cap.de_identidade(papel="ADMIN", escrita_permitida=False)
    assert c.google_validate_only is True
    assert c.google_demand_gen_validate_only is False
    assert c.json()["google_demand_gen_validate_only"] is False


def test_prova_demand_gen_so_liga_com_on_exato_e_nunca_autoriza_mutacao(monkeypatch):
    for valor in ("true", "1", "sim", "erro-de-grafia", ""):
        monkeypatch.setenv(cap.ENV_DEMAND_GEN_VALIDATE_ONLY, valor)
        assert cap.servidor_oferece_demand_gen_validate_only() is False

    monkeypatch.setenv(cap.ENV_DEMAND_GEN_VALIDATE_ONLY, "on")
    c = cap.de_identidade(papel="ADMIN", escrita_permitida=False)
    assert c.google_demand_gen_validate_only is True
    assert c.google_mutate is False

    operador = cap.de_identidade(papel="OPERATOR", escrita_permitida=False)
    assert operador.google_demand_gen_validate_only is False


def test_flag_nao_compensa_namespace_ou_campo_v25_ausente(monkeypatch):
    """Configuração não transforma um SDK incompatível em capacidade real."""
    monkeypatch.setenv(cap.ENV_DEMAND_GEN_VALIDATE_ONLY, "on")
    monkeypatch.setattr(cap, "_sdk_demand_gen_disponivel", lambda: False)

    assert cap.servidor_oferece_demand_gen_validate_only() is False
    c = cap.de_identidade(papel="ADMIN", escrita_permitida=False)
    assert c.google_validate_only is True
    assert c.google_demand_gen_validate_only is False
    assert c.google_mutate is False


def test_papel_revogado_perde_ate_a_leitura():
    """`volc_role_of` devolve string vazia para quem foi revogado, e vale no ato.

    É o mesmo corte que `POST /vinculos` já faz na rota: a sessão do Supabase
    continua válida até o token expirar, a autorização não.
    """
    c = cap.de_identidade(papel="", escrita_permitida=False)

    assert (c.is_admin, c.google_read, c.google_validate_only,
            c.google_mutate, c.lab_mode) == (False, False, False, False, False)
    assert "papel ativo" in (c.porque_sem_mutacao or "")


def test_operador_le_e_nao_prova():
    """Quem não é admin observa a conta e não gasta quota dela."""
    c = cap.de_identidade(papel="OPERATOR", escrita_permitida=False)

    assert c.google_read is True
    assert c.google_validate_only is False
    assert c.lab_mode is False, (
        "laboratório mostra jornadas que ainda não existem; ensiná-las a quem "
        "opera todo dia é prometer uma interface que o sistema não cumpre")


def test_o_laboratorio_fecha_sozinho_quando_a_escrita_abre(monkeypatch):
    """A amarração que dispensa alguém lembrar.

    Um laboratório que continuasse ligado depois de a escrita abrir seria a pior
    combinação possível: uma tela que convida a explorar sem consequência, sobre
    um sistema que passou a ter consequência.
    """
    monkeypatch.delenv(cap.ENV_LABORATORIO, raising=False)

    assert cap.de_identidade(papel="ADMIN", escrita_permitida=False).lab_mode is True
    assert cap.de_identidade(papel="ADMIN", escrita_permitida=True).lab_mode is False


def test_nem_ligado_explicitamente_abre_laboratorio_sobre_escrita(monkeypatch):
    """`on` quer o laboratório; ele não aceita o laboratório sobre consequência.

    ⚠️ Achado por revisão adversarial em 27/08/2026: com `VOLC_LABORATORIO=on`
    e a escrita aberta, `lab_mode` e `google_mutate` vinham os dois `True` — e
    nenhuma invariante recusava. O frontend afirma que a faixa "some sozinha no
    dia em que a escrita na conta abrir"; a afirmação só era verdadeira em
    `auto`.
    """
    monkeypatch.setenv(cap.ENV_LABORATORIO, "on")

    assert cap.servidor_oferece_laboratorio(escrita_permitida=True) is False
    assert cap.servidor_oferece_laboratorio(escrita_permitida=False) is True

    c = cap.de_identidade(papel="ADMIN", escrita_permitida=True)
    assert c.google_mutate is True
    assert c.lab_mode is False


def test_configuracao_ilegivel_nao_liga_o_laboratorio(monkeypatch):
    """Erro de digitação na configuração não pode ser o que abre uma superfície."""
    monkeypatch.setenv(cap.ENV_LABORATORIO, "sim, por favor")

    # Cai em `auto`, que com a escrita aberta significa fechado.
    assert cap.servidor_oferece_laboratorio(escrita_permitida=True) is False
    monkeypatch.setenv(cap.ENV_LABORATORIO, "off")
    assert cap.servidor_oferece_laboratorio(escrita_permitida=False) is False


def test_a_resposta_nao_carrega_segredo():
    """Nem nome de variável de ambiente, nem chave, nem caminho de arquivo.

    A frase de recusa é escrita para o operador, que não tem acesso ao servidor.
    Instrução impossível de executar faz a pessoa concluir que o sistema está
    quebrado — foi a correção que a rota `/trava` já levou.
    """
    corpo = cap.de_identidade(papel="ADMIN", escrita_permitida=False).json()

    texto = repr(corpo)
    for vazamento in ("FORGE_PERMITIR_ESCRITA", "destravar", "volc_ads",
                      cap.ENV_LABORATORIO, cap.ENV_DEMAND_GEN_VALIDATE_ONLY,
                      ".py"):
        assert vazamento not in texto, f"{vazamento!r} vazou para a tela"


@pytest.mark.parametrize("kwargs", [
    # mutar sem ser admin
    dict(is_admin=False, lab_mode=False, google_read=True,
         google_validate_only=True, google_mutate=True),
    # mutar sem poder provar
    dict(is_admin=True, lab_mode=False, google_read=True,
         google_validate_only=False, google_mutate=True),
    # provar sem poder ler
    dict(is_admin=True, lab_mode=False, google_read=False,
         google_validate_only=True, google_mutate=False,
         porque_sem_mutacao="qualquer"),
    # a porta estreita não existe sem a capacidade geral de prova
    dict(is_admin=True, lab_mode=False, google_read=True,
         google_validate_only=False, google_mutate=False,
         google_demand_gen_validate_only=True,
         porque_sem_mutacao="qualquer"),
    # fechada e muda
    dict(is_admin=True, lab_mode=False, google_read=True,
         google_validate_only=True, google_mutate=False),
    # laboratório aberto sobre um servidor que escreve
    dict(is_admin=True, lab_mode=True, google_read=True,
         google_validate_only=True, google_mutate=True),
    # laboratório sem papel administrativo
    dict(is_admin=False, lab_mode=True, google_read=True,
         google_validate_only=False, google_mutate=False,
         porque_sem_mutacao="qualquer"),
])
def test_combinacoes_incoerentes_nao_se_constroem(kwargs):
    """A invariante mora no tipo, não na boa intenção de quem o preenche."""
    with pytest.raises(ValueError):
        cap.Capacidades(**kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# A FRONTEIRA DA ROTA
# ═══════════════════════════════════════════════════════════════════════════


def test_a_rota_de_capacidades_nao_pode_falar_com_o_google():
    """A única rota do delta que importa `volc_ads` — e ela só LÊ a trava.

    ⚠️ `test_trafego_alertas.py` enumera as rotas de `routers/trafego_inventario`
    e obriga quem acrescenta uma a declarar de que lado da fronteira ela está.
    `/capacidades` vive em `routers/trafego.py`, que aquela fixture não monta —
    então ela entrou sem passar por gate nenhum de enumeração.

    Esta prova fecha o buraco pelo lado que importa: a rota lê `modo.estado()`,
    que é inspeção de configuração local, e não pode ganhar caminho para
    `mutar`, `destravar` ou qualquer consulta à conta.
    """
    import ast
    import pathlib

    fonte = pathlib.Path(__file__).resolve().parents[1] / "app" / "routers" / "trafego.py"
    arvore = ast.parse(fonte.read_text(encoding="utf-8"))

    alvo = next(
        (n for n in ast.walk(arvore)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
         and n.name == "capacidades_do_operador"),
        None)
    assert alvo is not None, "a rota de capacidades sumiu ou mudou de nome"

    # As FUNÇÕES que a rota chama, por nome — e não uma busca de texto no dump,
    # que casaria com docstring, comentário e nome de parâmetro.
    chamadas = {
        (n.func.attr if isinstance(n.func, ast.Attribute) else
         n.func.id if isinstance(n.func, ast.Name) else "")
        for n in ast.walk(alvo) if isinstance(n, ast.Call)
    }

    for proibido in ("mutar", "destravar", "mutate_campaigns",
                     "exigir_leitura_apenas", "subir", "validar_mutacoes"):
        assert proibido not in chamadas, (
            f"a rota de capacidades ganhou caminho para {proibido!r} — ela "
            f"projeta o que as travas decidiram, e não decide nada")

    # ⚠️ E ela pergunta o fator DURÁVEL da trava, não o transitório.
    # `escrita_permitida()` exige `destravar()`, que é global de processo e só
    # vale DENTRO do bloco `with` de uma operação — chamada de fora ela devolve
    # `False` sempre, inclusive num servidor onde `/subir` cria campanha. A
    # rota lê `modo.estado()`, cujo `env_presente` é a configuração do servidor.
    assert "estado" in chamadas, (
        "a rota deve ler `modo.estado()` — o fator durável da trava")
    assert "escrita_permitida" not in chamadas, (
        "`escrita_permitida()` fora de um bloco `destravar()` é sempre False, e "
        "a tela passaria a dizer que a permissão está fechada num servidor que "
        "escreve — além de deixar o Modo Laboratório aberto justamente ali")


# ═══════════════════════════════════════════════════════════════════════════
# A INVERSÃO — de quem é esta campanha?
# ═══════════════════════════════════════════════════════════════════════════
#
# Os dados abaixo são os MEDIDOS no Supabase oficial em 27/08/2026, conta
# 8017851692. Inventar números aqui tiraria da prova o que ela tem de melhor:
# ela falha se o comportamento divergir do caso real que motivou a entrega.

URL_MAQ = "https://creditoup.com.br/r/maquininha-de-cartao-menor-taxa/"
URL_FGTS = "https://creditoup.com.br/r/fgts-saque-aniversario/"
CONTA = "8017851692"


def _maquininha(**troca) -> rec.CampanhaConhecida:
    base = dict(
        volc_campaign_id="vc-maquininha",
        campaign_id="24155134757",
        customer_id=CONTA,
        nome=f"BR - 20260819_131546 / Maquininha de Cartão / {URL_MAQ}",
        estado_externo="ENABLED",
        canal="SEARCH",
        historico=False,
        url_final=URL_MAQ,
        lido_em="2026-08-27T10:45:29-03:00",
    )
    base.update(troca)
    return rec.CampanhaConhecida(**base)


def _fgts(**troca) -> rec.CampanhaConhecida:
    base = dict(
        volc_campaign_id="vc-fgts",
        campaign_id="24156373085",
        customer_id=CONTA,
        nome=f"BR BR - 20260819_222608 / FGTS Saque-Aniversário / {URL_FGTS}",
        estado_externo="ENABLED",
        canal="SEARCH",
        historico=False,
        url_final=URL_FGTS,
        lido_em="2026-08-27T10:45:29-03:00",
    )
    base.update(troca)
    return rec.CampanhaConhecida(**base)


FUNIL_MAQ = rec.Funil(opportunity_id=74, run_id=7, project_id=2,
                      customer_id=CONTA, lp_url=URL_MAQ)
FUNIL_FGTS = rec.Funil(opportunity_id=65, run_id=9, project_id=2,
                       customer_id=CONTA, lp_url=URL_FGTS)
#: O funil de cartão para negativado, que NÃO pode casar com nenhuma das duas.
FUNIL_OUTRO = rec.Funil(opportunity_id=73, run_id=6, project_id=2,
                        customer_id=CONTA,
                        lp_url="https://creditoup.com.br/?post_type=r&p=2152")

FUNIS = (FUNIL_MAQ, FUNIL_FGTS, FUNIL_OUTRO)


def test_as_duas_campanhas_reais_acham_o_funil_certo():
    """O caso que motivou a entrega, com os números medidos.

    Maquininha → oportunidade 74 / run 7. FGTS → oportunidade 65 / run 9. E
    nenhuma das duas encosta no funil 73, que é de outro termo.
    """
    universo = [_maquininha(), _fgts()]

    maq = rec.correspondencias_da_campanha(_maquininha(), FUNIS, universo)
    assert maq.estado == rec.CORRESPONDENCIA_UNICA
    assert [(c.opportunity_id, c.run_id) for c in maq.correspondencias] == [(74, 7)]

    fgts = rec.correspondencias_da_campanha(_fgts(), FUNIS, universo)
    assert fgts.estado == rec.CORRESPONDENCIA_UNICA
    assert [(c.opportunity_id, c.run_id) for c in fgts.correspondencias] == [(65, 9)]


def test_correspondencia_provavel_nunca_dispensa_a_confirmacao():
    """ADR-09, dito no tipo.

    Uma correspondência única e limpa continua sendo pergunta. Se esta prova
    cair, a tela passa a poder apresentar como vínculo o que ninguém confirmou —
    e vínculo errado contamina atribuição de receita de forma permanente.
    """
    revisao = rec.correspondencias_da_campanha(
        _maquininha(), FUNIS, [_maquininha(), _fgts()])

    assert revisao.exige_confirmacao_humana is True
    assert revisao.json()["vinculo"] is None


def test_a_url_da_conta_nao_e_promovida_a_sinal_forte():
    """`historica`, e não `forte` — o espelho não guarda quando a URL foi lida.

    Apresentá-la como observação de agora ofereceria como prova recente um valor
    que o gatilho da v9_04 preserva entre varreduras e pode ter três semanas.
    """
    revisao = rec.correspondencias_da_campanha(
        _maquininha(), FUNIS, [_maquininha(), _fgts()])

    (unica,) = revisao.correspondencias
    assert unica.forca_maxima == rec.HISTORICA
    assert [s.regra for s in unica.sinais] == [rec.REGRA_URL_DA_CONTA]


def test_forca_maxima_nao_ordena_por_alfabeto():
    """Por acaso, `medio` > `historica` > `forte` em ordem alfabética.

    Um `max()` ingênuo sobre a string devolveria `medio` como o mais forte de
    `{forte, medio}` — e uma evidência fraca seria apresentada como a melhor
    que existe, exatamente onde o operador está decidindo em quem confiar.
    """
    c = rec.Correspondencia(
        opportunity_id=1, run_id=1, project_id=1, destinos=(),
        sinais=(rec.Sinal(rec.REGRA_URL_NO_NOME, rec.MEDIO),
                rec.Sinal(rec.REGRA_LINHAGEM, rec.FORTE),
                rec.Sinal(rec.REGRA_URL_DA_CONTA, rec.HISTORICA)),
        estado_do_funil=rec.CORRESPONDENCIA_PROVAVEL,
        outras_campanhas_presentes=0)

    assert c.forca_maxima == rec.FORTE


def test_vinculo_vivo_encerra_a_pergunta():
    """Decisão registrada não vira sugestão perpétua a cada carregamento."""
    ja = _maquininha(vinculo_id="11111111-1111-1111-1111-111111111111",
                     vinculo_opportunity_id=74, vinculo_run_id=7)

    revisao = rec.correspondencias_da_campanha(ja, FUNIS, [ja, _fgts()])

    assert revisao.estado == rec.ASSOCIADA
    assert revisao.correspondencias == ()
    assert revisao.exige_confirmacao_humana is False
    assert revisao.json()["vinculo"]["opportunity_id"] == 74


def test_campanha_sem_conta_nao_apura_em_vez_de_negar():
    """"Não consegui provar" e "provei e não há" levam a lugares opostos.

    O segundo libera o operador a tratar a campanha como órfã; o primeiro pede
    que ele descubra por que a conta não está identificada.
    """
    orfa = _maquininha(customer_id=None)

    revisao = rec.correspondencias_da_campanha(orfa, FUNIS, [orfa])

    assert revisao.estado == rec.NAO_APURADA
    assert revisao.sinais_ausentes
    assert revisao.sinais_ausentes[0]["impede_prova"] is True


def test_campanha_sem_funil_correspondente_nao_e_erro():
    """O estado normal de toda campanha descoberta antes de alguém responder.

    Dois dos três funis têm URL publicada e puderam ser comparados; o terceiro
    é rascunho. Ao menos uma comparação foi possível, então "comparei e não
    achei" é honesto — e o rascunho continua visível nas ausências.
    """
    solta = _maquininha(volc_campaign_id="vc-solta",
                        campaign_id="999",
                        nome="campanha antiga sem funil",
                        url_final="https://outrodominio.com.br/x/")

    revisao = rec.correspondencias_da_campanha(solta, FUNIS, [solta])

    assert revisao.estado == rec.SEM_CORRESPONDENCIA
    assert revisao.correspondencias == ()
    assert revisao.exige_confirmacao_humana is False
    # ⚠️ E o que NÃO pôde ser comparado viaja mesmo sem candidato. Antes de
    # 27/08/2026 esta lista vinha vazia sempre que nada casava — justamente o
    # caso em que ela importa.
    assert any(s["impede_prova"] for s in revisao.sinais_ausentes)


def test_disputa_pelo_mesmo_funil_viaja_como_ressalva():
    """Duas campanhas presentes apontando para o mesmo funil.

    ⚠️ O estado da CAMPANHA continua `correspondencia_unica` — ela achou um
    funil só. Quem está em conflito é o funil, e copiar o estado dele para cá
    faria a tela dizer que a Maquininha está em conflito quando quem está é o
    funil. A disputa aparece como ressalva, que é o que o operador precisa ver
    antes de confirmar.
    """
    gemea = _maquininha(volc_campaign_id="vc-maquininha-2",
                        campaign_id="24155134758")
    universo = [_maquininha(), gemea, _fgts()]

    revisao = rec.correspondencias_da_campanha(_maquininha(), FUNIS, universo)

    assert revisao.estado == rec.CORRESPONDENCIA_UNICA
    (unica,) = revisao.correspondencias
    assert unica.outras_campanhas_presentes == 1
    assert unica.estado_do_funil == rec.CONFLITO


def test_historico_nao_disputa_o_leilao():
    """Campanha removida não encarece ninguém, e não conta como disputa."""
    morta = _maquininha(volc_campaign_id="vc-maquininha-morta",
                        campaign_id="24155134700",
                        estado_externo="REMOVED", historico=True)
    universo = [_maquininha(), morta, _fgts()]

    revisao = rec.correspondencias_da_campanha(_maquininha(), FUNIS, universo)

    (unica,) = revisao.correspondencias
    assert unica.outras_campanhas_presentes == 0


def test_conta_sem_funil_publicado_nao_apura():
    """79 das 84 campanhas do inventário caem aqui — e não em "não associada".

    Medido em 27/08/2026: `projects` tem 2 linhas e só uma declara conta de
    anúncio. Para as campanhas das outras duas contas o chamador devolve ZERO
    funis, e a resposta anterior era `sem_correspondencia` com ausências
    vazias. A tela dizia "não associada ao VOLC · nada precisa ser feito agora"
    sobre 79 campanhas que ninguém comparou com nada.
    """
    revisao = rec.correspondencias_da_campanha(_maquininha(), (), [_maquininha()])

    assert revisao.estado == rec.NAO_APURADA
    assert revisao.correspondencias == ()
    assert revisao.sinais_ausentes
    assert revisao.sinais_ausentes[0]["impede_prova"] is True
    assert "funil" in revisao.sinais_ausentes[0]["motivo"]


def test_alvo_fora_do_universo_e_erro_do_chamador():
    """Responder `sem_correspondencia` aqui seria vender ausência de dado como prova."""
    with pytest.raises(ValueError, match="universo"):
        rec.correspondencias_da_campanha(_maquininha(), FUNIS, [_fgts()])


def test_conta_de_outro_cliente_nao_casa():
    """A conta é pré-requisito da prova (ADR-03), não sinal.

    Duas contas diferentes com URLs parecidas é o caso em que o erro seria
    silencioso — portais de utilidade pública se parecem.

    ⚠️ E o veredito é `nao_apurada`, não `sem_correspondencia`: nenhum destes
    funis pôde sequer ser comparado com uma campanha de outra conta. Dizer
    "comparei e não achei" ali seria afirmar uma prova que não houve.
    """
    de_outro = _maquininha(customer_id="9999999999")

    revisao = rec.correspondencias_da_campanha(de_outro, FUNIS, [de_outro])

    assert revisao.estado == rec.NAO_APURADA
    assert revisao.correspondencias == ()
