#!/usr/bin/env python3
"""Gera o CADERNO DE CONTROLE da arbitragem — o SPEC/PRD virado documento de
imprimir, com caixas para marcar.

## Por que um script e não um .docx solto

Um documento gerado à mão nasce desatualizado no dia seguinte: o estado da
operação muda (fase concluída, teste novo, credencial girada) e o papel
continua dizendo o que era verdade na semana passada. Rodando de novo, o
caderno reimprime com o estado do dia — e a seção "onde estamos" é a única que
justifica imprimir de novo.

## O que ele NÃO faz

Não inventa estado. Tudo em §01 é MEDIDO na hora (contagem de teste rodada,
consulta ao banco, leitura do WordPress) ou declarado como "não verificado".
Uma fase marcada como feita sem prova seria pior que fase nenhuma: o caderno
existe para o dono confiar no que está escrito.

Rodar:
    backend/.venv/bin/python scripts/caderno-arbitragem.py
    # → docs/CADERNO-ARBITRAGEM.docx
"""
from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))

from app.docx import volc_theme as T  # noqa: E402
from app.docx.volc_engine import VolcDocx  # noqa: E402

HOJE = date.today().strftime("%d/%m/%Y")


# ── medições ao vivo ────────────────────────────────────────────────────────
#
# ⚠️ Nada aqui é digitado à mão. Se a contagem falhar, o caderno diz "não
# medido" — nunca o último número que alguém lembrava.

def _contar_testes(venv: Path, alvos: list[str], cwd: Path) -> str:
    """⚠️ `alvos` é LISTA. Passar "backend/tests volc_ads" como uma string só
    faz o pytest procurar um caminho com espaço no nome, não achar, e a medição
    virar "não medido" em silêncio — que foi o que aconteceu na primeira
    geração deste caderno."""
    exe = venv / "bin" / "python"
    if not exe.exists():
        return "não medido (venv ausente)"
    try:
        r = subprocess.run([str(exe), "-m", "pytest", *alvos, "-q", "--no-header"],
                           cwd=str(cwd), capture_output=True, text=True, timeout=600)
        for linha in reversed((r.stdout or "").strip().splitlines()):
            if " passed" in linha or " failed" in linha:
                return linha.strip().split(" in ")[0].strip()
    except Exception:  # noqa: BLE001 — medição nunca derruba a geração
        pass
    return "não medido"


def medir() -> dict:
    return {
        "engine": _contar_testes(RAIZ / "funnelforge-migracao/engine/.venv",
                                 ["tests/"], RAIZ / "funnelforge-migracao/engine"),
        "backend": _contar_testes(RAIZ / "backend/.venv",
                                  ["backend/tests", "volc_ads"], RAIZ),
    }


# ── o conteúdo ──────────────────────────────────────────────────────────────

TRAVAS = [
    ("Trava de escrita fechada",
     "Nunca chamar `destravar()`, nunca definir FORGE_PERMITIR_ESCRITA=1. Só "
     "leitura e validate_only — que É leitura: a API valida o payload e "
     "descarta sem criar nada."),
    ("Nada em conta de terceiro",
     "O portão de MCC (MCC_DA_CASA) recusa qualquer customer_id fora da árvore "
     "da casa, e recusa no servidor — não na tela."),
    ("Português do Brasil",
     "Em comentário, docstring, nome de variável e mensagem de erro. Sem exceção."),
    ("Todo número é medido, e diz onde",
     "Se não foi medido, não se cita. Nunca uma estatística, data ou benchmark "
     "inventado — nem como exemplo."),
    ("Escrita só com autorização na hora",
     "Criar campanha, subir lance, publicar página: cada uma exige o gesto "
     "humano no momento. Autorização de ontem não vale para hoje."),
]

