# Documentação do VOLC O.S.

Esta é a porta de entrada documental. Conteúdo vigente e conteúdo histórico não
devem ocupar o mesmo nível de autoridade.

## Comece aqui

- [`../PRODUCT.md`](../PRODUCT.md) — visão compacta do produto;
- [`ROADMAP-VOLC-OS.md`](ROADMAP-VOLC-OS.md) — próximos passos do sistema;
- [`volc-os-graph/ARQUITETURA-PERMANENTE.md`](volc-os-graph/ARQUITETURA-PERMANENTE.md) — Mapa Vivo;
- [`architecture/REPOSITORY-HYGIENE.md`](architecture/REPOSITORY-HYGIENE.md) — regras de organização;
- [`architecture/PROFESSIONALIZATION-ROADMAP.md`](architecture/PROFESSIONALIZATION-ROADMAP.md) — ondas para escalar sem reescrita total;
- [`design/DESIGN-SYSTEM.md`](design/DESIGN-SYSTEM.md) — linguagem visual VOLC;
- [`TRAFEGO.md`](TRAFEGO.md) — **porta de entrada da camada de Tráfego** (índice, precedência e o que foi superado);
- [`COMECE-AQUI-TRAFEGO.md`](COMECE-AQUI-TRAFEGO.md) — prompt de abertura de sessão de Tráfego (não é spec).

## Zonas

| Pasta | Conteúdo | Autoridade |
|---|---|---|
| `architecture/` | decisões estruturais, inventário e evolução | vigente |
| `design/` | design system e decisões visuais | vigente |
| `volc-os-graph/` | fontes e operação do Mapa Vivo | canônica |
| `superpowers/specs/` | especificações de entregas | por escopo/data |
| `superpowers/plans/` | planos de implementação | por escopo/data |
| `reference/` | catálogos e material consultivo | referência, pode envelhecer |
| `audits/` | auditorias datadas | evidência, não regra automática |
| `archive/` | histórico preservado | não vigente |

### Camada de Tráfego

Tem porta própria: [`TRAFEGO.md`](TRAFEGO.md). O pacote está em **proposta em revisão**
(24/08/2026) e os fatos medidos ficam em [`EVIDENCIAS-TRAFEGO.md`](EVIDENCIAS-TRAFEGO.md) —
PRD, SPEC, planos e ADRs linkam o ledger em vez de repetir números.

Documentação próxima de um módulo pode permanecer ao lado do código quando for
essencial para operá-lo, como `README.md`, contratos de prompt e guias de migração.

## Regra de atualização

Uma mudança material de arquitetura deve atualizar, na mesma entrega:

1. o documento canônico afetado;
2. o Mapa Vivo;
3. referências de paths;
4. o inventário de higiene, executando `python3 scripts/auditar_repositorio.py`.
