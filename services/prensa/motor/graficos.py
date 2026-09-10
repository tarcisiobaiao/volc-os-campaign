#!/usr/bin/env python3
"""PRENSA — MOTOR DE GRÁFICOS. SVG gerado em Python, determinístico, zero JS.

Por que não D3/Chart.js: biblioteca no browser traz não-determinismo (layout de
rótulo, animação, tema) e tira o dado do contrato. Aqui o path sai de numpy, o
JSON continua sendo a fonte da verdade, e o gate mede o resultado como mede
qualquer outra tinta.

DOUTRINA DESTE MÓDULO — o que separa gráfico editorial de gráfico de dashboard:
  · fio de cabelo, nunca borda grossa; a linha do dado é a mais forte da peça
  · zero grid completo — só a régua que o argumento exige
  · anotação COM chamada, não legenda solta num canto
  · numeral tabular sempre; o número é para comparar, não para ler
  · o acento é bisturi: pinta O ponto que prova a tese, e mais nada
  · nada de cantos arredondados, sombra colorida ou gradiente decorativo
"""
from __future__ import annotations
import math

def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _svg(w, h, corpo, extra=""):
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" style="display:block" '
            f'xmlns="http://www.w3.org/2000/svg" {extra}>{corpo}</svg>')

def _txt(x, y, t, cor, tam, fam, peso=400, anchor="start", track=0, up=False, italic=False):
    return (f'<text x="{x:.1f}" y="{y:.1f}" fill="{cor}" font-size="{tam}" '
            f'font-family="{fam}" font-weight="{peso}" text-anchor="{anchor}" '
            f'letter-spacing="{track}" font-style="{"italic" if italic else "normal"}" '
            f'style="font-variant-numeric:tabular-nums">'
            f'{_esc(t).upper() if up else _esc(t)}</text>')

# --------------------------------------------------------------------------
def curva_normal(w=884, h=360, *, media=0.5, sigma=0.16, faixa_lab=(0.10, 0.72),
                 faixa_otima=(0.74, 0.95), voce=0.22, cor_curva="#8A8F98",
                 cor_lab="#5A6678", cor_otima="#C9A84C", cor_texto="#FFFFFF",
                 cor_marca="#A4A8AF",
                 cor_fio="rgba(90,102,120,0.55)", fam="Archivo", fam_rot="IBM Plex Mono",
                 rot_lab="O QUE O LABORATÓRIO LIBERA", rot_otima="FAIXA ÓTIMA",
                 rot_voce="VOCÊ"):
    """A CURVA DE DISTRIBUIÇÃO — o gráfico que carrega a tese inteira:
    'faixa de referência é estatística de população doente'. Mostra a população,
    sombreia o que o laudo aceita, marca onde a biologia agradece, e crava onde
    o paciente está. Sem ela a frase é opinião; com ela é evidência."""
    pad_b, top = 108, 26
    hg = h - pad_b - top
    def X(u): return u * w
    def Y(u): return top + hg - u * hg
    def pdf(u): return math.exp(-((u - media) ** 2) / (2 * sigma ** 2))
    N = 240
    pts = [(X(i / N), Y(pdf(i / N))) for i in range(N + 1)]
    linha = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    def area(a, b, cor, op):
        seg = [(X(u), Y(pdf(u))) for u in [a + (b - a) * i / 80 for i in range(81)]]
        d = (f"M{X(a):.1f},{Y(0):.1f} L" + " L".join(f"{x:.1f},{y:.1f}" for x, y in seg)
             + f" L{X(b):.1f},{Y(0):.1f} Z")
        return f'<path d="{d}" fill="{cor}" opacity="{op}"/>'
    c = [f'<line x1="0" y1="{Y(0):.1f}" x2="{w}" y2="{Y(0):.1f}" stroke="{cor_fio}" stroke-width="1"/>']
    c.append(area(*faixa_lab, cor_lab, 0.34))
    c.append(area(*faixa_otima, cor_otima, 0.26))
    c.append(f'<path d="{linha}" fill="none" stroke="{cor_curva}" stroke-width="2"/>')
    # marcador do paciente — a linha mais forte da peça
    xv, yv = X(voce), Y(pdf(voce))
    c.append(f'<line x1="{xv:.1f}" y1="{Y(0):.1f}" x2="{xv:.1f}" y2="{yv-16:.1f}" '
             f'stroke="{cor_texto}" stroke-width="3"/>')
    c.append(f'<circle cx="{xv:.1f}" cy="{yv:.1f}" r="6" fill="{cor_texto}"/>')
    c.append(_txt(xv, yv - 26, rot_voce, cor_texto, 22, fam_rot, 600, "middle", 2.4, True))
    # COTA DIMENSIONAL — a faixa pintada é atmosfera: nenhum preenchimento
    # tênue o bastante para não competir com o ouro alcança 3:1 sobre o navy.
    # Quem carrega o argumento é a cota — traço horizontal com pernas nas
    # extremidades, como cota de desenho técnico. Ela mede a EXTENSÃO da faixa,
    # que é justamente a tese ("o laudo aceita esse tanto"), e o faz em tinta
    # que passa no piso. Vocabulário de prancheta, não de dashboard.
    for i, ((a, b), rot, cor) in enumerate((
            (faixa_lab, rot_lab, cor_marca), (faixa_otima, rot_otima, cor_otima))):
        yb = Y(0) + 18 + i * 46
        c.append(f'<path d="M{X(a):.1f},{yb-7:.1f} L{X(a):.1f},{yb:.1f} '
                 f'L{X(b):.1f},{yb:.1f} L{X(b):.1f},{yb-7:.1f}" fill="none" '
                 f'stroke="{cor}" stroke-width="2"/>')
        c.append(_txt(X((a + b) / 2), yb + 24, rot, cor, 20, fam_rot, 500, "middle", 2.2, True))
    return _svg(w, h, "".join(c))

