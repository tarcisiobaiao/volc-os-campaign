"""BLINDAGEM da v1 do Assistente Criativo — o ponto de partida selado.

Duas capacidades entram aqui porque são as que definem o produto, e nenhuma
delas é óbvia o bastante para sobreviver sozinha a uma refatoração futura.

## 1. A âncora é o DESEJO, não o mecanismo

É a capacidade mais importante do motor, e a que ninguém adivinha lendo o código.
O caso real: uma matéria em `apps.technewsbrasil.com.br` sobre o aplicativo
"Jornada do Estudante", que serve para consultar o programa Pé-de-Meia. A leitura
da página conclui — corretamente — que o ASSUNTO da página é o aplicativo. Mas
quem para o polegar no feed é o DINHEIRO, não o canal de consulta.

Antes desta separação o motor produzia quatro peças cujas headlines eram
"Pé-de-Meia no App Jornada do Estudante", "App Jornada do Estudante: O Que Ele
Mostra?", "Dados Sumiram no App Jornada do Estudante?" e "Login no App Jornada do
Estudante" — porque o validador exigia a string de `assunto_principal` dentro de
cada imagem, e ela consumia a headline inteira. O nome institucional do canal
virava o anúncio.

`assunto_principal` continua respondendo "do que esta página trata" e governando
congruência. `ancora_de_desejo` responde "o que faz alguém clicar", e é ELA que
precisa aparecer escrita na arte.

## 2. Um conceito, vários formatos, uma família

Cada formato é uma GERAÇÃO PRÓPRIA a partir da mesma peça — não um recorte da
peça 4x5. Medido: derivar 1.91x1 de um 4x5 por recorte preserva 42% da imagem e
decapita headline e CTA, porque texto vive exatamente nas bordas que a tesoura
corta. Gerar irmãs custa o mesmo que o motor já gasta (uma chamada por formato) e
devolve composição nativa em cada proporção, com a mesma cena, a mesma copy e a
mesma família cromática.
"""
import pytest

from app.criativo.agente.contrato import DirecaoDeArte, SaidaDoAgente
from app.criativo.agente.validacao import SaidaCriativaInvalida, validar_saida
from app.criativo.studio.spec_visual import compilar_prompt, especificar
from test_criativo_agente_meta import pedido, saida
from test_criativo_studio_adaptador import saida as saida_do_studio


FAMILIA = ["azul royal", "amarelo ouro", "verde bandeira", "branco"]

#: O pedido real que originou esta blindagem: página sobre o APP, âncora no
#: PROGRAMA. As duas coisas coexistem no mesmo briefing de propósito.
def _pedido_de_arbitragem(quantidade=1):
    return pedido(quantidade).model_copy(update={
        "assunto_principal": "App Jornada do Estudante",
        "ancora_de_desejo": "Pé-de-Meia",
        "ancoras_aceitas": ["Pé de Meia", "poupança do ensino médio"],
        "familia_cromatica": FAMILIA,
    })


#: Uma direção de arte v2 que USA a família — é o que o motor precisa emitir.
DIRECAO = {
    "blueprint_version": "volc.art-direction/2",
    "rota_de_texto": "campo_cromatico", "registro": "cartaz_beneficio",
    "presenca_humana": "ausente",
    "composicao": "Campo de cor no terço superior; objeto centrado abaixo.",
    "tipografia": "Sans grotesca pesada em caixa alta, duas linhas.",
    "paleta_e_contraste": "Dominante verde bandeira no campo chapado; apoio amarelo ouro na headline; tinta branca.",
    "cena": "Caderno e caneta sobre carteira escolar, luz de sala de aula.",
    "tratamento": "Fotografia nítida, textura de papel e fórmica preservadas.",
}


def _com_headline(headline, complemento="Consulte pelo celular."):
    bruto = saida(1)
    bruto["pecas"][0].update(headline_interna=headline, complemento_interno=complemento,
                             direcao_de_arte=dict(DIRECAO))
    return SaidaDoAgente.model_validate(bruto)


@pytest.mark.parametrize("headline", [
    "Pé-de-Meia: quanto já entrou?",
    "Onde cai o Pé-de-Meia?",
    "Poupança do ensino médio: veja a data",   # variante confirmada pelo operador
])
def test_a_arte_pode_falar_do_dinheiro_sem_citar_o_app(headline):
    """A headline que o motor NÃO conseguia emitir antes da separação."""
    validar_saida(_pedido_de_arbitragem(), _com_headline(headline))


@pytest.mark.parametrize("headline", [
    "Login no App Jornada do Estudante",
    "App Jornada do Estudante: o que ele mostra?",
    "Dados sumiram no aplicativo?",
])
def test_o_nome_do_canal_sozinho_nao_basta(headline):
    """As headlines reais do lote reclamado, agora recusadas."""
    with pytest.raises(SaidaCriativaInvalida, match="a imagem não diz sobre o que é"):
        validar_saida(_pedido_de_arbitragem(), _com_headline(headline, "Acesso com CPF."))


