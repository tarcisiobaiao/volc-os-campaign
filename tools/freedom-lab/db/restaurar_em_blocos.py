"""Corta um dump --schema-only em blocos, só em fronteira de objeto ("-- Name:").

Uso: python3 -I restaurar_em_blocos.py <dump.sql> <dir-saida>
Medido pelo W4 em 15/10/2026: numa sessão única o backend do restore caiu perto do fim
sem o psql registrar ERROR, e a base ficou sem gatilhos e policies. Em blocos, cada um
é conferido e refeito uma vez se cair. CREATE SCHEMA public sai (a imagem já tem).
"""
import re
import sys


def main(dump: str, saida: str, linhas_por_bloco: int = 3000) -> int:
    txt = open(dump, encoding="utf-8").read().replace("\nCREATE SCHEMA public;\n", "\n")
    cab = txt[:txt.index("\n--\n-- Name:")]
    partes = re.split(r"(?=\n--\n-- Name: )", txt[len(cab):])
    bloco, n, i = [], 0, 0
    for parte in partes:
        bloco.append(parte)
        n += parte.count("\n")
        if n > linhas_por_bloco:
            open(f"{saida}/{i:02d}.sql", "w", encoding="utf-8").write(cab + "".join(bloco))
            i, bloco, n = i + 1, [], 0
    if bloco:
        open(f"{saida}/{i:02d}.sql", "w", encoding="utf-8").write(cab + "".join(bloco))
        i += 1
    return i


if __name__ == "__main__":
    print(main(sys.argv[1], sys.argv[2]))