# --------------------------------------------------------------------------
def mostrador(w=884, h=330, *, frac=0.22, faixa_otima=(0.62, 0.92), rotulo="FERRITINA",
              valor="18", unidade="ng/mL", cor_trilho="#132B4F", cor_arco="#C9A84C",
              cor_faixa="#C9A84C", cor_texto="#FFFFFF", cor_muted="#8A8F98",
              fam="Archivo", fam_rot="IBM Plex Mono"):
    """MOSTRADOR RADIAL — arco de 240°, com a faixa ótima marcada no próprio arco.
    O ponteiro não 'enfeita': ele mostra a distância entre onde está e onde devia."""
    esp = 20
    r = (h - esp - 2) / 1.5          # 1.5r + esp = h - 2  →  tinta em [1, h-1]
    cx, cy = w / 2, r + esp / 2 + 1
    a0, a1 = math.radians(150), math.radians(390)
    def P(t):
        a = a0 + (a1 - a0) * t
        return cx + r * math.cos(a), cy + r * math.sin(a)
    def arco(t0, t1, cor, larg, op=1.0):
        x0, y0 = P(t0); x1, y1 = P(t1)
        grande = 1 if (t1 - t0) > 0.5 else 0
        return (f'<path d="M{x0:.1f},{y0:.1f} A{r},{r} 0 {grande} 1 {x1:.1f},{y1:.1f}" '
                f'fill="none" stroke="{cor}" stroke-width="{larg}" opacity="{op}"/>')
    c = [arco(0, 1, cor_trilho, esp)]
    c.append(arco(faixa_otima[0], faixa_otima[1], cor_faixa, esp, 0.34))
    c.append(arco(0, frac, cor_arco, esp, 0.85))
    xp, yp = P(frac)
    c.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{xp:.1f}" y2="{yp:.1f}" '
             f'stroke="{cor_texto}" stroke-width="3"/>')
    c.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="7" fill="{cor_texto}"/>')
    c.append(_txt(cx, cy - 54, valor, cor_texto, 92, fam, 900, "middle"))
    c.append(_txt(cx, cy - 22, unidade, cor_muted, 24, fam_rot, 400, "middle", 2))
    c.append(_txt(cx, cy + 34, rotulo, cor_arco, 22, fam_rot, 600, "middle", 3, True))
    return _svg(w, h, "".join(c))

