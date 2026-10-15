"""Congela os pontos do código que alcançam um verbo de escrita do Google Ads.

Varre volc_ads, backend/app, scripts e tools/freedom-lab/src (todos os arquivos,
inclusive testes de pacote como testes_*.py), em qualquer nível (função ou módulo):
- acesso a atributo com nome de RPC de escrita (mutate, mutate_*, upload_*_conversions,
  apply/dismiss_recommendation, create_customer_client, offline user data jobs…),
  chamado ou só guardado em variável (`m = svc.mutate`);
- string literal com esses nomes (pega `getattr(svc, "mutate")`);
- `getattr` com nome montado em tempo de execução (`"mut" + "ate"`, f-string, chamada).
Qualquer ponto novo exige entrar em PERMITIDOS num commit revisado. As guardas dos
pontos de escrita real são conferidas pela AST da função, não por substring.
Medido em 15/10/2026 (Data Manager acrescentada pelo W14). Cada regra tem contraprova abaixo: sem ela, o teste falha.
"""
import ast
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
BASES = ("volc_ads", "backend/app", "tools/freedom-lab/src", "scripts")
VERBO = re.compile(
    r"^(mutate|mutate_(?!operations?$|operation_responses$|error$)\w+"
    r"|upload_(click|call)_conversions|upload_conversion_adjustments|upload_user_data"
    r"|apply_recommendation|dismiss_recommendation|create_customer_client"
    r"|create_offline_user_data_job|add_offline_user_data_job_operations"
    r"|run_offline_user_data_job|move_manager_link"
    # Data Manager (W14): o porto do transporte e o RPC do SDK oficial
    r"|ingerir|ingest_events|ingest_ad_events)$")
#: O endereço da Data Manager em string de código (docstring não conta): quem o
#: escreve fala com o Google sem passar pelo porto `ingerir`.
ENDERECO = re.compile(r"datamanager\.googleapis\.com|events:ingest")

PERMITIDOS = {
    # pontos de escrita real: guardados por modo.exigir_leitura_apenas (conferido abaixo)
    ("volc_ads/gads/client.py", "mutar", "mutate"),
    ("volc_ads/gestao/lote.py", "enviar", "mutate"),
    ("volc_ads/gestao/lote.py", "aplicar_recomendacoes", "apply_recommendation"),
    ("volc_ads/gestao/lote.py", "aplicar_recomendacoes", "dismiss_recommendation"),
    # validate_only fixo em True (conferido abaixo)
    ("volc_ads/gads/client.py", "validar_mutacoes", "mutate"),
    ("volc_ads/campanha/pmax.py", "validar_pos_criacao", "mutate_campaign_goal_configs"),
    # Data Manager (W14): validateOnly literal True e o envio real guardado
    ("backend/app/trafego/conversao_offline/application/enviar.py", "validar_no_google", "ingerir"),
    ("backend/app/trafego/conversao_offline/application/enviar.py", "enviar_de_verdade", "ingerir"),
    # o único lugar que conhece o endereço é o transporte HTTP
    ("backend/app/trafego/conversao_offline/infrastructure/data_manager_http.py", "<modulo>",
     "endereco:datamanager.googleapis.com"),
    ("backend/app/trafego/conversao_offline/infrastructure/data_manager_http.py", "ingerir",
     "endereco:events:ingest"),
    # testes que procuram a ausência de escrita por nome
    ("volc_ads/copy/testes_termos_de_busca.py", "test_coleta_faz_uma_gaql_somente_leitura_no_search_term_view", "str:mutate"),
    ("volc_ads/gestao/testes_lote.py", "_erro", "str:mutate"),
    ("volc_ads/testes_entrega.py", "test_nao_escreve_nada", "str:mutate"),
    ("volc_ads/testes_entrega.py", "test_nao_escreve_nada", "str:mutate_ad_groups"),
    ("volc_ads/testes_entrega.py", "test_nao_escreve_nada", "str:mutate_campaigns"),
    ("volc_ads/testes_forca.py", "test_o_modulo_nao_escreve_nada", "str:mutate"),
    # getattr dinâmico sobre protos/campos, conferido à mão em 15/10 (não alcança serviço)
    ("backend/app/motor_pautas/testes/test_ficha.py", "test_todo_nivel_derivavel_e_alcancavel", "getattr-dinamico"),
    ("backend/app/trafego/meta_execucao/capacidades.py", "valor_flag", "getattr-dinamico"),
    ("scripts/creditoup_ssh_check.py", "validate", "getattr-dinamico"),
    ("volc_ads/campanha/display_ops.py", "aplicar_campanha", "getattr-dinamico"),
    ("volc_ads/campanha/display_ops.py", "aplicar_rda", "getattr-dinamico"),
    ("volc_ads/campanha/display_ops.py", "ops_criterios_de_campanha", "getattr-dinamico"),
    ("volc_ads/campanha/testes_display.py", "test_nenhum_objeto_display_nasce_ligado", "getattr-dinamico"),
}


