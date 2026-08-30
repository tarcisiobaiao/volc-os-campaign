"""Camada psicológica — a tensão que faz alguém virar a página.

O papel dela no motor não é pontuar. É **transferir**.

O modelo pontua bem quando reconhece o arquétipo, porque aí tem RPM medido. Mas
num país novo as regras de arquétipo não disparam: `Cesantias` não casa com
nenhum padrão brasileiro, e `subsidio de vivienda ds49` muito menos. Sem uma
ponte, todo termo estrangeiro cai em "sem arquétipo" e perde o RPM.

A ponte é a tensão. `FGTS` e `Cesantias` não compartilham nenhuma letra, mas
compartilham a pergunta: *"tem dinheiro meu parado que eu não sei sacar?"*. O
nome é local, a ansiedade é universal — e é a ansiedade que decide se a pessoa
lê três páginas ou fecha a aba.

Por isso os marcadores aqui são **formas de pergunta**, não substantivos. A
estrutura interrogativa de uma aflição é a mesma em qualquer língua:
"quando cai" / "cuándo cobro" / "when do I get paid" é o mesmo objeto mental.
Substantivo não viaja; pergunta viaja.

As sete tensões saem dos ganchos destilados dos vencedores medidos, não de um
manual de copywriting.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# ── as sete tensões ──────────────────────────────────────────────────────────
# Cada uma com a intensidade medida no arquétipo onde ela domina, e com os
# arquétipos que a acionam. A intensidade vem do desfecho, não de julgamento.

TENSOES = {
    "medo_de_perder": {
        "pergunta": "vai cair pra mim? se eu perder a data, perco o dinheiro",
        "intensidade": 0.77,
        "arquetipos": ["transferencia_renda", "cadastro_social_unico"],
    },
    "dinheiro_esquecido": {
        "pergunta": "tem dinheiro meu parado que eu não sei sacar?",
        "intensidade": 0.73,
        "arquetipos": ["fundo_verba_trabalhista"],
    },
    "acesso_negado": {
        "pergunta": "o direito é meu, mas o sistema não me deixa chegar nele",
        "intensidade": 0.64,
        "arquetipos": ["previdencia_aposentadoria", "app_servico_gov"],
    },
    "obrigacao_legal": {
        "pergunta": "me pediram esse documento e eu não tenho — como tiro agora?",
        "intensidade": 0.77,
        "arquetipos": ["documento_identidade_civil", "transito_veicular", "tributo_fiscal"],
    },
    "ascensao": {
        "pergunta": "isso pode mudar minha vida e é de graça — eu entro?",
        "intensidade": 0.78,
        "arquetipos": ["curso_gratuito_profissionalizante", "habitacao_popular",
                       "emprego_jovem_aprendiz", "educacao_superior_bolsa"],
    },
    "urgencia_de_renda": {
        "pergunta": "preciso ganhar dinheiro essa semana — como começo?",
        "intensidade": 0.66,
        "arquetipos": ["emprego_gig_entrega", "emprego_concurso_publico",
                       "emprego_vaga_privada"],
    },
    "protecao_familiar": {
        "pergunta": "se alguém aqui em casa passar mal, eu tô coberto?",
        "intensidade": 0.84,
        "arquetipos": ["saude_publica"],
    },
}

# ── marcadores: formas de pergunta, por tensão, multilíngue ──────────────────
# pt/es/en na mesma lista de propósito. Não são traduções uma da outra — são as
# formas que a demanda realmente usa em cada língua, extraídas das keywords com
# clique medido.

_MARCADORES: dict[str, list[str]] = {
    "medo_de_perder": [
        r"quando (cai|sai|paga|recebo)", r"cu[aá]ndo (cobro|pagan|sale|deposit)",
        r"when.{0,12}(paid|deposit|due|does it arrive)", r"payment (date|schedule)",
        r"calend[aá]rio", r"fecha de pago", r"will i (get|receive)",
        r"\bdata (do|de) pagamento", r"vai cair", r"lista de", r"quem recebe",
        r"qui[eé]nes? (cobran|reciben)",
    ],
    "dinheiro_esquecido": [
        r"tenho direito", r"tengo derecho", r"valores? a receber",
        r"esquecid", r"olvidad", r"n[aã]o sacad", r"sin (cobrar|retirar)",
        r"unclaimed", r"am i (owed|entitled)", r"do i have money",
        r"how much (do i have|am i owed)", r"how to (withdraw|claim|cash out)",
        r"saldo", r"quanto tenho", r"cu[aá]nto tengo", r"como sacar", r"c[oó]mo retirar",
    ],
    "acesso_negado": [
        r"como (acess|entrar|logar)", r"c[oó]mo (ingres|acced)",
        r"senha", r"contrase[nñ]a", r"login", r"n[aã]o consigo", r"no puedo",
        r"turnos?", r"agendar", r"comprovante", r"constancia", r"certificad[oa] de",
        r"can't (log ?in|access)", r"reset (my )?password", r"book an appointment",
        r"proof of", r"replacement (card|document)",
        r"recibo", r"segunda ?via de", r"2[ªa]? ?via",
    ],
    "obrigacao_legal": [
        r"como (tirar|emitir|fazer)", r"c[oó]mo (sacar|tramitar|obtener)",
        r"how (to|do i) (get|apply|renew|register|enroll)", r"\bdeadline\b",
        r"\bprazo\b", r"\bplazo\b", r"vence", r"expire", r"obrigat[oó]ri",
        r"obligatori", r"multa", r"documento", r"renova", r"\bdni\b",
    ],
    # `\bcurso` com fronteira é obrigatório: sem ela o padrão casa dentro de
    # "con-curso", e todo concurso público virava ascensão. `bolsa` e
    # `certificado` saíram: "Bolsa Família" é transferência de renda e
    # "Certificado de Reservista" é documento — ambos ambíguos demais para
    # servirem de marcador.
    "ascensao": [
        r"gratuit", r"gr[aá]tis", r"\bfree\b", r"\bcursos?\b", r"capacita",
        r"inscri[cç][aã]o", r"inscripci[oó]n", r"como se inscrever",
        r"c[oó]mo (inscribir|postular)", r"quem tem direito", r"qui[eé]n puede",
        r"who (is eligible|qualifies|can apply)", r"am i eligible",
        r"eligibility (requirements|criteria)", r"free (course|training|program)",
        r"casa pr[oó]pria", r"vivienda", r"subsidio de vivienda",
        r"\bbeca\b", r"financiamento estudantil",
    ],
    "urgencia_de_renda": [
        r"como (trabalhar|ser|virar)", r"c[oó]mo (trabajar|ser)",
        r"quanto ganha", r"cu[aá]nto (gana|paga)", r"cadastro de",
        r"vaga", r"empleo", r"repartidor", r"entregador", r"motorista",
        r"trabalhar com", r"renda extra", r"ingreso extra",
        r"how much (do|does).{0,18}(earn|pay|make)", r"sign up to (drive|deliver)",
        r"become a (driver|courier|rider)", r"side (income|hustle)",
    ],
    "protecao_familiar": [
        r"como saber s[ei]", r"c[oó]mo saber si", r"estou cadastrad",
        r"estoy (afiliad|inscrit)", r"qual (plano|posto)", r"qu[eé] (eps|obra social)",
        r"cobertura", r"aten[cç][aã]o", r"vacina", r"consulta m[eé]dica",
        r"am i covered", r"which (plan|provider) am i", r"health (plan|coverage)",
        r"medicare|medicaid|nhs\b",
    ],
}

_COMPILADOS = {
    t: [re.compile(p, re.IGNORECASE) for p in ps] for t, ps in _MARCADORES.items()
}

_ARQ_PARA_TENSAO = {
    arq: t for t, d in TENSOES.items() for arq in d["arquetipos"]
}


def _sem_acento(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


@dataclass(frozen=True)
class Leitura:
    tensao: str | None
    intensidade: float
    confianca: str          # alta | media | nenhuma
    marcadores: tuple[str, ...]
    arquetipos_provaveis: tuple[str, ...]

    @property
    def transferivel(self) -> bool:
        """Se dá para emprestar o RPM de um arquétipo conhecido a este termo."""
        return self.tensao is not None and bool(self.arquetipos_provaveis)


def por_arquetipo(arquetipo: str | None) -> str | None:
    return _ARQ_PARA_TENSAO.get(arquetipo or "")


def ler(termo: str, *, contexto: str = "") -> Leitura:
    """Classifica a tensão de um termo pela forma da pergunta que ele carrega.

    `contexto` é a descrição do que a entidade é — quando existe, ajuda muito,
    porque o nome sozinho (`Cesantias`) não carrega a pergunta, mas a descrição
    ("dinheiro que a empresa deposita e o trabalhador saca ao ser demitido")
    carrega.
    """
    alvo = f"{termo} {contexto}".strip()
    pontos: dict[str, list[str]] = {}
    for tensao, padroes in _COMPILADOS.items():
        achados = [p.pattern for p in padroes if p.search(alvo)]
        if achados:
            pontos[tensao] = achados

    if not pontos:
        return Leitura(None, 0.0, "nenhuma", (), ())

    tensao = max(pontos, key=lambda t: (len(pontos[t]), TENSOES[t]["intensidade"]))
    n = len(pontos[tensao])
    # Duas tensões empatadas em um marcador cada é ruído, não leitura.
    confianca = "alta" if n >= 2 else ("media" if len(pontos) == 1 else "nenhuma")

    return Leitura(
        tensao=tensao,
        intensidade=float(TENSOES[tensao]["intensidade"]),
        confianca=confianca,
        marcadores=tuple(pontos[tensao]),
        arquetipos_provaveis=tuple(TENSOES[tensao]["arquetipos"]),
    )