def test_sem_ancora_declarada_vale_o_assunto_e_nada_muda_para_briefings_antigos():
    """Um pedido histórico não muda de significado por causa de um campo novo."""
    antigo = pedido(1).model_copy(update={"assunto_principal": "Pé-de-Meia"})
    assert antigo.ancora_de_desejo is None
    validar_saida(antigo, _com_headline("Pé-de-Meia: entenda a consulta"))
    with pytest.raises(SaidaCriativaInvalida, match="a imagem não diz sobre o que é"):
        validar_saida(antigo, _com_headline("Entenda a consulta"))


def test_o_operador_decide_a_variante_e_o_modelo_nao_inventa_a_dele():
    """Aceitar sinônimo proposto na mesma resposta que ele valida seria circular."""
    sem_variantes = pedido(1).model_copy(update={"ancora_de_desejo": "Pé-de-Meia"})
    with pytest.raises(SaidaCriativaInvalida, match="a imagem não diz sobre o que é"):
        validar_saida(sem_variantes, _com_headline("Poupança do ensino médio: veja a data"))


# ── Multi-formato: um conceito, quatro canvases, uma família ────────────────

SLOTS = ["4x5", "1x1", "9x16", "1.91x1"]


def _irmas():
    """A mesma peça especificada nos quatro formatos — o que o adaptador faz."""
    lote = saida_do_studio(1)
    peca, copy = lote.pecas[0], lote.copies_compartilhadas[0]
    peca.direcao_de_arte = DirecaoDeArte.model_validate(DIRECAO)
    return {
        slot: especificar(peca, copy, slot, "sem_foto", familia_cromatica=FAMILIA)
        for slot in SLOTS
    }


def test_cada_formato_recebe_o_proprio_canvas_e_nao_um_recorte():
    """Recortar um 4x5 para 1.91x1 preserva 42% e decapita headline e CTA.

    A prova de que não há recorte: cada spec carrega a medida final do SEU
    formato, e o prompt pede aquela proporção especificamente.
    """
    from app.criativo import dominio

    for slot, spec in _irmas().items():
        formato = dominio.formato_de(slot)
        assert (spec.largura_final, spec.altura_final) == (formato.largura, formato.altura)
        assert f"{formato.largura}x{formato.altura}" in compilar_prompt(spec)


def test_as_irmas_compartilham_conceito_copy_e_familia_cromatica():
    """É uma família, não quatro peças soltas: só o canvas muda."""
    irmas = _irmas()
    referencia = irmas["4x5"]
    for slot, spec in irmas.items():
        assert spec.creative_ref == referencia.creative_ref, slot
        assert spec.texto_exato == referencia.texto_exato, slot
        assert spec.direcao_de_arte == referencia.direcao_de_arte, slot
        assert spec.familia_cromatica == FAMILIA, slot


def test_a_familia_cromatica_chega_ao_prompt_de_pixels_de_todo_formato():
    """Sem isto a cor volta a ser sugestão em prosa, e o motor converge no azul."""
    for slot, spec in _irmas().items():
        prompt = compilar_prompt(spec)
        assert "UNIDADE CROMÁTICA OBRIGATÓRIA" in prompt, slot
        for cor in FAMILIA:
            assert cor in prompt, f"{cor} ausente no prompt de {slot}"


def test_o_rotulo_de_proporcao_nunca_vaza_para_o_prompt():
    """`formato.rotulo` do 4x5 é "Retrato" — em português, retrato de PESSOA.

    Ele vazava na última linha do prompt do motor, na posição de maior recência,
    e o lote inteiro saía com retrato de adolescente.
    """
    for slot, spec in _irmas().items():
        prompt = compilar_prompt(spec)
        for rotulo in ("Retrato", "Quadrado", "Paisagem", "Vertical"):
            assert rotulo not in prompt, f"{rotulo!r} vazou no prompt de {slot}"


def test_o_plano_de_geracao_emite_um_briefing_por_peca_e_formato():
    """A porta real do produto: quantos briefings saem de um conceito."""
    from app.criativo.studio import PedidoDeGeracao
    from app.criativo.studio.adaptador import montar_plano

    lote = saida_do_studio(1)
    lote.pecas[0].direcao_de_arte = DirecaoDeArte.model_validate(DIRECAO)
    plano = montar_plano(
        saida=lote,
        pedido=PedidoDeGeracao(
            run_ref="crrun_" + "c" * 24,
            selected_creative_refs=[lote.pecas[0].ref],
            format_ids=SLOTS,
        ),
        caminhos_aprovados=frozenset([f"/pecas/{lote.pecas[0].ref}"]),
        contexto_do_publico="Estudante de ensino médio da rede pública.",
        objetivo="OUTCOME_TRAFFIC",
        familia_cromatica=FAMILIA,
    )
    assert plano.pode_executar, plano.bloqueios
    assert len(plano.briefings) == len(SLOTS)
    assert {b.formato_slot for b in plano.briefings} == set(SLOTS)
    # Uma linhagem só: as quatro peças são o MESMO conceito em canvases diferentes.
    assert {b.linhagem.creative_ref for b in plano.briefings} == {lote.pecas[0].ref}
