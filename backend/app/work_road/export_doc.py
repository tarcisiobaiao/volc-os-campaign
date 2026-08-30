"""Exportação textual do Work Road: HTML imprimível e PDF selecionável."""
from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any


SCOPES = {"full", "current", "next-wave", "open"}


def recortar(documento: dict[str, Any], escopo: str, recorte: dict[str, str] | None = None) -> dict[str, Any]:
    iniciativas = list(documento.get("initiatives") or [])
    if escopo == "open":
        iniciativas = [
            {**item, "tasks": [tarefa for tarefa in item.get("tasks") or [] if tarefa.get("status") not in {"done", "reserved"}]}
            for item in iniciativas
        ]
        iniciativas = [item for item in iniciativas if item["tasks"]]
    elif escopo == "next-wave" and iniciativas:
        primeira = str(iniciativas[0].get("wave") or "")
        iniciativas = [item for item in iniciativas if item.get("wave") == primeira]
    elif escopo == "current" and recorte:
        iniciativa = recorte.get("iniciativa") or ""
        onda = recorte.get("onda") or ""
        status = recorte.get("status") or ""
        busca = (recorte.get("busca") or "").strip().lower()
        filtradas = []
        for item in iniciativas:
            if iniciativa and item.get("id") != iniciativa:
                continue
            if onda and item.get("wave") != onda:
                continue
            tarefas = []
            for tarefa in item.get("tasks") or []:
                if status and status != "all" and tarefa.get("status") != status:
                    continue
                if busca:
                    hay = " ".join([
                        str(tarefa.get("id") or ""),
                        str(tarefa.get("title") or ""),
                        str(tarefa.get("explanation") or ""),
                    ]).lower()
                    if busca not in hay:
                        continue
                tarefas.append(tarefa)
            if tarefas:
                filtradas.append({**item, "tasks": tarefas})
        iniciativas = filtradas
    clone = dict(documento)
    clone["initiatives"] = iniciativas
    return clone


def _linhas_tarefa(tarefa: dict[str, Any], iniciativa: dict[str, Any]) -> list[str]:
    linhas = [
        f"{tarefa.get('id')} — {tarefa.get('title')}",
        f"Iniciativa {iniciativa.get('id')} · {iniciativa.get('title')} · {iniciativa.get('wave')} · {tarefa.get('status')}",
    ]
    if tarefa.get("explanation"):
        linhas.append(str(tarefa["explanation"]))
    else:
        linhas.append("Explicação da tarefa ausente na fonte.")
    if tarefa.get("proof"):
        linhas.append(f"Evidência: {tarefa['proof']}")
    else:
        linhas.append("Tarefa sem evidência na fonte.")
    deps = tarefa.get("dependencies") or tarefa.get("depends_on")
    if deps:
        linhas.append("Dependências declaradas: " + ", ".join(str(item) for item in deps))
    checklist = tarefa.get("checklist")
    if isinstance(checklist, list) and checklist:
        for item in checklist:
            marca = "[x]" if item.get("done") else "[ ]"
            linhas.append(f"  {marca} {item.get('description') or item.get('id')}")
    else:
        linhas.append("  Checklist ainda não documentado.")
    linhas.append("")
    return linhas


def texto(documento: dict[str, Any], *, gerado_em: str, aviso: str | None = None) -> str:
    source = documento.get("source") or {}
    linhas = [
        "VOLC O.S. — Workbook do Roadmap Vivo",
        f"Gerado em {gerado_em}",
        f"Fonte {source.get('path') or 'ausente'} · hash {source.get('sha256') or 'ausente'}",
        f"Atualizada em {documento.get('updated_at') or 'ausente'}",
        "",
    ]
    if aviso:
        linhas.extend([aviso, ""])
    linhas.extend(["Sumário", ""])
    for iniciativa in documento.get("initiatives") or []:
        linhas.append(f"{iniciativa.get('id')} · {iniciativa.get('title')} ({iniciativa.get('wave')})")
    linhas.extend(["", "Sequência prioritária", ""])
    for iniciativa in documento.get("initiatives") or []:
        linhas.append(f"Onda {iniciativa.get('wave')} — {iniciativa.get('why')}")
        for tarefa in iniciativa.get("tasks") or []:
            linhas.extend(_linhas_tarefa(tarefa, iniciativa))
        linhas.extend(["Anotações desta iniciativa", "________________________________", ""])
    linhas.extend([
        "Legenda: done = concluída e provada; partial = parcial; risk = existe com risco; todo = a fazer; reserved = fora do percentual.",
        "Ausência de campo não foi preenchida. Ordem editorial não prova dependência.",
    ])
    return "\n".join(linhas)