def achados_no_fonte(rel: str, fonte: str):
    arvore = ast.parse(fonte)
    pais = {c: p for p in ast.walk(arvore) for c in ast.iter_child_nodes(p)}

    def contexto(n):
        while n in pais:
            n = pais[n]
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return n.name
        return "<modulo>"

    docstrings = {id(b[0].value) for b in
                  [getattr(n, "body", None) for n in ast.walk(arvore)
                   if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
                  if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant)}

    for n in ast.walk(arvore):
        if (isinstance(n, ast.Constant) and isinstance(n.value, str)
                and id(n) not in docstrings and ENDERECO.search(n.value)):
            yield (rel, contexto(n), "endereco:" + ENDERECO.search(n.value).group(0))
        if isinstance(n, ast.Attribute) and VERBO.match(n.attr):
            yield (rel, contexto(n), n.attr)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and VERBO.match(n.value):
            yield (rel, contexto(n), "str:" + n.value)
        elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "getattr"
              and len(n.args) >= 2 and isinstance(n.args[1], (ast.BinOp, ast.JoinedStr, ast.Call))):
            yield (rel, contexto(n), "getattr-dinamico")
        elif isinstance(n, ast.alias) and VERBO.match(n.name.rsplit(".", 1)[-1]):
            yield (rel, contexto(n), "import:" + n.name)


def achados():
    for base in BASES:
        for arq in sorted((RAIZ / base).rglob("*.py")):
            rel = str(arq.relative_to(RAIZ))
            yield from achados_no_fonte(rel, arq.read_text(encoding="utf-8"))


def test_escrita_google_so_nos_pontos_conhecidos():
    novos = set(achados()) - PERMITIDOS
    assert not novos, sorted(novos)


# ---------- guardas pela AST ----------

def _funcao(fonte: str, nome: str) -> ast.FunctionDef:
    return next(n for n in ast.walk(ast.parse(fonte))
                if isinstance(n, ast.FunctionDef) and n.name == nome)


def _chamadas(fn, attr):
    return [n for n in ast.walk(fn) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr == attr]


def primeira_instrucao_e_guarda(fonte: str, nome: str) -> bool:
    corpo = list(_funcao(fonte, nome).body)
    if corpo and isinstance(corpo[0], ast.Expr) and isinstance(corpo[0].value, ast.Constant):
        corpo = corpo[1:]  # docstring
    c = corpo[0].value if corpo and isinstance(corpo[0], ast.Expr) else None
    return (isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
            and c.func.attr == "exigir_leitura_apenas"
            and isinstance(c.func.value, ast.Name) and c.func.value.id == "modo")


def guarda_antes_do_verbo(fonte: str, nome: str, verbos: set[str],
                          guarda: str = "exigir_leitura_apenas") -> bool:
    fn = _funcao(fonte, nome)
    guardas = [c.lineno for c in _chamadas(fn, guarda)]
    usos = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Attribute) and n.attr in verbos]
    return bool(guardas) and bool(usos) and min(guardas) < min(usos)


