from funnelforge.pipeline import phrase_registry
from funnelforge.pipeline.uniqueness import jaccard
from funnelforge.pipeline.validators.checks import run_validators

A = ("<!-- wp:paragraph --><p>O saque aniversario do FGTS permite antecipar "
     "parte do saldo pela Caixa.</p><!-- /wp:paragraph -->")
B = ("<!-- wp:paragraph --><p>O saque aniversario do FGTS permite antecipar "
     "parte do saldo pela Caixa.</p><!-- /wp:paragraph -->")
C = ("<!-- wp:paragraph --><p>Como emitir a segunda via da conta de luz pela "
     "distribuidora regional.</p><!-- /wp:paragraph -->")


def test_jaccard_ignores_html_boilerplate():
    # identical visible text -> 1.0 despite wp comments
    assert jaccard(A, B) == 1.0
    # different topics -> low overlap
    assert jaccard(A, C) < 0.35


def test_uniqueness_flags_duplicate_against_prior():
    issues = run_validators(["uniqueness"], A,
                            {"prior_drafts": [B], "jaccard_threshold": 0.35})
    assert any(i.code == "duplicate_content" for i in issues)


def test_uniqueness_passes_distinct_and_no_priors():
    assert run_validators(["uniqueness"], A,
                          {"prior_drafts": [C], "jaccard_threshold": 0.35}) == []
    assert run_validators(["uniqueness"], A, {}) == []   # no priors -> no-op


# ---------------------------------------------------------------------------
# T1C review fix: two genuinely-distinct pages sharing the MANDATORY
# compliance/nav/byline boilerplate kit (AVISO + "Sobre o Site" RODAPE +
# BYLINE + NAV) must NOT be flagged as duplicates -- only pages whose
# DISTINCTIVE body content actually overlaps should trip the guard.
# ---------------------------------------------------------------------------

_NAV = ("<!-- wp:paragraph {\"align\":\"center\"} -->"
        "<p class=\"has-text-align-center\">Home | Beneficios | Credito e "
        "FGTS | Bancos e Apps | Direitos</p><!-- /wp:paragraph -->")

_AVISO = ("<!-- wp:paragraph {\"align\":\"center\"} -->"
          "<p class=\"has-text-align-center\"><small><em>* Você "
          "permanecerá neste mesmo site *</em></small></p>"
          "<!-- /wp:paragraph -->")

_RODAPE = ("<!-- wp:group --><div class=\"wp-block-group\">"
           "<h3>Sobre o Site</h3>"
           "<p>Somos um portal informativo independente de utilidade "
           "pública. Não pede dados pessoais nem qualquer valor. Os "
           "conteúdos são informativos e não têm vínculo, parceria ou "
           "ligação oficial com órgãos públicos ou entidades "
           "governamentais; verifique sempre os canais oficiais. "
           "Financiado por anúncios em parceria com o Google Adsense; não "
           "temos relação com os anunciantes. Não temos relação com "
           "Facebook ou Google (marcas registradas dos respectivos "
           "donos). CNPJ 12.345.678/0001-90.</p></div><!-- /wp:group -->")

_BYLINE = ("<!-- wp:paragraph --><p>Nome: Equipe Credito Up. Credencial: "
           "Redação de jornalismo de serviço.</p><!-- /wp:paragraph -->")


def _boilerplate_page(h1: str, body: str) -> str:
    return (_NAV + _AVISO
            + f"<!-- wp:heading --><h1>{h1}</h1><!-- /wp:heading -->"
            + body + _AVISO + _BYLINE + _RODAPE)