def html_documento(documento: dict[str, Any], *, gerado_em: str, aviso: str | None = None) -> str:
    source = documento.get("source") or {}
    aviso_html = f"<p class='aviso'>{html.escape(aviso)}</p>" if aviso else ""
    blocos: list[str] = []
    for iniciativa in documento.get("initiatives") or []:
        tarefas = []
        for tarefa in iniciativa.get("tasks") or []:
            deps = tarefa.get("dependencies") or tarefa.get("depends_on") or []
            checklist = tarefa.get("checklist") or []
            itens = "".join(
                f"<li>{'☑' if item.get('done') else '☐'} {html.escape(str(item.get('description') or item.get('id')))}</li>"
                for item in checklist
            ) or "<li>Checklist ainda não documentado.</li>"
            tarefas.append(
                "<article class='card'>"
                f"<h3>{html.escape(str(tarefa.get('id')))} — {html.escape(str(tarefa.get('title')))}</h3>"
                f"<p>{html.escape(str(iniciativa.get('id')))} · {html.escape(str(tarefa.get('status')))}</p>"
                f"<p>{html.escape(str(tarefa.get('explanation') or 'Explicação da tarefa ausente na fonte.'))}</p>"
                f"<p>Evidência: {html.escape(str(tarefa.get('proof') or 'ausente'))}</p>"
                f"<p>Dependências declaradas: {html.escape(', '.join(str(item) for item in deps) or 'nenhuma')}</p>"
                f"<ul>{itens}</ul>"
                "</article>"
            )
        blocos.append(
            f"<section><h2>{html.escape(str(iniciativa.get('id')))} · {html.escape(str(iniciativa.get('title')))}</h2>"
            f"<p>{html.escape(str(iniciativa.get('wave')))} — {html.escape(str(iniciativa.get('why')))}</p>"
            + "".join(tarefas)
            + "<div class='notes'><h3>Anotações</h3><p>________________________________</p></div></section>"
        )
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8"/>
  <title>Workbook VOLC O.S.</title>
  <style>
    @page {{ size: A4; margin: 18mm 16mm 22mm 16mm; @bottom-center {{ content: "VOLC O.S. " counter(page); }} }}
    body {{ font-family: Inter, Helvetica, Arial, sans-serif; color: #1a1c1e; background: #f3f5f7; font-size: 12pt; line-height: 1.45; }}
    h1,h2,h3 {{ font-family: "Space Grotesk", Helvetica, sans-serif; page-break-after: avoid; }}
    header {{ border-bottom: 1px solid #d8dee6; padding-bottom: 12px; margin-bottom: 24px; }}
    .aviso {{ border: 1px solid #d9850b; padding: 8px 12px; }}
    .card {{ border-top: 1px solid #d8dee6; padding: 12px 0; page-break-inside: avoid; }}
    footer {{ position: running(footer); font-size: 9pt; color: #68717d; }}
    @media print {{
      body {{ background: #fff; }}
      a {{ color: inherit; text-decoration: none; }}
    }}
  </style>
</head>
<body>
  <header>
    <p>VOLC O.S.</p>
    <h1>Workbook do Roadmap Vivo</h1>
    <p>Gerado em {html.escape(gerado_em)}</p>
    <p>Fonte {html.escape(str(source.get("path") or "ausente"))} · hash {html.escape(str(source.get("sha256") or "ausente"))}</p>
    <p>Atualizada em {html.escape(str(documento.get("updated_at") or "ausente"))}</p>
    {aviso_html}
  </header>
  <nav><h2>Sumário</h2><ol>
    {"".join(f"<li>{html.escape(str(item.get('id')))} · {html.escape(str(item.get('title')))}</li>" for item in documento.get("initiatives") or [])}
  </ol></nav>
  {"".join(blocos)}
  <section>
    <h2>Legenda</h2>
    <p>done = concluída e provada; partial = parcial; risk = existe com risco; todo = a fazer; reserved = fora do percentual.</p>
    <p>Ausência de campo não foi preenchida. Ordem editorial não prova dependência.</p>
  </section>
</body>
</html>
"""


def _pdf_escape(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf_bytes(texto_corrente: str) -> bytes:
    """PDF de texto selecionável, A4, sem rasterizar a interface."""
    largura, altura = 595, 842
    margem = 48
    corpo = 10
    leading = 13
    max_chars = 92
    paginas: list[list[str]] = []
    atual: list[str] = []
    for bruta in texto_corrente.splitlines() or [""]:
        linha = bruta if bruta else " "
        while len(linha) > max_chars:
            atual.append(linha[:max_chars])
            linha = linha[max_chars:]
            if len(atual) >= 54:
                paginas.append(atual)
                atual = []
        atual.append(linha)
        if len(atual) >= 54:
            paginas.append(atual)
            atual = []
    if atual:
        paginas.append(atual)

    objetos: list[bytes] = []
    objetos.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{3 + indice * 2} 0 R" for indice, _ in enumerate(paginas))
    objetos.append(f"<< /Type /Pages /Count {len(paginas)} /Kids [{kids}] >>".encode("latin-1"))

    for indice, linhas in enumerate(paginas):
        conteudo = ["BT", "/F1 {0} Tf".format(corpo), f"{margem} {altura - margem} Td"]
        for linha in linhas:
            conteudo.append(f"({_pdf_escape(linha)}) Tj")
            conteudo.append(f"0 -{leading} Td")
        conteudo.append("ET")
        conteudo.extend([
            "BT",
            "/F1 8 Tf",
            f"{margem} 28 Td",
            f"({_pdf_escape('VOLC O.S.  pagina ' + str(indice + 1) + ' de ' + str(len(paginas)))}) Tj",
            "ET",
        ])
        stream = "\n".join(conteudo).encode("latin-1", "replace")
        page_id = 3 + indice * 2
        content_id = page_id + 1
        objetos.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {largura} {altura}] "
                f"/Resources << /Font << /F1 {3 + len(paginas) * 2} 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            ).encode("latin-1")
        )
        objetos.append(f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream")
    objetos.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for indice, obj in enumerate(objetos, start=1):
        offsets.append(len(out))
        out.extend(f"{indice} 0 obj\n".encode("latin-1"))
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(objetos) + 1}\n".encode("latin-1"))
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    out.extend(
        (
            f"trailer << /Size {len(objetos) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode("latin-1")
    )
    return bytes(out)


def gerado_em() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