def validate_only_sempre_true(fonte: str, nome: str) -> bool:
    fn = _funcao(fonte, nome)
    valores = [a.value for a in ast.walk(fn) if isinstance(a, ast.Assign)
               for t in a.targets if isinstance(t, ast.Attribute) and t.attr == "validate_only"]
    valores += [k.value for k in ast.walk(fn) if isinstance(k, ast.keyword) and k.arg == "validate_only"]
    return bool(valores) and all(isinstance(v, ast.Constant) and v.value is True for v in valores)


def _ler(rel):
    return (RAIZ / rel).read_text(encoding="utf-8")


def test_guardas_reais_pela_ast():
    assert primeira_instrucao_e_guarda(_ler("volc_ads/gads/client.py"), "mutar")
    assert validate_only_sempre_true(_ler("volc_ads/gads/client.py"), "validar_mutacoes")
    assert validate_only_sempre_true(_ler("volc_ads/campanha/pmax.py"), "validar_pos_criacao")
    assert guarda_antes_do_verbo(_ler("volc_ads/gestao/lote.py"), "enviar", {"mutate"})
    w14 = "backend/app/trafego/conversao_offline/application/enviar.py"
    assert validate_only_sempre_true(_ler(w14), "validar_no_google")
    # W14 tem trava PRÓPRIA por chamada (chave.consumir), não a global do forge:
    # aberta por outra requisição, a global liberaria o envio de conversões junto.
    assert guarda_antes_do_verbo(_ler(w14), "enviar_de_verdade", {"ingerir"}, guarda="consumir")
    assert "exigir_leitura_apenas" not in _ler(w14)
    assert guarda_antes_do_verbo(_ler("volc_ads/gestao/lote.py"), "aplicar_recomendacoes",
                                 {"apply_recommendation", "dismiss_recommendation"})


# ---------- contraprovas: cada regra falha sem a guarda ----------

def test_contraprova_varredura_pega_o_que_o_filtro_antigo_deixava_passar():
    fonte = '''
svc.mutate(request=r)                       # nível de módulo
def f(svc):
    m = svc.mutate                          # guardado em variável
    getattr(svc, "mut" + "ate")()           # nome montado
    getattr(svc, "mutate")()                # nome literal
    svc.upload_click_conversions(request=r)
    svc.dismiss_recommendation(request=r)
    svc.create_customer_client(request=r)
from x import mutate_campaigns as _m
'''
    tipos = {a[2] for a in achados_no_fonte("x.py", fonte)}
    assert {"mutate", "getattr-dinamico", "str:mutate", "upload_click_conversions",
            "dismiss_recommendation", "create_customer_client",
            "import:mutate_campaigns"} <= tipos
    assert ("x.py", "<modulo>", "mutate") in set(achados_no_fonte("x.py", fonte))


def test_contraprova_endereco_da_data_manager_fora_do_transporte():
    fonte = '''"""Fala de datamanager.googleapis.com só na docstring."""
import httpx
def atalho(c):
    """events:ingest aqui também é só texto."""
    return c.post("https://datamanager.googleapis.com/v1/" + "events:ingest", json={})
'''
    assert set(achados_no_fonte("x.py", fonte)) == {
        ("x.py", "atalho", "endereco:datamanager.googleapis.com"),
        ("x.py", "atalho", "endereco:events:ingest")}


def test_contraprova_comentario_nao_e_guarda():
    fonte = '''
def mutar(c, ops):
    """doc"""
    # modo.exigir_leitura_apenas("finge")
    c.mutate(ops)
'''
    assert not primeira_instrucao_e_guarda(fonte, "mutar")


def test_contraprova_validate_only_false_depois_do_true():
    fonte = '''
def validar_mutacoes(req):
    req.validate_only = True
    req.validate_only = False
'''
    assert not validate_only_sempre_true(fonte, "validar_mutacoes")
    assert not validate_only_sempre_true("def validar_mutacoes(s):\n    s.mutate(validate_only=False)\n",
                                         "validar_mutacoes")


def test_contraprova_guarda_depois_do_verbo():
    fonte = '''
def enviar(svc, modo):
    svc.mutate(request=r)
    modo.exigir_leitura_apenas("tarde demais")
'''
    assert not guarda_antes_do_verbo(fonte, "enviar", {"mutate"})