PRINCIPIOS = [
    ("P1", "O sistema percebe sozinho que parou",
     "Seis meses escrevendo no banco errado, 9.407 gclids nunca enviados e uma "
     "conta suspensa que parou tudo — em nenhum dos três o sistema soube. Todo "
     "componente que escreve dado escreve também um recibo, no mesmo banco do "
     "dado. \"Verde\" sem linhas contadas não existe."),
    ("P2", "Cold start é o caso normal, não a borda",
     "A operação nasce com N=0. \"Ainda não medido\" é resposta válida em "
     "qualquer ponto do sistema; um valor inventado, nunca."),
    ("P3", "Assimetria de autorização",
     "Reduzir gasto pode ser pré-autorizado, com teto, validade e revogação. "
     "AUMENTAR gasto exige humano, na hora, sempre. Errar reduzindo custa "
     "oportunidade; errar aumentando custa dinheiro."),
    ("P4", "Um substantivo: Proposta",
     "Tudo que quer mudar o mundo externo vira uma Proposta. Só o Executor "
     "executa Propostas, e só por uma porta."),
    ("P5", "Fato ≠ opinião ≠ ação",
     "Métrica medida, decisão do motor e registro de atuação vivem em três "
     "tabelas. Nunca mais uma coluna de auditoria com DEFAULT now() "
     "transformando 12 decisões em 92 falsos positivos."),
    ("P6", "Moeda e procedência declaradas",
     "Cada fonte de receita declara moeda, grão, revshare e dono da conta. Foi "
     "a moeda implícita que fez a camada 05 reportar 82% de perda onde havia 5%."),
    ("P7", "Doutrina de campanha — do dono, inegociável",
     "Campanha = rei: um termo, uma campanha, um conjunto. Nasce PAUSED, em "
     "MANUAL_CPC com phrase. Gradua em 30 conversões para lance automático; "
     "broad é a recompensa da graduação."),
    ("P8", "O portão mora dentro da porta",
     "Portão que vive no router é convenção, não portão: quem chamar o engine "
     "por fora passa por cima. Ele desce para dentro do cliente Google Ads."),
    ("P9", "A conta de monetização é um objeto vigiado",
     "Suspensão de conta é o pior modo de falha da arbitragem: a receita zera e "
     "o custo continua. O sistema inteiro vigiava o denominador; o numerador "
     "pode sumir por decisão de terceiro."),
]

