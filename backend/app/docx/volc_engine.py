"""
VOLC DOCX — Engine (python-docx). Porta fiel do volc-components.js.

Expõe uma classe VolcDocx que compõe um documento no padrão visual VOLC:
capa, índice, H1/H2/H3, corpo justificado, bullets, insight box, note box,
data table com zebra + header navy, footnote, header/footer com paginação.

Todos os detalhes de cor/tamanho/espaçamento vêm de volc_theme.py.
"""
from __future__ import annotations

import io
from typing import Any, Dict, List, Optional, Sequence, Union

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Twips

from . import volc_theme as T

Cell = Union[str, Dict[str, Any]]


# --- low-level OOXML helpers ------------------------------------------------
def _rgb(hex_str: str) -> RGBColor:
    return RGBColor.from_string(hex_str)


def _style_run(run, *, size=None, color=None, bold=False, italic=False,
               all_caps=False, char_spacing=None) -> None:
    run.font.name = T.FONT_FAMILY
    # garante Calibri também no East Asian / complex script
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs"):
        rFonts.set(qn(attr), T.FONT_FAMILY)
    if size is not None:
        run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = _rgb(color)
    run.font.bold = bool(bold)
    run.font.italic = bool(italic)
    if all_caps:
        run.font.all_caps = True
    if char_spacing is not None:
        sp = OxmlElement("w:spacing")
        sp.set(qn("w:val"), str(char_spacing))
        # ordem OOXML no rPr: ... color, spacing, w, kern, position, sz ...
        sz = rPr.find(qn("w:sz"))
        if sz is not None:
            sz.addprevious(sp)
        else:
            rPr.append(sp)


def _para_spacing(paragraph, *, before=None, after=None, line=None) -> None:
    pf = paragraph.paragraph_format
    if before is not None:
        pf.space_before = Twips(before)
    if after is not None:
        pf.space_after = Twips(after)
    if line is not None:
        pf.line_spacing = line / 240.0  # múltiplo (240 = simples)


def _set_paragraph_border(paragraph, *, edge="bottom", size=12, color="B8860B", space=6) -> None:
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = pPr.find(qn("w:pBdr"))
    if pBdr is None:
        pBdr = OxmlElement("w:pBdr")
        pPr.insert(0, pBdr)  # pBdr deve vir cedo no pPr (antes de spacing/ind)
    el = OxmlElement(f"w:{edge}")
    el.set(qn("w:val"), "single")
    el.set(qn("w:sz"), str(size))
    el.set(qn("w:space"), str(space))
    el.set(qn("w:color"), color)
    pBdr.append(el)


def _set_outline_level(paragraph, level: int) -> None:
    pPr = paragraph._p.get_or_add_pPr()
    ol = OxmlElement("w:outlineLvl")
    ol.set(qn("w:val"), str(level))
    pPr.append(ol)


def _set_keep_next(paragraph) -> None:
    """Mantém o parágrafo na MESMA página que o próximo (não orfão de heading/linha)."""
    pPr = paragraph._p.get_or_add_pPr()
    if pPr.find(qn("w:keepNext")) is None:
        pPr.insert(0, OxmlElement("w:keepNext"))


def _row_cant_split(row) -> None:
    """Impede que UMA linha da tabela quebre no meio ao virar a página."""
    trPr = row._tr.get_or_add_trPr()
    if trPr.find(qn("w:cantSplit")) is None:
        trPr.append(OxmlElement("w:cantSplit"))


def _keep_table_together(table) -> None:
    """Mantém a tabela INTEIRA na mesma página: linhas não quebram no meio e ficam
    'grudadas' (keepNext) — se não couber, o Word joga a tabela toda pra página
    seguinte em vez de rachá-la entre duas páginas."""
    rows = table.rows
    n = len(rows)
    for i, row in enumerate(rows):
        _row_cant_split(row)
        if i < n - 1:  # todas menos a última: grudam na próxima linha
            for cell in row.cells:
                for para in cell.paragraphs:
                    _set_keep_next(para)