_BODY_ANTECIPACAO = (
    "<!-- wp:heading --><h2>Como funciona a antecipação</h2><!-- /wp:heading -->"
    "<!-- wp:paragraph --><p>O saque aniversário do FGTS permite antecipar "
    "parte do saldo da conta vinculada diretamente pelo aplicativo da "
    "Caixa. A adesão muda a modalidade de saque do fundo de garantia e "
    "pode ser cancelada a qualquer momento pelo titular. O valor liberado "
    "depende do saldo total da conta e segue uma tabela de faixas "
    "definida pela lei que criou a modalidade.</p><!-- /wp:paragraph -->"
    "<!-- wp:heading --><h2>Quem pode aderir à antecipação</h2><!-- /wp:heading -->"
    "<!-- wp:paragraph --><p>Qualquer trabalhador com conta ativa do FGTS "
    "pode aderir à antecipação pelo aplicativo, sem precisar comprovar "
    "motivo. A adesão é gratuita e não exige análise de crédito nem "
    "consulta ao CPF em birôs de proteção.</p><!-- /wp:paragraph -->"
    "<!-- wp:heading --><h2>Perguntas frequentes</h2><!-- /wp:heading -->"
    "<!-- wp:paragraph --><p>Quem tem o nome negativado pode antecipar? "
    "Sim, a operação usa o saldo do próprio FGTS como garantia, então não "
    "há consulta ao Serasa ou SPC.</p><!-- /wp:paragraph -->"
)

_BODY_CONSULTA = (
    "<!-- wp:heading --><h2>Como consultar o saldo do FGTS</h2><!-- /wp:heading -->"
    "<!-- wp:paragraph --><p>A consulta ao saldo do FGTS pode ser feita "
    "gratuitamente pelo aplicativo oficial disponível para celular, sem "
    "precisar ir a uma agência da Caixa. O extrato mostra os depósitos "
    "mensais feitos pelo empregador atual e o histórico de contas de "
    "empregos anteriores, quando existirem.</p><!-- /wp:paragraph -->"
    "<!-- wp:heading --><h2>O que fazer se o saldo não aparecer</h2><!-- /wp:heading -->"
    "<!-- wp:paragraph --><p>Quando o saldo de um período não aparece no "
    "extrato, o motivo costuma ser atraso no recolhimento pelo "
    "empregador. Nesse caso, o trabalhador pode registrar uma reclamação "
    "diretamente pelo aplicativo ou procurar o sindicato da "
    "categoria.</p><!-- /wp:paragraph -->"
    "<!-- wp:heading --><h2>Perguntas frequentes</h2><!-- /wp:heading -->"
    "<!-- wp:paragraph --><p>Preciso ir à agência para consultar o saldo? "
    "Não, a consulta é feita pelo aplicativo ou pelo site oficial do "
    "FGTS.</p><!-- /wp:paragraph -->"
)


def test_uniqueness_ignores_shared_compliance_nav_byline_boilerplate():
    """Two genuinely distinct interior pages -- different H1, different
    2xH2 bodies, different FAQ -- sharing the SAME mandatory nav/AVISO/
    RODAPE/BYLINE compliance kit must NOT be flagged as duplicates."""
    page_a = _boilerplate_page(
        "Antecipação do Saque-Aniversário do FGTS: entenda como funciona",
        _BODY_ANTECIPACAO)
    page_b = _boilerplate_page(
        "Como Consultar o Saldo do FGTS pelo Aplicativo",
        _BODY_CONSULTA)

    similarity = jaccard(page_a, page_b)
    assert similarity < 0.35, f"boilerplate-only overlap over-blocked: {similarity:.2f}"
    assert run_validators(
        ["uniqueness"], page_a,
        {"prior_drafts": [page_b], "jaccard_threshold": 0.35}) == []


def test_uniqueness_still_flags_identical_body_boilerplate_pages():
    """Same compliance kit AND same distinctive body (only the H1 differs)
    must still be flagged -- the boilerplate-aware guard must keep catching
    real near-duplicates, not just get more lenient across the board."""
    page_a = _boilerplate_page(
        "Antecipação do Saque-Aniversário do FGTS: entenda como funciona",
        _BODY_ANTECIPACAO)
    page_c = _boilerplate_page(
        "Saque-Aniversário do FGTS: como funciona a antecipação em 2026",
        _BODY_ANTECIPACAO)

    similarity = jaccard(page_a, page_c)
    assert similarity >= 0.35, f"near-duplicate body not caught: {similarity:.2f}"
    issues = run_validators(
        ["uniqueness"], page_a,
        {"prior_drafts": [page_c], "jaccard_threshold": 0.35})
    assert any(i.code == "duplicate_content" for i in issues)