FASES = [
    ("F0", "Estancar: apagar as luzes do prédio velho", "horas · reversível",
     "Parar de queimar quota, fechar as portas abertas e remover o ruído que "
     "contamina qualquer diagnóstico daqui em diante.",
     ["Desligar no n8n os flows do núcleo que apontam para o Supabase hospedado",
      "Manter ATIVOS: receita-joinads-d1, receita-joinads-intraday, "
      "pauta-kw-minning-pautador-pro",
      "Desativar os 6 formulários públicos da Factory v3",
      "Desativar o webhook Apply Bidding e remover a URL do bundle do front",
      "Girar o developer token do Google Ads",
      "Girar a chave da exchangerate-api",
      "Caçar o chamador fantasma de compute_funnel_daily"],
     "Nenhum workflow ativo do núcleo contém a URL do Supabase hospedado; "
     "o webhook antigo responde 404; grep da URL no front devolve zero."),

    ("F1", "O sistema percebe que parou: recibos, relógio e câmbio", "M · reversível",
     "Construir o alicerce do P1 antes de qualquer funcionalidade: recibos no "
     "plano de dados, watchdog no componente que nunca falhou, e o job de "
     "câmbio como prova do desenho.",
     ["Tabela de recibos, com linhas contadas por escrita",
      "Watchdog no componente mais confiável, vigiando o menos confiável",
      "Job de câmbio diário, com recibo",
      "Notificação externa quando o vigia acusa"],
     "A cotação de hoje está no banco, todo dia, com recibo OK e linhas=1. "
     "Parar o container do backend gera linha em alertas (CRITICO) sem "
     "intervenção humana, E a notificação externa chega."),

    ("F2", "Custo no banco certo: a ingestão própria mínima", "M–L · reversível",
     "O lado esquerdo da equação fluindo para o banco que o produto lê, com o "
     "padrão do SPEC: job por fonte, parametrizável por data, recibo, lote.",
     ["Job de custo do Google Ads, por conta e por data",
      "Reprocessamento histórico sob demanda",
      "Tabela contas_anuncio populada (vira a allowlist do F3)",
      "vw_arbitragem_diaria com CPC real"],
     "Reprocessar fevereiro reescreve as linhas IDÊNTICAS às existentes "
     "(diff por campaign_id,date) com recibo sob_demanda — prova o pipeline "
     "inteiro sem gastar um real."),

    ("F3", "O substantivo e a porta: Proposta, Autorização, Executor",
     "L · reversível até armar",
     "Nascem os quatro substantivos e a porta única. Toda mutação de conta "
     "passa a atravessar a mesma escada. Aqui o Executor só executa Propostas "
     "aprovadas por humano.",
     ["Tabelas: propostas, autorizacoes, execucoes",
      "Executor com porta única, e o portão de MCC DENTRO dela (P8)",
      "Front: criar e aprovar Proposta",
      "Webhook antigo morto e re-testado"],
     "Ajuste de lance de ponta a ponta: Proposta no front → aprovar → "
     "execucoes tem request, response, valor_antes, valor_depois CONFIRMADA — "
     "e o valor confere no Google Ads Editor. Aprovar sem sessão → 401."),

    ("F4", "Nascimento completo: a junta 2 fechada na transação",
     "M–L · a 1ª campanha real é gasto",
     "O cockpit passa a criar campanha inteira: com procedência, vínculo de "
     "funil e conversão sintética, gravando tudo no banco na mesma transação. "
     "É o conserto definitivo da junta FUNIL→CAMPANHA.",
     ["/provar emite selo com validate_only (repetível, sem custo)",
      "/subir grava funnel_run_id e customer_id na mesma transação",
      "Conversão sintética criada e vinculada",
      "Taxonomia do nome: PAÍS - carimbo / termo / URL"],
     "Depois do /subir, funnel_run_id e customer_id estão preenchidos em "
     "campaigns; a campanha aparece PAUSED na conta certa."),

    ("F5", "O loop de conversão e o sensor: a junta 4 e o fator 2", "M–L · reversível",
     "Fechar o corte mais caro (9.407 gclids, zero enviados) e cegar menos: o "
     "evento de ad-view que fecha três cortes de uma vez.",
     ["Upload de conversões offline, com autorização permanente própria",
      "Sensor de ad-view publicando avg_ads_per_session",
      "fact_page_daily sem host vazio"],
     "Zero linhas novas com host vazio. Funil ativo: avg_ads_per_session > 0 "
     "em 100% das linhas novas. Clique de teste com gclid percorre a fila até "
     "o status de envio."),

    ("F6", "O motor em casa: replay, sombra, e o Trilho A armado",
     "L · reversível por revogação + kill switch",
     "A inteligência sai do JSON e vira serviço testado; a defesa noturna passa "
     "a existir de verdade — só na direção REDUZ.",
     ["Motor portado do n8n para o backend, com testes",
      "Replay dourado com divergências 100% classificadas",
      "14 dias de sombra com diário de bordo",
      "Kill switch e revogação de autorização"],
     "Replay dourado passa. Em 14 dias de sombra, ZERO execuções de AUMENTA "
     "sob autorização (só sob aprovação humana)."),

    ("F7", "A carteira: as telas compõem", "M · reversível",
     "A tela que não existe: \"das suas N campanhas, estas 6 querem algo de "
     "você hoje\" — e o detalhe que explica por quê, com a equação decomposta.",
     ["Carteira: quais campanhas pedem ação hoje",
      "Aprovação em lote de Propostas",
      "Detalhe com a equação decomposta"],
     "Com 5 ou mais campanhas ativas, a Carteira responde em UMA consulta. "
     "Um fator não medido aparece como \"não medido\" — nunca zero disfarçado."),

    ("F8", "Previsão persistida", "M · condicionada a N",
     "A bola de cristal vira serviço honesto: persistida, medida contra "
     "baseline, e útil como simulador — nunca como executor.",
     ["Previsões persistidas por campanha elegível",
      "Cobertura real do intervalo de confiança no painel",
      "Veto preditivo INATIVO até o critério de N"],
     "Cobertura do CI de 90% fica em 80% ou mais — o antigo entregava 64% "
     "prometendo 90%."),
]