def _set_cell_bg(cell, hex_fill: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    tcPr.append(shd)


def _set_cell_borders(cell, edges: Dict[str, Optional[tuple]]) -> None:
    """edges: {'top': (size_eighths, color) | None, ...}. None => nil (sem borda)."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        spec = edges.get(edge, None)
        if spec is None:
            el.set(qn("w:val"), "nil")
        else:
            size, color = spec
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), str(size))
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), color)
        tcBorders.append(el)
    tcPr.append(tcBorders)


def _set_cell_margins(cell, m: Dict[str, int]) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement("w:tcMar")
    for name in ("top", "bottom", "left", "right"):
        el = OxmlElement(f"w:{name}")
        el.set(qn("w:w"), str(m[name]))
        el.set(qn("w:type"), "dxa")
        tcMar.append(el)
    tcPr.append(tcMar)


def _set_table_fixed(table) -> None:
    table.autofit = False
    table.allow_autofit = False
    tblPr = table._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblPr.append(layout)


def _add_page_number(paragraph) -> None:
    run = paragraph.add_run()
    _style_run(run, size=T.SIZE["headerFooter"], bold=True, color=T.COLORS["navy"])
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_end)


_ALIGN = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}


class VolcDocx:
    def __init__(self, *, title: str, description: str = "", header_text: str = "",
                 brand: str = "VOLC", show_header: bool = False) -> None:
        self.brand = brand
        self.doc = Document()
        self._setup_page()
        self._setup_base_styles()
        self._setup_metadata(title, description)
        if show_header:
            self._setup_header(header_text)
        self._setup_footer()

    # ---- setup -------------------------------------------------------------
    def _setup_page(self) -> None:
        sec = self.doc.sections[0]
        sec.page_width = Twips(T.PAGE["width"])
        sec.page_height = Twips(T.PAGE["height"])
        sec.top_margin = Twips(T.PAGE["margin"]["top"])
        sec.bottom_margin = Twips(T.PAGE["margin"]["bottom"])
        sec.left_margin = Twips(T.PAGE["margin"]["left"])
        sec.right_margin = Twips(T.PAGE["margin"]["right"])

    def _setup_base_styles(self) -> None:
        normal = self.doc.styles["Normal"]
        normal.font.name = T.FONT_FAMILY
        normal.font.size = Pt(T.SIZE["body"])
        normal.font.color.rgb = _rgb(T.COLORS["slate"])
        rpr = normal.element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.insert(0, rfonts)
        for attr in ("w:ascii", "w:hAnsi", "w:cs"):
            rfonts.set(qn(attr), T.FONT_FAMILY)

    def _setup_metadata(self, title: str, description: str) -> None:
        cp = self.doc.core_properties
        cp.author = self.brand
        cp.title = title
        cp.comments = description or ""

    def _setup_header(self, description: str) -> None:
        header = self.doc.sections[0].header
        header.is_linked_to_previous = False
        para = header.paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.LEFT
        para.paragraph_format.tab_stops.add_tab_stop(Twips(T.PAGE["rightEdge"]), WD_TAB_ALIGNMENT.RIGHT)
        _set_paragraph_border(para, edge="bottom", size=T.BORDER["headerBottom"], color=T.COLORS["gold"], space=4)
        r = para.add_run("VOLC")
        _style_run(r, size=T.SIZE["headerFooter"], bold=True, color=T.COLORS["gold"], char_spacing=T.CHAR_SPACING["logo"])
        if description:
            r2 = para.add_run(f"   {description}")
            _style_run(r2, size=T.SIZE["headerFooter"], color=T.COLORS["slateLight"])
        r3 = para.add_run("\tCONFIDENCIAL")
        _style_run(r3, size=T.SIZE["headerFooter"], bold=True, color=T.COLORS["gold"], char_spacing=T.CHAR_SPACING["confidential"])

    def _setup_footer(self) -> None:
        footer = self.doc.sections[0].footer
        footer.is_linked_to_previous = False
        para = footer.paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.LEFT
        para.paragraph_format.tab_stops.add_tab_stop(Twips(T.PAGE["rightEdge"]), WD_TAB_ALIGNMENT.RIGHT)
        _set_paragraph_border(para, edge="top", size=T.BORDER["footerTop"], color=T.COLORS["border"], space=4)
        r = para.add_run(self.brand)
        _style_run(r, size=T.SIZE["headerFooter"], italic=True, color=T.COLORS["slateLight"])
        r2 = para.add_run("\tPág. ")
        _style_run(r2, size=T.SIZE["headerFooter"], color=T.COLORS["slateLight"])
        _add_page_number(para)

    # ---- primitives --------------------------------------------------------
    def _new_para(self, *, align="left", before=None, after=None, line=None):
        p = self.doc.add_paragraph()
        p.alignment = _ALIGN[align]
        _para_spacing(p, before=before, after=after, line=line)
        return p

    def para(self, text: str, *, align="justify", bold=False, italic=False,
             color=None, size=None) -> None:
        sp = T.PARA["body"]
        p = self._new_para(align=align, before=sp["before"], after=sp["after"], line=sp["line"])
        r = p.add_run(text)
        _style_run(r, size=size or T.SIZE["body"], color=color or T.COLORS["slate"], bold=bold, italic=italic)

    def para_runs(self, runs: Sequence[Dict[str, Any]], *, align="justify") -> None:
        sp = T.PARA["body"]
        p = self._new_para(align=align, before=sp["before"], after=sp["after"], line=sp["line"])
        for spec in runs:
            r = p.add_run(spec.get("text", ""))
            _style_run(
                r,
                size=spec.get("size", T.SIZE["body"]),
                color=spec.get("color", T.COLORS["slate"]),
                bold=spec.get("bold", False),
                italic=spec.get("italic", False),
            )

    def section_num(self, num: str) -> None:
        p = self._new_para(after=80)
        r = p.add_run(num)
        _style_run(r, size=T.SIZE["sectionNum"], bold=True, color=T.COLORS["gold"],
                   char_spacing=T.CHAR_SPACING["sectionNum"])

    def h1(self, text: str) -> None:
        sp = T.PARA["h1"]
        p = self._new_para(before=sp["before"], after=sp["after"])
        _set_paragraph_border(p, edge="bottom", size=T.BORDER["h1Bottom"], color=T.COLORS["gold"], space=6)
        _set_outline_level(p, 0)
        _set_keep_next(p)
        r = p.add_run(text)
        _style_run(r, size=T.SIZE["h1"], bold=True, color=T.COLORS["navy"])

    def h2(self, text: str) -> None:
        sp = T.PARA["h2"]
        p = self._new_para(before=sp["before"], after=sp["after"])
        _set_outline_level(p, 1)
        _set_keep_next(p)
        r = p.add_run(text)
        _style_run(r, size=T.SIZE["h2"], bold=True, color=T.COLORS["navySoft"])

    def h3(self, text: str) -> None:
        sp = T.PARA["h3"]
        p = self._new_para(before=sp["before"], after=sp["after"])
        _set_outline_level(p, 2)
        _set_keep_next(p)
        r = p.add_run(text)
        _style_run(r, size=T.SIZE["h3"], bold=True, color=T.COLORS["gold"])

    def bullet(self, text: str, *, color=None) -> None:
        self.bullet_runs([{"text": text, "color": color or T.COLORS["slate"]}])

    def bullet_runs(self, runs: Sequence[Dict[str, Any]]) -> None:
        sp = T.PARA["bullet"]
        p = self._new_para(align="justify", before=sp["before"], after=sp["after"], line=sp["line"])
        pf = p.paragraph_format
        pf.left_indent = Twips(T.BULLET_INDENT["left"])
        pf.first_line_indent = Twips(-T.BULLET_INDENT["hanging"])
        rb = p.add_run("•\t")
        _style_run(rb, size=T.SIZE["body"], color=T.COLORS["gold"])
        for spec in runs:
            r = p.add_run(spec.get("text", ""))
            _style_run(
                r,
                size=spec.get("size", T.SIZE["body"]),
                color=spec.get("color", T.COLORS["slate"]),
                bold=spec.get("bold", False),
                italic=spec.get("italic", False),
            )

    def spacer(self, size: Union[str, int] = "sm") -> None:
        val = T.SPACER.get(size, T.SPACER["sm"]) if isinstance(size, str) else size
        p = self._new_para(before=val, after=val)
        r = p.add_run("")
        _style_run(r, size=1)

    def page_break(self) -> None:
        self.doc.add_page_break()

    def footnote(self, text: str) -> None:
        p = self._new_para(before=60, after=40)
        r = p.add_run(text)
        _style_run(r, size=T.SIZE["footnote"], italic=True, color=T.COLORS["slateLight"])

    def centered_statement(self, text: str) -> None:
        p = self._new_para(align="center", before=240, after=240)
        r = p.add_run(text)
        _style_run(r, size=16, bold=True, italic=True, color=T.COLORS["gold"])

    # ---- boxes (tabela de 1 célula com barra lateral) ----------------------
    def _single_cell_box(self, fill: str, left_bar_color: str, left_bar_size: int, margins: Dict[str, int]):
        table = self.doc.add_table(rows=1, cols=1)
        table.alignment = WD_TABLE_ALIGNMENT.LEFT
        _set_table_fixed(table)
        _row_cant_split(table.rows[0])  # a caixa (insight/note) não racha entre páginas
        cell = table.cell(0, 0)
        cell.width = Twips(T.PAGE["usableWidth"])
        _set_cell_borders(cell, {
            "top": None, "bottom": None, "right": None,
            "left": (left_bar_size, left_bar_color),
        })
        _set_cell_bg(cell, fill)
        _set_cell_margins(cell, margins)
        # remove o parágrafo vazio inicial da célula
        cell.paragraphs[0]._p.getparent().remove(cell.paragraphs[0]._p)
        return cell

    def insight_box(self, label: str, text: str) -> None:
        cell = self._single_cell_box(
            fill=T.COLORS["bgAccent"], left_bar_color=T.COLORS["gold"],
            left_bar_size=T.BORDER["insightLeft"], margins=T.CELL["insightBox"],
        )
        pl = cell.add_paragraph()
        _para_spacing(pl, after=80)
        rl = pl.add_run(label)
        _style_run(rl, size=T.SIZE["insightLabel"], bold=True, color=T.COLORS["gold"], all_caps=True)
        pt = cell.add_paragraph()
        pt.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _para_spacing(pt, line=320)
        rt = pt.add_run(text)
        _style_run(rt, size=T.SIZE["insightText"], italic=True, color=T.COLORS["navy"])
        self.spacer("xs")

    def note_box(self, text: str) -> None:
        cell = self._single_cell_box(
            fill=T.COLORS["bg"], left_bar_color=T.COLORS["slateLight"],
            left_bar_size=T.BORDER["noteLeft"], margins=T.CELL["noteBox"],
        )
        pt = cell.add_paragraph()
        pt.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        _para_spacing(pt, line=300)
        rt = pt.add_run(text)
        _style_run(rt, size=T.SIZE["note"], italic=True, color=T.COLORS["slateLight"])
        self.spacer("xs")

    # ---- data table --------------------------------------------------------
    def data_table(self, headers: List[str], rows: List[List[Cell]], widths: List[int]) -> None:
        table = self.doc.add_table(rows=len(rows) + 1, cols=len(headers))
        table.alignment = WD_TABLE_ALIGNMENT.LEFT
        _set_table_fixed(table)

        # header row
        for i, htext in enumerate(headers):
            cell = table.cell(0, i)
            cell.width = Twips(widths[i])
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            _set_cell_borders(cell, {e: (T.BORDER["tableHeaderCell"], T.COLORS["navy"]) for e in ("top", "bottom", "left", "right")})
            _set_cell_bg(cell, T.COLORS["navy"])
            _set_cell_margins(cell, T.CELL["tableHeader"])
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            _para_spacing(p, before=0, after=0)
            r = p.add_run(htext)
            _style_run(r, size=T.SIZE["tableHeader"], bold=True, color=T.COLORS["white"])

        # body rows
        for ridx, row in enumerate(rows):
            zebra = (ridx % 2 == 1)
            for cidx, content in enumerate(row):
                cell = table.cell(ridx + 1, cidx)
                cell.width = Twips(widths[cidx])
                cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
                is_obj = isinstance(content, dict)
                text = str(content.get("text", "")) if is_obj else str(content)
                bold = content.get("bold", False) if is_obj else False
                color = content.get("color", T.COLORS["slate"]) if is_obj else T.COLORS["slate"]
                fill = content.get("fill") if is_obj else None
                if not fill:
                    fill = T.COLORS["bg"] if zebra else T.COLORS["white"]
                align = content.get("align") if is_obj else None
                if not align:
                    align = "left" if cidx == 0 else "right"
                _set_cell_borders(cell, {e: (T.BORDER["tableBodyCell"], T.COLORS["border"]) for e in ("top", "bottom", "left", "right")})
                _set_cell_bg(cell, fill)
                _set_cell_margins(cell, T.CELL["tableBody"])
                p = cell.paragraphs[0]
                p.alignment = _ALIGN[align]
                _para_spacing(p, before=0, after=0)
                r = p.add_run(text)
                _style_run(r, size=T.SIZE["tableBody"], bold=bold, color=color)
        _keep_table_together(table)  # tabela inteira não racha entre páginas
        self.spacer("xs")

    # ---- cover / toc -------------------------------------------------------
    def cover(self, *, title1: str, title2: str, subtitle1: str, subtitle2: str,
              classification: str = "", descriptions: Optional[List[str]] = None) -> None:
        # logo (marca) com borda dourada inferior
        p = self._new_para(before=2400, after=240)
        _set_paragraph_border(p, edge="bottom", size=T.BORDER["coverLogoBottom"], color=T.COLORS["gold"], space=6)
        r = p.add_run(self.brand)
        _style_run(r, size=T.SIZE["coverLogo"], bold=True, color=T.COLORS["gold"], char_spacing=T.CHAR_SPACING["logo"])
        # classification (opcional)
        if classification:
            p = self._new_para(before=2000, after=240)
            r = p.add_run(classification)
            _style_run(r, size=T.SIZE["sectionNum"], bold=True, color=T.COLORS["gold"], char_spacing=T.CHAR_SPACING["confidential"])
        else:
            self.spacer("xxl")
        # títulos
        p = self._new_para(before=120, after=180)
        r = p.add_run(title1)
        _style_run(r, size=T.SIZE["coverTitle"], bold=True, color=T.COLORS["navy"])
        p = self._new_para(after=480)
        r = p.add_run(title2)
        _style_run(r, size=T.SIZE["coverTitle"], bold=True, color=T.COLORS["navy"])
        # subtítulos
        p = self._new_para(after=120)
        r = p.add_run(subtitle1)
        _style_run(r, size=16, color=T.COLORS["navySoft"])
        p = self._new_para(after=960)
        r = p.add_run(subtitle2)
        _style_run(r, size=16, color=T.COLORS["navySoft"])
        # descrições (opcional)
        for i, desc in enumerate(descriptions or []):
            p = self._new_para(before=1200 if i == 0 else 0, after=80)
            r = p.add_run(desc)
            _style_run(r, size=T.SIZE["body"], italic=True, color=T.COLORS["slate"])
        self.page_break()

    def toc(self, items: List[Sequence[str]]) -> None:
        self.h1("Índice")
        self.spacer("xs")
        for num, title, pg in items:
            p = self._new_para(before=120, after=120)
            p.paragraph_format.tab_stops.add_tab_stop(Twips(T.PAGE["tocRight"]), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
            r1 = p.add_run(f"{num}   ")
            _style_run(r1, size=T.SIZE["body"], bold=True, color=T.COLORS["gold"])
            r2 = p.add_run(title)
            _style_run(r2, size=T.SIZE["body"], color=T.COLORS["navy"])
            r3 = p.add_run(f"\t{pg}")
            _style_run(r3, size=T.SIZE["body"], color=T.COLORS["slateLight"])
        self.page_break()

    # ---- output ------------------------------------------------------------
    def to_bytes(self) -> bytes:
        buf = io.BytesIO()
        self.doc.save(buf)
        return buf.getvalue()

    def save(self, path: str) -> None:
        self.doc.save(path)