# --------------------------------------------------------------------------
def trajetoria(w=884, h=320, *, serie=(0.18, 0.22, 0.20, 0.34, 0.52, 0.68, 0.79),
               rotulos=("M0", "M1", "M2", "M3", "M4", "M5", "M6"), alvo=0.74,
               cor_linha="#C9A84C", cor_area="#C9A84C", cor_fio="rgba(90,102,120,0.55)",
               cor_texto="#FFFFFF", cor_muted="#8A8F98", fam_rot="IBM Plex Mono",
               rot_alvo="FAIXA ÓTIMA"):
    """TRAJETÓRIA — o protocolo ao longo do tempo. Área sob a curva porque o
    argumento é acúmulo, não instante. A linha do alvo é tracejada: é meta, não dado."""
    pad_b = 54
    n = len(serie)
    # TETO DE TINTA RESOLVIDO (Lei 18) — o extremo da tinta tem de pertencer a UMA
    # âncora em toda a faixa de h. Aqui disputavam o topo o rótulo do alvo (corpo
    # fixo, pendurado em `alvo`) e o círculo do ponto final (raio fixo, pendurado
    # em max(serie)): duas retas de inclinações diferentes trocando de posto em
    # h≈410, e span(h) virava dobradiça. Agora cada elemento capaz de alcançar um
    # extremo declara (valor de dado, reserva em px), e S é a maior escala que
    # mantém todos dentro da reserva — o vencedor encosta, ninguém ultrapassa.
    R_ULT, R_PT, ESP, FOLGA_TETO = 6, 3.5, 3, 2
    teto = ((max(serie), R_ULT), (max(serie), ESP / 2), (alvo, 0.5))
    S = min((h - pad_b - FOLGA_TETO - d) / v for v, d in teto if v > 0)
    # RESERVA LATERAL RESOLVIDA — mesma lei, eixo x. O ponto extremo carrega sua
    # reserva real; o rótulo extremo ancora no lado que o contém, e por isso tem
    # reserva ZERO, sem precisar medir largura de texto.
    def X(i): return (w - 2 * R_ULT) * i / (n - 1) + R_ULT
    def Y(v): return (h - pad_b) - S * v
    pts = [(X(i), Y(v)) for i, v in enumerate(serie)]
    linha = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    d_area = linha + f" L{X(n-1):.1f},{Y(0):.1f} L{X(0):.1f},{Y(0):.1f} Z"
    c = [f'<line x1="0" y1="{Y(0):.1f}" x2="{w}" y2="{Y(0):.1f}" stroke="{cor_fio}" stroke-width="1"/>',
         f'<path d="{d_area}" fill="{cor_area}" opacity="0.16"/>',
         f'<line x1="0" y1="{Y(alvo):.1f}" x2="{w}" y2="{Y(alvo):.1f}" stroke="{cor_linha}" '
         f'stroke-width="1" stroke-dasharray="6 6" opacity="0.75"/>',
         # o rótulo pende ABAIXO da régua que nomeia: acima, disputava o topo com
         # o ponto final, e era essa disputa que dobrava a reta.
         _txt(0, Y(alvo) + 26, rot_alvo, cor_linha, 19, fam_rot, 500, "start", 2.2, True),
         f'<path d="{linha}" fill="none" stroke="{cor_linha}" stroke-width="{ESP}"/>']
    for i, (x, y) in enumerate(pts):
        ult = i == n - 1
        c.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{R_ULT if ult else R_PT}" '
                 f'fill="{cor_texto if ult else cor_linha}"/>')
        anc = "start" if i == 0 else ("end" if ult else "middle")
        xr = 0 if i == 0 else (w if ult else x)
        c.append(_txt(xr, Y(0) + 34, rotulos[i], cor_muted, 19, fam_rot, 400, anc, 1.6, True))
    return _svg(w, h, "".join(c))