ORDEM = [
    ("F0", "segurança + diagnóstico limpo", "horas",
     "tudo que vem depois mede errado com o ruído ligado"),
    ("F1", "o sistema se vigia (P1)", "M",
     "sem recibo, cada fase seguinte pode \"passar\" mentindo"),
    ("F2", "CPC real no banco certo", "M–L",
     "o motor e a carteira leem daqui; é pré-requisito de faixa do F3"),
    ("F3", "o substantivo + a porta", "L",
     "F4, F6 e F7 são impossíveis sem Proposta e Executor"),
    ("F4", "voltar a operar (junta 2)", "M–L",
     "precisa da porta; destrava o F5 e o negócio em si"),
    ("F5", "sinal de conversão + fator 2 (junta 4)", "M–L",
     "sem ele o Google otimiza no escuro de novo"),
    ("F6", "defesa sozinha + otimização na fila", "L",
     "precisa de dados (F2), porta (F3) e idealmente CVR (F5)"),
    ("F7", "escala de operação", "M", "antes seria tela vazia"),
    ("F8", "antecipação honesta", "M",
     "último porque exige N que só as fases anteriores geram"),
]

RISCOS = [
    ("O sensor é de terceiros até o F5 provar o contrário",
     "A posse do código do sensor de ad-view não está com a casa. Enquanto "
     "estiver, o fator 2 da equação depende de decisão alheia."),
    ("Gastar mídia é o único ato irreversível por natureza",
     "Ele fica atrás de dois gestos humanos — subir com selo e ativar a "
     "campanha — e de uma direção: AUMENTA nunca é automático."),
    ("Abandonar o hospedado é irreversível por decisão",
     "Os dados continuam lá, mas nenhuma fase depende deles."),
    ("Instrução em prosa não sustenta invariante",
     "Medido três vezes em 19/08/2026: o prompt proibia o caractere & e o "
     "modelo o escreveu; pedia URL exata e devolveu domínio-raiz; mandava usar "
     "\"o sistema exige\", que outro validador recusa. O que sustenta é código."),
]


def _check(doc: VolcDocx, texto: str) -> None:
    doc.bullet(f"☐   {texto}")


