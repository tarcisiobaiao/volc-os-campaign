"""scripts/mascarar-segredos.sh não deixa passar nenhum formato de segredo conhecido.

Cada amostra traz um segredo FALSO (gerado aqui, sem valor real) e o teste exige
que o pedaço secreto não apareça na saída. Também confere que texto comum
(contagens, caminhos, nomes de variável) passa intacto — a máscara não pode
apagar a evidência.
"""
import pathlib
import subprocess

import pytest

FILTRO = pathlib.Path(__file__).resolve().parents[1] / "mascarar-segredos.sh"


def mascarar(texto: str) -> str:
    return subprocess.run(["bash", str(FILTRO)], input=texto, capture_output=True, text=True, check=True).stdout


FALSO = "Zq9fK2mPw7xR4tYb8nVc3LdH"  # 24 chars, não é segredo de nada

VAZAMENTOS = [
    ("jwt", f"apikey eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.{FALSO}", ["eyJyb2xlIjoiYW5vbiJ9", FALSO]),
    ("bearer", f"Authorization: Bearer {FALSO}", [FALSO]),
    ("bearer-minusculo", f"authorization: bearer {FALSO}", [FALSO]),
    ("connstring-postgres", f"postgres://postgres:{FALSO}@db.example.invalid:5432/postgres", [FALSO]),
    ("connstring-postgresql", f"DATABASE_URL=postgresql://u:{FALSO}@h/db", [FALSO]),
    ("supabase-access-token", f"token sbp_{FALSO}", [FALSO]),
    ("stripe-like", f"STRIPE=sk_live_{FALSO}", [FALSO]),
    ("openai-like", f"sk-proj-{FALSO}", [FALSO]),
    ("sk-underscore", f"x sk_{FALSO} y", [FALSO]),
    ("github", f"ghp_{FALSO}", [FALSO]),
    ("google-api", f"AIza{FALSO}abc", [FALSO]),
    ("slack", f"xoxb-{FALSO}", [FALSO]),
    ("password-igual", f"PASSWORD={FALSO}", [FALSO]),
    ("senha-dois-pontos", f'"senha": "{FALSO}"', [FALSO]),
    ("service-role-key", f"SUPABASE_SERVICE_ROLE_KEY={FALSO}", [FALSO]),
    ("apikey-header", f"apikey: {FALSO}", [FALSO]),
    ("jwt-secret", f"JWT_SECRET={FALSO}", [FALSO]),
    ("senha-com-simbolos", "POSTGRES_PASSWORD=Pq@7!x#Wm$2zR%kL", ["Pq@7!x#Wm$2zR%kL"]),
    ("sb-secret", f"SB=sb_secret_{FALSO}", [FALSO]),
    ("basic", f"Authorization: Basic {FALSO}", [FALSO]),
    ("token-scheme", f"Authorization: Token {FALSO}", [FALSO]),
    ("json-aspas-escapadas", '{\\"password\\":\\"' + FALSO + '\\"}', [FALSO]),
    ("json-aspas-escapadas-apikey", '\\"apikey\\": \\"' + FALSO + '\\"', [FALSO]),
    ("createclient-posicional", f'const db = createClient(URL, "{FALSO}");', [FALSO]),
    ("createclient-posicional-aspas-simples", f"createClient('https://x.invalid', '{FALSO}')", [FALSO]),
    ("bearer-maiusculo", f"AUTHORIZATION: BEARER {FALSO}", [FALSO]),
    ("supabaseclient-posicional", f'new SupabaseClient("https://x.invalid", "{FALSO}")', [FALSO]),
    ("pem-uma-linha", "-----BEGIN PRIVATE KEY-----MIIEvQIBADANBgkqhkiG9w0BAQEFAAS" + FALSO + "-----END PRIVATE KEY-----", [FALSO, "MIIEvQIBADANBgkqhkiG9w0BAQEFAAS"]),
    ("pem-multilinha", "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA" + FALSO + "\nQWERTYUIOPASDFGHJKL0987654321\n-----END RSA PRIVATE KEY-----", [FALSO, "QWERTYUIOPASDFGHJKL0987654321"]),
    ("connstring-simbolos", "postgres://u:Pq@7!x#Wm$2@h:5432/db", ["7!x#Wm$2"]),
]


@pytest.mark.parametrize("nome,linha,segredos", VAZAMENTOS, ids=[v[0] for v in VAZAMENTOS])
def test_formato_nao_vaza(nome, linha, segredos):
    saida = mascarar(linha + "\n")
    for s in segredos:
        assert s not in saida, f"{nome}: vazou {s!r} em {saida!r}"
    assert "MASCARAD" in saida, f"{nome}: nada foi mascarado em {saida!r}"


EVIDENCIA_INTACTA = [
    "    173 \"GET /rest/v1/niche_conversion_mappings HTTP/1.1\" 200",
    "5:const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get(\"SUPABASE_SERVICE_ROLE_KEY\")!;",
    "FUNCTIONS_VERIFY_JWT=false",
    "8:const db = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);",
    "DISABLE_SIGNUP=false",
    "raw_events|1918|0|1859|2026-09-25 00:00:02.655613-03",
    "anon|2313|WITH pgrst_source AS ( SELECT \"public\".\"niche_conversion_mappings\".* FROM",
]


@pytest.mark.parametrize("linha", EVIDENCIA_INTACTA)
def test_evidencia_passa_intacta(linha):
    assert mascarar(linha + "\n").rstrip("\n") == linha