# --------------------------------------------------------------------------
def small_multiples(w=884, h=300, *, paineis=(), cor_linha="#C9A84C", cor_ruim="#8A8F98",
                    cor_fio="rgba(90,102,120,0.40)", cor_texto="#FFFFFF",
                    cor_muted="#8A8F98", fam="Archivo", fam_rot="IBM Plex Mono"):
    """SMALL MULTIPLES — cinco sparklines na mesma escala. O olho compara forma,
    não número; é a leitura que uma tabela de cinco linhas nunca entrega."""
    n = len(paineis) or 1
    gap = 26
    pw = (w - gap * (n - 1)) / n
    c = []
    for i, p in enumerate(paineis):
        ox = i * (pw + gap)
        s = p["serie"]; bom = p.get("bom", True)
        cor = cor_linha if bom else cor_ruim
        gh = h - 108
        R_PT = 4.5
        def X(j, ox=ox): return ox + (pw - R_PT) * j / (len(s) - 1)
        def Y(v): return 44 + gh - v * gh
        d = "M" + " L".join(f"{X(j):.1f},{Y(v):.1f}" for j, v in enumerate(s))
        if i:
            c.append(f'<line x1="{ox-gap/2:.1f}" y1="30" x2="{ox-gap/2:.1f}" y2="{h-40}" '
                     f'stroke="{cor_fio}" stroke-width="1"/>')
        c.append(_txt(ox, 22, p["rotulo"], cor_muted, 18, fam_rot, 500, "start", 2, True))
        c.append(f'<path d="{d}" fill="none" stroke="{cor}" stroke-width="2.5"/>')
        c.append(f'<circle cx="{X(len(s)-1):.1f}" cy="{Y(s[-1]):.1f}" r="{R_PT}" fill="{cor}"/>')
        c.append(_txt(ox, h - 8, p["valor"], cor_texto if bom else cor_muted, 30, fam, 900))
    return _svg(w, h, "".join(c))

# --------------------------------------------------------------------------
def radar(w=884, h=430, *, eixos=(), atual=(), otimo=(), cor_atual="#8A8F98",
          cor_otimo="#C9A84C", cor_fio="rgba(90,102,120,0.45)", cor_texto="#FFFFFF",
          fam_rot="IBM Plex Mono"):
    """RADAR — perfil multidimensional. Duas malhas: onde está e onde devia.
    A área entre as duas É o protocolo."""
    cx, cy, r = w / 2, h / 2 + 6, min(w, h) / 2 - 74
    n = len(eixos)
    def P(i, v):
        a = -math.pi / 2 + 2 * math.pi * i / n
        return cx + r * v * math.cos(a), cy + r * v * math.sin(a)
    c = []
    for anel in (0.25, 0.5, 0.75, 1.0):
        pts = [P(i, anel) for i in range(n)]
        c.append(f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x,y in pts)}" '
                 f'fill="none" stroke="{cor_fio}" stroke-width="1"/>')
    for i in range(n):
        x, y = P(i, 1.0)
        c.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x:.1f}" y2="{y:.1f}" '
                 f'stroke="{cor_fio}" stroke-width="1"/>')
    for serie, cor, op, larg in ((otimo, cor_otimo, 0.18, 2), (atual, cor_atual, 0.22, 2.5)):
        pts = [P(i, v) for i, v in enumerate(serie)]
        c.append(f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x,y in pts)}" '
                 f'fill="{cor}" fill-opacity="{op}" stroke="{cor}" stroke-width="{larg}"/>')
    for i, rot in enumerate(eixos):
        x, y = P(i, 1.20)
        an = "middle" if abs(x - cx) < 40 else ("start" if x > cx else "end")
        c.append(_txt(x, y + 6, rot, cor_texto, 19, fam_rot, 500, an, 1.8, True))
    return _svg(w, h, "".join(c))

# PAPEL DA TINTA — cada cor declarada tem função, e função define o piso de
# contraste que ela precisa alcançar NO PIXEL. Um fio de régua pode ser tênue de
# propósito; a linha que prova a tese, não. Sem este mapa o portão não sabe o que
# cobrar de quê, e trataria régua e argumento com o mesmo rigor — reprovando a
# sutileza ou aprovando a invisibilidade.
PAPEL = {
    "cor_curva": "argumento", "cor_linha": "argumento", "cor_arco": "argumento",
    "cor_atual": "argumento", "cor_otimo": "argumento", "cor_ruim": "argumento",
    "cor_otima": "argumento", "cor_faixa": "argumento", "cor_marca": "argumento",
    "cor_texto": "rotulo", "cor_muted": "rotulo",
    "cor_fio": "estrutura", "cor_trilho": "estrutura", "cor_area": "estrutura",
    "cor_lab": "estrutura",
}

GRAFICOS = {"curva_normal": curva_normal, "mostrador": mostrador,
            "trajetoria": trajetoria, "small_multiples": small_multiples, "radar": radar}
