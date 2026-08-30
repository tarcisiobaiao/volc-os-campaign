"""O contrato com `docs/growth-engine/legado-n8n/regras-canonicas.json`.

## Dois documentos, dois propósitos

| | arquivo do Agente G | `trafego_regra_otimizacao` |
|---|---|---|
| é | inventário forense do que o legado DECLAROU | contrato do que pode ser PUBLICADO |
| `null` significa | "não sabemos" (aviso 1 do arquivo) | coluna sem valor |
| autoridade sobre | o que existia no n8n | o que pode gastar verba |

O mapeamento entre os dois é o que revela a distância — e a distância é o
achado. Medido em 26/08/2026: as 19 regras estão em `estado: proposta` e
**nenhuma é publicável como está**.

Isso não é defeito de nenhum dos dois lados. No n8n o limite morava dentro do
`if` do workflow; aqui ele tem de ser DECLARADO para poder ser imposto pelo
gatilho `trafego_proposta_respeita_regra`. Uma regra migrada sem cooldown, sem
amostra e sem responsável nomeado é uma automação com autorização ilimitada —
e é exatamente isso que a v10_02 recusa.

## O que estas provas defendem

1. **nenhum campo do arquivo é ignorado em silêncio** — um campo ignorado é um
   limite que o arquivo pretendia declarar e a regra rodaria sem;
2. **`estado` e publicabilidade concordam nos dois sentidos** — uma regra que se
   diz `proposta` não pode ser publicável, e uma que virou publicável não pode
   continuar dizendo `proposta`;
3. **toda lacuna tem nome**, para o trabalho de fechá-la ser dimensionável.

Se o arquivo sumir, os testes que dependem dele pulam com a razão dita em
`pytest -rs` — e `test_o_contrato_esta_declarado` continua rodando.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.trafego import intencao as it  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parents[2]
ARQUIVO = RAIZ / "docs" / "growth-engine" / "legado-n8n" / "regras-canonicas.json"


def _documento():
    if not ARQUIVO.exists():
        pytest.skip(
            f"{ARQUIVO.relative_to(RAIZ)} ainda nao existe (Agente G). "
            f"Enquanto isso, `app/trafego/intencao.py` E o contrato.")
    return json.loads(ARQUIVO.read_text(encoding="utf-8"))


def _regras():
    bruto = _documento()
    if isinstance(bruto, dict):
        bruto = bruto.get("regras", bruto.get("rules", []))
    if not isinstance(bruto, list) or not bruto:
        pytest.fail(f"{ARQUIVO.name} nao traz uma lista de regras.")
    return bruto


# ═══════════════════════════════════════════════════════════════════════════
# 1. O CONTRATO EXISTE, COM OU SEM O ARQUIVO
# ═══════════════════════════════════════════════════════════════════════════


def test_o_contrato_esta_declarado():
    """Roda SEMPRE. Sem ele, um `skip` global deixaria a suite verde sem
    nenhuma verificacao do contrato — e `skip` mudo conta como sucesso."""
    assert callable(it.validar_regra_canonica)
    assert callable(it.adaptar_regra_do_legado)
    assert set(it.NIVEIS_DE_AUTONOMIA) == {"T0", "T1"}
    campos = set(it.RegraDeOtimizacao.__dataclass_fields__)
    assert set(it._AMOSTRA_OBRIGATORIA) <= campos
    assert set(it._LIMITE_OBRIGATORIO) <= campos


def test_toda_coluna_apontada_pelo_mapa_existe_de_verdade():
    """Um mapa que aponta para coluna inexistente e pior que mapa nenhum: ele
    parece cobertura e nao traduz nada."""
    campos = set(it.RegraDeOtimizacao.__dataclass_fields__)
    alvos = {v for v in it.MAPA_DO_LEGADO.values() if v}
    assert alvos <= campos, f"aponta para o que nao existe: {alvos - campos}"
    assert set(it.SEM_EQUIVALENTE_NO_LEGADO) <= campos


# ═══════════════════════════════════════════════════════════════════════════
# 2. ⚠️ NADA DO ARQUIVO É IGNORADO EM SILÊNCIO
# ═══════════════════════════════════════════════════════════════════════════


def test_nenhum_campo_do_arquivo_fica_de_fora_do_mapa():
    """A prova mais importante deste arquivo.

    Um campo do arquivo que o mapa nao conhece seria descartado sem aviso — e o
    caso caro e concreto: uma regra com `teto_de_orcamento` num nome que o
    adaptador nao le rodaria SEM TETO, que e o oposto do que o arquivo dizia.

    Quando o Agente G acrescentar um campo, este teste falha e diz o nome dele.
    O conserto e classifica-lo: coluna do schema, ou forense declarado.
    """
    do_arquivo = set()
    for regra in _regras():
        do_arquivo |= set(regra)
    desconhecidos = sorted(do_arquivo - set(it.MAPA_DO_LEGADO))
    assert not desconhecidos, (
        f"campo(s) do arquivo fora de MAPA_DO_LEGADO: {desconhecidos}. "
        f"Classifique cada um: coluna de trafego_regra_otimizacao, ou forense "
        f"(valor None no mapa).")


def test_o_mapa_nao_promete_campo_que_o_arquivo_nao_tem():
    """O outro sentido: uma entrada no mapa para um campo que sumiu do arquivo e
    traducao morta, e ela esconde que o dado deixou de chegar."""
    do_arquivo = set()
    for regra in _regras():
        do_arquivo |= set(regra)
    orfas = sorted(set(it.MAPA_DO_LEGADO) - do_arquivo)
    assert not orfas, f"entrada(s) do mapa sem campo no arquivo: {orfas}"


# ═══════════════════════════════════════════════════════════════════════════
# 3. `estado` E PUBLICABILIDADE CONCORDAM — NOS DOIS SENTIDOS
# ═══════════════════════════════════════════════════════════════════════════


def test_regra_em_proposta_nao_pode_ser_publicavel():
    """Se uma regra `proposta` passasse no validador, o `estado` estaria
    mentindo — e alguem a publicaria confiando num rotulo que nao vale."""
    enganosas = []
    for regra in _regras():
        if regra.get("estado") == "proposta":
            pode, _ = it.publicavel(regra)
            if pode:
                enganosas.append(regra.get("id"))
    assert not enganosas, (
        f"regra(s) marcadas `proposta` que JA sao publicaveis: {enganosas}. "
        f"Ou o estado esta desatualizado, ou o validador afrouxou.")


def test_regra_fora_de_proposta_tem_de_ser_publicavel():
    """O sentido que protege contra afrouxar o arquivo em vez de fechar a
    lacuna: promover uma regra a `adotada` sem os campos declarados quebra
    aqui, e nao no meio de uma rodada de decisao gastando verba."""
    quebradas = []
    for regra in _regras():
        if regra.get("estado") in ("proposta", None):
            continue
        pode, lacunas = it.publicavel(regra)
        if not pode:
            quebradas.append(f"{regra.get('id')} [{regra.get('estado')}]: "
                             f"{'; '.join(lacunas)}")
    assert not quebradas, "\n".join(quebradas)


def test_o_inventario_do_legado_esta_todo_em_proposta():
    """Medido em 26/08/2026: 19 de 19. Este teste nao existe para congelar o
    numero — ele existe para o dia em que a primeira regra sair de `proposta`
    ser um evento VISIVEL, e nao uma linha que passou num diff."""
    estados = {r.get("estado") for r in _regras()}
    assert estados <= {"proposta", "adotada", "descartada"}, (
        f"estado(s) fora do vocabulario conhecido: {estados}")


# ═══════════════════════════════════════════════════════════════════════════
# 4. TODA LACUNA TEM NOME
# ═══════════════════════════════════════════════════════════════════════════


def test_toda_regra_nao_publicavel_diz_o_que_falta():
    """Uma recusa sem motivo obriga alguem a reproduzir a avaliacao a mao. O
    trabalho de fechar as lacunas so e dimensionavel se cada uma tiver nome."""
    mudas = []
    for regra in _regras():
        pode, lacunas = it.publicavel(regra)
        if not pode and not lacunas:
            mudas.append(regra.get("id"))
    assert not mudas, f"recusada(s) sem motivo declarado: {mudas}"


def test_as_chaves_do_arquivo_sao_unicas():
    """`(chave, versao)` e unico no banco (`trafego_regra_versao_ux`). Duas
    linhas iguais passariam no validador uma a uma e quebrariam na carga —
    tarde, e no meio de um backfill."""
    vistos, duplicadas = set(), []
    for regra in _regras():
        chave = regra.get("id")
        if chave in vistos:
            duplicadas.append(chave)
        vistos.add(chave)
    assert not duplicadas, f"id(s) repetido(s): {duplicadas}"


def test_toda_regra_declara_de_onde_veio():
    """`origem_legado` vira `fonte` na coluna. Sem ela, uma regra migrada do n8n
    fica indistinguivel de uma que alguem inventou numa terca-feira — e no dia
    em que ela passar a errar, ninguem sabe onde procurar o original."""
    sem_origem = []
    for regra in _regras():
        origem = regra.get("origem_legado") or {}
        if not origem.get("flow"):
            sem_origem.append(regra.get("id"))
    assert not sem_origem, f"regra(s) sem origem no legado: {sem_origem}"


def test_a_chave_derivada_do_id_passa_na_check_do_banco():
    """`trafego_regra_chave_valida` exige `^[a-z][a-z0-9_]{2,63}$`. Um `id` com
    hifen ou maiuscula passaria por todo o pipeline e falharia no INSERT."""
    invalidas = []
    for regra in _regras():
        campos, _ = it.adaptar_regra_do_legado(regra)
        chave = campos.get("chave", "")
        if not (chave and chave[0].isalpha() and chave == chave.lower()
                and chave.replace("_", "").isalnum() and 3 <= len(chave) <= 64):
            invalidas.append(chave)
    assert not invalidas, f"id(s) que a CHECK do banco recusaria: {invalidas}"


def test_o_adaptador_nao_inventa_valor_para_null():
    """⚠️ O aviso 1 do proprio arquivo: `null` significa NAO SABEMOS.

    Preencher um cooldown de 24h porque a coluna e `NOT NULL` transformaria uma
    lacuna conhecida numa politica com aparencia de decidida — e ela gastaria
    verba com o carimbo de "declarada".
    """
    for regra in _regras():
        campos, lacunas = it.adaptar_regra_do_legado(regra)
        if regra.get("cooldown_horas") is None:
            assert "cooldown_horas" not in campos
            assert "cooldown_horas" in lacunas
        if regra.get("atraso_de_conversao_dias") is None:
            assert "atraso_conversao_dias" not in campos
            assert "atraso_conversao_dias" in lacunas
        if regra.get("teto_de_orcamento") is None:
            assert "teto_orcamento_micros" not in campos


def test_frescor_maximo_e_a_coluna_que_o_legado_nunca_teve():
    """A lacuna mais cara do inventario inteiro: nenhuma regra do n8n declarava
    idade maxima do dado. Sem piso de frescor, uma regra decidia com o que
    estivesse na mao — e uma leitura de tres semanas atras valia tanto quanto a
    de hoje."""
    assert "frescor_maximo_horas" in it.SEM_EQUIVALENTE_NO_LEGADO
    for regra in _regras():
        _, lacunas = it.adaptar_regra_do_legado(regra)
        assert any(l.startswith("frescor_maximo_horas") for l in lacunas)