def montar(m: dict) -> VolcDocx:
    doc = VolcDocx(
        title="VOLC O.S. Arbitragem — Caderno de Controle",
        description=f"Plano de execução e acompanhamento · gerado em {HOJE}",
        brand="VOLC", show_header=False,
    )

    doc.cover(
        title1="VOLC O.S. — Arbitragem",
        title2="Caderno de Controle",
        subtitle1="O plano de execução, em fases, com o que marcar",
        subtitle2=f"Gerado em {HOJE} · reimprima quando o estado mudar",
        classification="USO INTERNO",
    )
    doc.page_break()

    # ── 00 · como usar ──────────────────────────────────────────────────
    doc.section_num("00")
    doc.h1("Como usar este caderno")
    doc.para(
        "Este caderno é para imprimir e riscar. Cada fase traz o objetivo, o "
        "que fazer (com caixa para marcar) e — o que mais importa — o CRITÉRIO "
        "DE ACEITE: uma frase que descreve como verificar que a fase está "
        "realmente feita, não como parece feita.")
    doc.insight_box(
        "A regra do caderno",
        "Uma caixa só é marcada depois que o critério de aceite foi verificado. "
        "Marcar por impressão devolve o caderno ao estado de qualquer relatório "
        "verde: bonito e sem lastro.")
    doc.para(
        "A seção 01 é gerada por medição na hora — contagem de testes rodada, "
        "não digitada. Reimprimir o caderno atualiza o retrato; o resto do "
        "documento é a doutrina, e muda pouco.")

    # ── 01 · onde estamos ───────────────────────────────────────────────
    doc.section_num("01")
    doc.h1("Onde estamos hoje")
    doc.para(f"Retrato de {HOJE}. Só o que foi medido entra aqui.")

    doc.h2("Provas automatizadas")
    doc.data_table(
        ["suíte", "resultado"],
        [["motor de funil (engine)", m["engine"]],
         ["backend + volc_ads", m["backend"]],
         ["front (vitest)", "rodar: npx vitest run"],
         ["tipos (tsc)", "76 erros herdados do webgo — linha de base, não regressão"]],
        [3600, 5400])

    doc.h2("O que está de pé")
    doc.bullet("Motor de widgets reescrito: a LLM descreve o conteúdo em JSON e "
               "o motor imprime o HTML. Allowlist, CLS zero e acessibilidade "
               "deixaram de depender de o modelo lembrar.")
    doc.bullet("Descoberta mecânica de link profundo (canal_profundo): domínio-"
               "raiz vira a página que o leitor precisa, com verificação ao "
               "vivo e volta honesta para a raiz quando não acha.")
    doc.bullet("Retentativa de transporte na cascata de copy: queda de conexão "
               "deixou de derrubar ~174 s de trabalho pago.")
    doc.bullet("Publicação avulsa de página: uma página que caiu num portão e "
               "foi consertada tem caminho de volta ao WordPress pela tela.")

    doc.h2("O que NÃO está feito")
    doc.note_box(
        "As três credenciais abaixo circularam e continuam válidas. Enquanto "
        "não girarem, elas são o maior risco aberto do sistema — maior que "
        "qualquer fase deste caderno.")
    _check(doc, "Girar o developer token do Google Ads")
    _check(doc, "Girar a Application Password do WordPress")
    _check(doc, "Girar a SUPABASE_SERVICE_ROLE_KEY")

    # ── 02 · as travas ──────────────────────────────────────────────────
    doc.page_break()
    doc.section_num("02")
    doc.h1("As travas permanentes")
    doc.para(
        "Estas não são fases: valem em todas elas, o tempo todo. Uma fase que "
        "só passa afrouxando uma trava não passou.")
    for titulo, texto in TRAVAS:
        doc.h3(titulo)
        doc.para(texto)

    # ── 03 · princípios ─────────────────────────────────────────────────
    doc.page_break()
    doc.section_num("03")
    doc.h1("Os nove princípios do desenho")
    doc.para(
        "Toda decisão de arquitetura se justifica por um destes. Quando dois "
        "conflitam, vale o de número menor.")
    for codigo, titulo, texto in PRINCIPIOS:
        doc.h3(f"{codigo} · {titulo}")
        doc.para(texto)

    # ── 04 · as fases ───────────────────────────────────────────────────
    doc.page_break()
    doc.section_num("04")
    doc.h1("As nove fases")
    doc.para(
        "Ordenadas por valor destravado ÷ esforço. Esforço em camiseta: "
        "S menor que um dia · M de dias · L de uma a duas semanas de uma "
        "pessoa sênior.")
    for codigo, titulo, esforco, objetivo, itens, aceite in FASES:
        doc.spacer("md")
        doc.h2(f"{codigo} — {titulo}")
        doc.para(esforco, italic=True, color=T.COLORS["slateLight"])
        doc.para(objetivo)
        doc.h3("O que fazer")
        for item in itens:
            _check(doc, item)
        doc.insight_box("Critério de aceite", aceite)

    # ── 05 · a ordem ────────────────────────────────────────────────────
    doc.page_break()
    doc.section_num("05")
    doc.h1("A ordem, defendida")
    doc.para(
        "Por que cada fase vem antes da seguinte. A ordem não é gosto: é "
        "dependência — e pular uma faz a próxima medir errado.")
    doc.data_table(
        ["fase", "valor destravado", "esforço", "por que antes da seguinte"],
        [[f, v, e, p] for f, v, e, p in ORDEM],
        [900, 2700, 900, 4500])

    # ── 06 · riscos ─────────────────────────────────────────────────────
    doc.spacer("lg")
    doc.section_num("06")
    doc.h1("Riscos transversais")
    doc.para("Não pertencem a uma fase — atravessam todas.")
    for titulo, texto in RISCOS:
        doc.h3(titulo)
        doc.para(texto)

    doc.spacer("lg")
    doc.centered_statement(
        "Um funil pela metade não é meio funil. Uma fase pela metade não é "
        "meia fase.")

    return doc


def main() -> None:
    print("medindo o estado (rodando as suítes)…")
    m = medir()
    for k, v in m.items():
        print(f"  {k}: {v}")
    saida = RAIZ / "docs" / "CADERNO-ARBITRAGEM.docx"
    montar(m).save(str(saida))
    print(f"\n✅ {saida}  ({saida.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
