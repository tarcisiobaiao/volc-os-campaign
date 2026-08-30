"""Mock de copy — determinístico, sem rede, roteirizável por gatilho.

Mesma doutrina do `app/llm/mock.py` do backend: cliente falso que produz saída
estruturalmente válida para que a esteira inteira rode antes de existir chave.
Mas **não é o mesmo objeto**: aquele implementa `DiscoveryEngine`
(`discover`/`mine`/`build_funnel`) e não tem `complete()`; a geração de copy
precisa de um cliente de texto. Reaproveitar aquele exigiria torcer o contrato
dos dois lados.

O que este acrescenta ao mock do backend: **roteiro**. Cada chamada consome a
próxima resposta da lista, então um teste pode encenar exatamente um gatilho da
cascata — JSON ilegível na primeira, contagem a menos na segunda, e assim por
diante — e provar que a cascata reage como projetado, sem gastar um token.

Nada aqui fala com a rede. Nada aqui toca conta.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..gads.errors import ChavePolitica, ErroGads, FalhaGads, Politica


class RoteiroEsgotado(RuntimeError):
    """A cascata pediu mais gerações do que o roteiro previu.

    É um sinal útil, não um acidente: significa que a cascata não parou onde o
    teste esperava que parasse.
    """


@dataclass
class ClienteMock:
    """Cliente de texto roteirizado. Uma resposta por chamada, em ordem.

    Cada item do roteiro pode ser:
      str   — devolvido cru (use para encenar JSON ilegível);
      dict  — serializado em JSON (o caminho normal);
      Exception — levantada (para encenar falha de transporte).
    """

    roteiro: list = field(default_factory=list)
    chamadas: list[tuple[str, str]] = field(default_factory=list)
    nome: str = "mock"

    def gerar(self, sistema: str, usuario: str) -> str:
        self.chamadas.append((sistema, usuario))
        if not self.roteiro:
            raise RoteiroEsgotado(
                f"chamada {len(self.chamadas)} sem resposta no roteiro"
            )
        resposta = self.roteiro.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        if isinstance(resposta, dict):
            return json.dumps(resposta, ensure_ascii=False)
        return str(resposta)

    @property
    def n_chamadas(self) -> int:
        return len(self.chamadas)

    @property
    def n_completas(self) -> int:
        """Quantas foram geração do CONJUNTO, e não de um asset.

        É a métrica que prova que a cascata não regenerou tudo por preguiça.
        """
        return sum(1 for s, _ in self.chamadas if s == SISTEMA_COMPLETO)

    @property
    def n_assets(self) -> int:
        return sum(1 for s, _ in self.chamadas if s == SISTEMA_ASSET)


# Os dois papéis de chamada. Ficam aqui porque o mock precisa distingui-los
# para contar, e a cascata precisa deles para montar o prompt certo.
SISTEMA_COMPLETO = "gerador-de-copy:conjunto"
SISTEMA_ASSET = "gerador-de-copy:asset"


@dataclass
class JuizMock:
    """Juiz do Google roteirizado — encena `validate_only` sem tocar a conta.

    Devolve `None` (aceito) ou uma `FalhaGads` já classificada. As falhas são
    montadas com os mesmos dataclasses que `classificar()` produz a partir do
    proto real, então a cascata não sabe se está falando com mock ou com a API.
    """

    roteiro: list[FalhaGads | None] = field(default_factory=list)
    chamadas: int = 0

    def __call__(self, dados: dict) -> FalhaGads | None:
        self.chamadas += 1
        if not self.roteiro:
            return None
        return self.roteiro.pop(0)


def falha_politica(
    texto_violador: str,
    *,
    politica: str = "FINANCIAL_SERVICES",
    isentavel: bool = True,
    indice_operacao: int = 12,
) -> FalhaGads:
    """Uma reprovação de política nomeando o texto exato — como a API faz.

    `violating_text` é o que torna a regeneração por asset possível: sem ele, um
    mutate de 72 operações diz que ALGO violou e não diz o quê.
    """
    return FalhaGads(
        erros=(
            ErroGads(
                campo_codigo="policy_violation_error",
                valor_codigo="POLICY_ERROR",
                mensagem=f"Policy violation on {texto_violador!r}.",
                caminho_campo=(
                    f"mutate_operations[{indice_operacao}].ad_group_ad_operation"
                    ".create.ad.responsive_search_ad.headlines[?].text"
                ),
                indice_operacao=indice_operacao,
                gatilho=texto_violador,
                politica=Politica(
                    formato="violacao",
                    descricao_externa="Ads must not imply the site executes the service.",
                    nome_externo="Financial products and services",
                    isentavel=isentavel,
                    chave=ChavePolitica(policy_name=politica,
                                        violating_text=texto_violador),
                ),
            ),
        ),
        request_id="mock-req",
    )


# ── copy base válida, para o roteiro partir de algo que passa ───────────────


def copy_valida(n_headlines: int = 15) -> dict:
    """Um conjunto que passa nas 7 checagens. Ponto de partida dos roteiros.

    Os títulos vêm do brief do FGTS ajustados para caber nas cotas da seção 6 —
    incluindo a correção da repetição de 'saque', que é o achado que o juiz 1
    levantou contra o brief escrito à mão.
    """
    # As 15 linhas abaixo estão DENTRO das faixas da seção 6 (conferido em
    # `_dentro_das_faixas`). Isso não é capricho: se a base já estivesse fora,
    # o alerta de cota pós-substituição seria ruído do mock em vez de sinal da
    # cascata, e o teste mediria a si mesmo.
    headlines = [
        "Saque-Aniversário FGTS 2026",      # 0  M1   ano
        "O Que Mudou no Fundo Este Ano",    # 1  M5   recência
        "Quem Tem Direito Este Ano?",       # 2  M8   leitura + pergunta
        "Tabela Oficial por Faixa",         # 3  M1   leitura
        "Entenda o Passo a Passo",          # 4  M3   leitura
        "A Regra Muda em 31/10/2026",       # 5  M9   ano + dígito não-ano
        "As Regras da Lei do Fundo",        # 6  M1   leitura
        "Carência: Só Após Aderir",         # 7  M4   dois blocos
        "Demissão e Multa Rescisória",      # 8  M1
        "Anual ou Rescisão: A Escolha",     # 9  M4   dois blocos + contraste
        "Não Perde a Multa do Saldo",       # 10 M1   negação
        "Faixas: Da Alíquota à Parcela",    # 11 M4   dois blocos
        "Confira: Vale a Pena?",            # 12 M8   dois blocos + pergunta
        "Emitir o Extrato Anual",           # 13 M7   verbo de execução
        "Solicitar o Saque Anual",          # 14 M7   verbo de execução
    ][:n_headlines]

    mecanicas = ["M1", "M5", "M8", "M1", "M3", "M9", "M1", "M4", "M1", "M4",
                 "M1", "M4", "M8", "M7", "M7"][:n_headlines]
    # Todo título com afirmação concreta (dígito, "até", "muda") declara fato:
    # é a checagem 7. O h0 carrega "2026" e por isso NÃO pode declarar "-".
    fatos_h = ["F3", "F3", "-", "-", "-", "F1", "-", "F5", "-", "-",
               "-", "F2", "-", "-", "-"][:n_headlines]

    dados = {
        "headlines": headlines,
        "descriptions": [
            "Regras do Saque-Aniversário do FGTS em 2026: prazos, limites e "
            "quem tem direito.",
            "Portal informativo: veja a tabela legal por faixa e o cálculo do "
            "valor anual liberado.",
            "Conteúdo apoiado na Lei 8.036/90 e na Resolução CCFGTS 1.130/2025. "
            "Fontes citadas.",
            "Veja o prazo de 90 dias, a regra que muda em 31/10/2026 e a "
            "diferença entre saldo e saque.",
        ],
        "sitelinks": [
            {"title": "Regras de 2026", "description1": "O que vale hoje",
             "description2": "E o que muda em outubro"},
            {"title": "Tabela por faixa", "description1": "Alíquota e parcela",
             "description2": "Conforme o Anexo da lei"},
            {"title": "Quem tem direito", "description1": "As condições mínimas",
             "description2": "Em linguagem simples"},
            {"title": "Demissão e FGTS", "description1": "O que fica disponível",
             "description2": "E o que continua retido"},
        ],
        "callouts": ["Conteúdo informativo", "Fontes oficiais citadas",
                     "Atualizado em 2026", "Portal independente"],
        "snippet": {"header": "Tipos",
                    "values": ["Saque-Aniversário", "Saque-Rescisão",
                               "Multa rescisória", "Saque anual"]},
    }
    return com_ancoragem(dados, mecanicas, fatos_h)


def com_ancoragem(dados: dict, mecanicas: list[str], fatos_h: list[str]) -> dict:
    """Anexa `ancoragem` e `auditoria` COERENTES com o conteúdo.

    Coerentes de propósito: um roteiro que quer encenar ancoragem mentindo
    estraga isto DEPOIS, explicitamente. Assim o teste diz o que está testando.
    """
    from .contrato import comprimento_efetivo, medir

    hs = dados["headlines"]
    dados["ancoragem"] = {
        "headlines": [
            {"i": i, "mecanica": mecanicas[i] if i < len(mecanicas) else "M1",
             "fato": fatos_h[i] if i < len(fatos_h) else "-",
             "papel": "a página | nomear | informação | FONTE",
             "chars": comprimento_efetivo(h)}
            for i, h in enumerate(hs)
        ],
        "descriptions": [{"i": i, "fatos": ["F1", "F4"],
                          "chars": len(d)}
                         for i, d in enumerate(dados["descriptions"])],
        "sitelinks": [{"i": i, "fato": "F2"}
                      for i in range(len(dados["sitelinks"]))],
        "callouts": [{"i": i, "fato": "-"}
                     for i in range(len(dados["callouts"]))],
    }
    contagem = medir(hs)
    contagem["mecanicas_distintas"] = len(set(mecanicas[:len(hs)]))
    contagem["max_titulos_por_fato"] = 2
    dados["auditoria"] = {
        "modo": "com_lastro",
        "contagem_final": contagem,
        "reprovados_politica": [],
        "reprovados_mornidao": [],
        "sem_lastro_evitado": [],
        "incoerencia_destino": "",
        "lacunas": [],
    }
    return dados
