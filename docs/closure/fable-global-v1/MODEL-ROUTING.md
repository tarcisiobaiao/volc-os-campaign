# Roteamento de modelos — fechamento global VOLC O.S.

Princípio econômico: o modelo mais caro descobre e decide; os mais baratos
executam o que já foi especificado. Uma missão só desce de tier quando a
arquitetura dela já está fechada (contrato, ownership, gates e aceite binário).

## Tabela de funções

| Modelo | Função no fechamento | Quando usar | Quando NÃO usar |
|---|---|---|---|
| **Fable 5** | Arquitetura, especificação, síntese, decisões de alta ambiguidade, revisão científica | Specs godmode, reconciliação de contradições entre fontes, decisões de fronteira entre pacotes, revisão final de contratos de dados | Implementação mecânica; rodar gates; tarefas com spec fechada |
| **Opus 5** | Execução complexa e revisão de contratos | Integração de branches com conflito real, migrações com risco, fact-check de APIs Google, revisão de PR grande | Microcorreções; tarefas repetitivas bem especificadas |
| **Codex GPT-5.6 Sol** | Implementação, testes, integração, correção | Missões com spec pronta e aceite binário: writers de engine, ratchets de teste, correção de defeitos apontados por revisão | Descoberta de arquitetura; decisões de produto; specs |
| **Gemini 3.7 Flash** | Execução bem especificada, análise repetível, tarefas delimitadas | Coleta/diagnóstico read-only em série (diagnóstico Search, observabilidade PMax, health deadman), varreduras com contrato de saída fixo | Qualquer missão que dependa de descobrir arquitetura ou negociar contrato |
| **DeepSeek** | Microcorreções determinísticas de baixo risco | Reparo de identificador/símbolo com AST+allowlist (padrão do sniper 4/4), ajustes mecânicos com validador determinístico atrás | Copy/semântica (0/4 de aceite humano no smoke de 28/08), qualquer coisa sem gate determinístico |

## Regras de encaminhamento

1. **Nenhuma missão desce para Gemini/DeepSeek com pergunta aberta de
   arquitetura.** Se a spec contém "descobrir", "decidir" ou "avaliar
   alternativas", ela sobe para Fable/Opus primeiro e volta como spec fechada.
2. **Toda missão de writer tem um reviewer de tier igual ou superior** quando o
   diff toca contrato de dados, dinheiro, mutação externa ou segurança. O padrão
   já praticado no harness (writer Codex + adversário Codex + reviewer
   Fable/Opus) é o piso para missões CL-B, CL-C e CL-D.
3. **Evidência do smoke DeepSeek (P10-T10) limita o escopo DeepSeek**: schema
   ok em 7/8, código 4/4 com AST+prova funcional, copy 0/4 no aceite semântico.
   Portanto: DeepSeek nunca recebe missão cujo aceite é julgamento semântico.
4. **Gemini executa, não interpreta política.** As runs de 29/08 (adk-smoke,
   search-diagnostico, pmax-observabilidade, health-deadman) definem o perfil:
   entrada delimitada, saída tipada, zero mutate. Manter esse envelope.
5. **Fable não se auto-rebaixa.** Sessões de síntese/spec permanecem em Fable 5
   até o artefato final; investigação paralela pode descer de tier, a decisão não.

## Mapeamento missão → modelo (ondas 1–2)

Ver `EXECUTION-WAVES.md` para a lista completa; cada spec em `missions/*.json`
declara `recommended_model` e `reviewer_model` individualmente.
