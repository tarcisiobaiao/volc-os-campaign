"""Recusa dump que carregue dado. Uso: python3 -I verificar_dump_schema.py <dump.sql>

Um filtro por linha não serve: o schema de produção tem 98 linhas "INSERT" dentro de corpos de função e colunas chamadas "copy"
e dado pode vir em minúsculo, indentado, por \\copy, setval,
DO $$…$$, WITH … INSERT ou large object. Aqui o dump é lido como SQL: corpos
dollar-quoted, strings e comentários saem, e o que sobra no nível de comando não pode
conter nenhuma forma de dado. O TOC do pg_dump também não pode ter entrada de dado.
Sai 0 se só schema; 1 com o motivo (sem imprimir conteúdo do dump).
"""
import re
import sys

TOC_DE_DADO = re.compile(r"^-- (Data for Name:|Name: .*; Type: (TABLE DATA|SEQUENCE SET|BLOB|LARGE OBJECT|BLOBS))", re.M)
DOLAR = re.compile(r"(\$[A-Za-z_0-9]*\$).*?\1", re.S)
ATOMICO = re.compile(r"(?is)\bBEGIN\s+ATOMIC\b.*?\bEND\s*;")
STRING = re.compile(r"(?:E)?'(?:[^']|'')*'", re.S)
COMENTARIO = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)
PROIBIDO = [
    # comando COPY/\copy (não a coluna chamada "copy"): copy <alvo> [(cols)] from|to
    ("copy", re.compile(r"(?im)^\s*\\?copy\s+(\S+|\(.*?\))(\s*\([^)]*\))?\s+(from|to)\b", re.S)),
    ("insert", re.compile(r"(?i)\binsert\s+into\b")),
    ("do-bloco", re.compile(r"(?im)^\s*do\b")),
    ("setval", re.compile(r"(?i)\bsetval\s*\(")),
    ("large-object", re.compile(r"(?i)\blo_(create|write|open|import|from_bytea|put)\s*\(")),
    ("update-delete", re.compile(r"(?im)^\s*(update|delete\s+from|truncate)\b")),
]


def motivos(texto: str) -> list[str]:
    erros = [f"TOC de dado: {m.group(1) or m.group(2)}" for m in TOC_DE_DADO.finditer(texto)][:3]
    sql = COMENTARIO.sub(" ", STRING.sub("''", ATOMICO.sub(" ", DOLAR.sub("$$ $$", texto))))
    erros += [f"{nome} no nível de comando" for nome, rx in PROIBIDO if rx.search(sql)]
    return erros


def main(caminho: str) -> int:
    erros = motivos(open(caminho, encoding="utf-8", errors="replace").read())
    for e in erros:
        print("dump recusado:", e, file=sys.stderr)
    return 1 if erros else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