# ---------------------------------------------------------------------------
# CARD-0007: phrase_registry -- cross-run persistent JSON store backing the
# opening_line_unique validator (see validators/checks.py's presell_opening_line
# / opening_line_unique, and steps.py's _write_ctx / step_publish wiring).
# ---------------------------------------------------------------------------


def test_phrase_registry_normalize_line_ignores_case_accents_emoji_and_punctuation():
    a = phrase_registry.normalize_line("Toque na opção certa e aprenda ✅!!!")
    b = phrase_registry.normalize_line("  TOQUE   NA OPCAO CERTA E APRENDA  ")
    assert a == b == "toque na opcao certa e aprenda"


def test_phrase_registry_record_and_load_roundtrip(tmp_path):
    path = tmp_path / "_phrase_registry.json"
    phrase_registry.record(path, "presell_opening", "Primeira linha de abertura",
                           "funil-a-pr", "run-1")
    phrase_registry.record(path, "presell_opening", "Segunda linha, bem diferente",
                           "funil-b-pr", "run-2")
    assert phrase_registry.load_lines(path, "presell_opening") == [
        "Primeira linha de abertura", "Segunda linha, bem diferente"]
    # a different `kind` namespace never sees these entries
    assert phrase_registry.load_lines(path, "other_kind") == []


def test_phrase_registry_record_is_idempotent_on_normalized_duplicate(tmp_path):
    path = tmp_path / "_phrase_registry.json"
    phrase_registry.record(path, "presell_opening", "Toque na opção certa e ver ✅",
                           "funil-a-pr", "run-1")
    # same phrase, different case/accents/emoji/slug/run -> must NOT duplicate
    phrase_registry.record(path, "presell_opening", "TOQUE NA OPCAO CERTA E VER",
                           "funil-b-pr", "run-2")
    assert phrase_registry.load_lines(path, "presell_opening") == [
        "Toque na opção certa e ver ✅"]


def test_phrase_registry_load_tolerates_missing_file(tmp_path):
    path = tmp_path / "does_not_exist" / "_phrase_registry.json"
    assert phrase_registry.load_lines(path, "presell_opening") == []


def test_phrase_registry_load_tolerates_corrupted_file(tmp_path):
    path = tmp_path / "_phrase_registry.json"
    path.write_text("{not valid json at all", encoding="utf-8")
    assert phrase_registry.load_lines(path, "presell_opening") == []
    path.write_text('{"version": 1, "entries": "not-a-list"}', encoding="utf-8")
    assert phrase_registry.load_lines(path, "presell_opening") == []
    path.write_text('{"version": 1, "entries": [{"kind": "presell_opening"}]}',
                    encoding="utf-8")
    assert phrase_registry.load_lines(path, "presell_opening") == []  # entry missing 'text'


def test_phrase_registry_record_recovers_from_corrupted_file(tmp_path):
    """record() never raises on a corrupted registry -- it just starts fresh."""
    path = tmp_path / "_phrase_registry.json"
    path.write_text("not json { at all", encoding="utf-8")
    phrase_registry.record(path, "presell_opening", "Uma linha nova", "funil-a-pr", "run-1")
    assert phrase_registry.load_lines(path, "presell_opening") == ["Uma linha nova"]


def test_phrase_registry_record_writes_atomically(tmp_path):
    path = tmp_path / "_phrase_registry.json"
    phrase_registry.record(path, "presell_opening", "Uma linha qualquer",
                           "funil-a-pr", "run-1")
    assert path.exists()
    assert not (tmp_path / "_phrase_registry.json.tmp").exists()
