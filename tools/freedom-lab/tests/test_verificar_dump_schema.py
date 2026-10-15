"""O filtro de dump só-schema pega cada forma de dado que o grep antigo deixava passar,
e aceita o que um schema real tem: INSERT dentro de função e coluna chamada copy."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "db"))
from verificar_dump_schema import motivos  # noqa: E402

SCHEMA_OK = '''
CREATE TABLE public.criativo (id int, copy jsonb DEFAULT '{}'::jsonb NOT NULL);
CREATE FUNCTION public.f() RETURNS trigger LANGUAGE plpgsql AS $_$
BEGIN
  INSERT INTO public.log VALUES (1);
  copy_x := 1;
  RETURN NEW;
END $_$;
CREATE FUNCTION public.g() RETURNS int LANGUAGE sql BEGIN ATOMIC
  INSERT INTO public.log VALUES (2);
  SELECT 1;
END;
COMMENT ON TABLE public.criativo IS 'INSERT INTO não é dado aqui; COPY também não';
'''


def test_schema_real_passa():
    assert motivos(SCHEMA_OK) == []


@pytest.mark.parametrize("dado", [
    "copy public.users (id) from stdin;\n1\n\\.\n",
    "\\copy public.users from stdin\n",
    "   COPY public.users (id) FROM stdin;\n",
    "INSERT\tINTO public.users VALUES (1);\n",
    "DO $$ BEGIN INSERT INTO public.users VALUES (1); END $$;\n",
    "WITH x AS (SELECT 1) INSERT INTO public.users SELECT * FROM x;\n",
    "SELECT pg_catalog.setval('public.users_id_seq', 48213, true);\n",
    "SELECT lo_create(1); SELECT lowrite(lo_open(1, 131072), 'x');\n",
    "--\n-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: postgres\n--\n",
    "UPDATE public.users SET email = 'x';\n",
])
def test_cada_forma_de_dado_e_recusada(dado):
    assert motivos(SCHEMA_OK + dado), dado
