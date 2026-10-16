"""Gera docs/bia-hermes/CATALOGO-COMANDOS.md a partir do catálogo em código.

    cd backend && PYTHONPATH=..:. python3 ../scripts/bia_gerar_catalogo_comandos.py > ../docs/bia-hermes/CATALOGO-COMANDOS.md
"""
from app.agente_bia.comandos import catalogo as c

NOME = {"local_ui": "local_ui — roda na tela", "hermes_safe": "hermes_safe — leitura do Hermes",
        "requires_tool": "requires_tool — exige ferramenta", "external_mutation": "external_mutation — muda algo fora",
        "telegram_only": "telegram_only — só no Telegram"}


def tabela(itens, titulo):
    print(f"## {titulo}\n")
    print("| Comando | Origem | Classe | Na web | Execução | Descrição / motivo |")
    print("|---|---|---|---|---|---|")
    for e in itens:
        args = f" {e.args}".replace("|", "\\|") if e.args else ""
        texto = (e.descricao if e.disponivel else e.motivo).replace("|", "\\|")
        alias = f" (aliases: {', '.join(e.aliases)})" if e.aliases else ""
        print(f"| `/{e.nome}{args}`{alias} | {e.origem} | {e.classe} | {'sim' if e.disponivel else 'não'} "
              f"| {e.execucao or '—'} | {texto} |")
    print()


def main() -> None:
    cat = c.catalogo()
    cont = c.classes_contagem()
    print("# Bia web: catálogo de comandos `/`\n")
    print("Gerado por `scripts/bia_gerar_catalogo_comandos.py` a partir de `backend/app/agente_bia/comandos/catalogo.py`")
    print("(inventário real do Hermes v0.18.0 em `inventario_hermes_v0_18_0.json`: `COMMAND_REGISTRY` com 82 comandos")
    print("e 48 comandos de skill do profile `default`). **Não edite à mão.**\n")
    print("## Regras\n")
    print("- Texto que começa com `/` **nunca** é encaminhado ao Hermes: o servidor devolve 422 `comando_no_texto`, e o front intercepta antes.")
    print("- Só rodam os comandos com `disponivel = true`. Os locais rodam no navegador; o único de servidor (`/status`) é **somente leitura**, "
          "por rota tipada `POST /api/agent/comandos/status`, com recibo `{executado_em, origem, somente_leitura, duracao_ms}`. "
          "A rota despacha por nome: comando de servidor sem ação devolve 501.")
    print("- Nenhum comando habilita toolset. As classes `requires_tool`, `external_mutation` e `telegram_only` ficam **bloqueadas** e aparecem na paleta com o motivo.")
    print("- Comando desconhecido vira nota local \"Comando desconhecido\"; nada sai do navegador.")
    print("- Alias do Telegram (`/new`, `/help`…) mostra o motivo e o equivalente da web.\n")
    print("## Contagem por classe\n")
    print("| Classe | Total |\n|---|---:|")
    for k in ("local_ui", "hermes_safe", "requires_tool", "external_mutation", "telegram_only"):
        print(f"| {NOME[k]} | {cont.get(k, 0)} |")
    print(f"| **Total** | **{len(cat)}** |\n")
    tabela([e for e in cat if e.origem == "volc"], "Comandos da web (disponíveis)")
    tabela([e for e in cat if e.origem == "hermes_registro"], "Registro do Hermes (82)")
    tabela([e for e in cat if e.origem == "hermes_skill"], "Comandos de skill do profile `default` (48)")


if __name__ == "__main__":
    main()
