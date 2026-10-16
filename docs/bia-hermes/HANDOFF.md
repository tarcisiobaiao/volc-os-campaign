# Bia web: handoff da missão 3 (chat completo)

Para o integrador da branch `feat/bia-hermes-volc-v1` (worktree `worktrees/bia-hermes-volc-v1`). O handoff das missões 1–2 continua válido em `HANDOFF-INTEGRADOR.md`; este arquivo cobre só o delta da missão 3. A versão para máquina está em `handoff.json`.

**Veredito: `PRONTO_PARA_QA_HUMANO`.**
Provas reais 1–12 passaram (`provas/PROVA-CHAT-20261015.md`). Falta a conferência humana de teclado virtual em celular real, leitor de tela e uma mensagem no Telegram. Há uma decisão de risco aberta para o dono (R9, abaixo).

## Linhagem

- SHA inicial obrigatório: `321266a885f0ab86d7026ca4b6ce7e3b16fe00c9`.
- Commits da missão, em ordem:

| Commit | Conteúdo |
|---|---|
| `3213b243` | backend: anexos, streaming real e comandos `/` |
| `4213e6e5` | frontend: o chat completo |
| `f6e170b4` | bancada visual (`tools/bia-harness`) |
| `7a29a471` | correções da revisão de segurança independente |
| `3ab33b77` | repetir upload só em falha de rede ou servidor |
| último commit | esta documentação |

- Nenhum commit anterior foi reescrito. Não houve merge, push ou deploy.

## O que mudou (arquivos)

**Backend: só módulos da Bia**
- `backend/app/agente_bia/anexos/`: `dominio.py`, `extracao.py`, `armazem.py` (novos).
- `backend/app/agente_bia/comandos/`: `catalogo.py` e `inventario_hermes_v0_18_0.json` (novos).
- Alterados:
  - `aplicacao.py`: mensagem com anexos, `BufferDeFluxo`, `status`.
  - `infra_hermes.py`: stream, conteúdo multimodal, `saude` e `sessao`.
  - `rotas.py`: 6 rotas novas e o campo `anexos`.
  - `portas.py`, `dominio.py`, `cors.py` (cabeçalho `X-Bia-Nome`).
- Testes: `backend/tests/test_agente_bia_chat.py` (novo, 58 testes coletados) e `bia_dubles.py`.

**Frontend: só `src/features/bia/`**
- `api.ts` e `tipos.ts` foram reescritos.
- `useBia.ts` foi refeito: fluxo SSE com recaída para sondagem, notas locais, trava síncrona contra envio duplo.
- Novos:
  - hooks `useAnexos.ts` e `useComandos.ts`, e o mapa de ícones `icones.ts`;
  - `componentes/`: `Compositor`, `PaletaDeComandos`, `FilaDeAnexos`, `Historico`, `Markdown` e `Conversas`.
- `BiaWidget.tsx` é o novo shell. `BiaNoLayout.tsx` agora apaga os rascunhos no logout.
- Testes: `__tests__/bia-widget.test.tsx` foi reescrito (43 testes) e `bia-sem-hermes-no-bundle.test.ts` foi estendido (fetch e XHR só vão para `${BASE}/api/agent/`).

**Ferramentas e documentação**
- `tools/bia-harness/` (bancada visual com API falsa e `capturar.py`).
- `scripts/bia_gerar_catalogo_comandos.py`.
- `docs/bia-hermes/`:
  - `ANEXOS-E-STREAMING.md` e `CATALOGO-COMANDOS.md` (gerado do código);
  - `CONTRATO-ROTAS.md` e `THREAT-MODEL.md`, com seção nova em cada;
  - `provas/PROVA-CHAT-20261015.md`, `provas/telegram-depois-missao3-20261015.json` e `provas/capturas-20261015/`.

**Arquivos compartilhados: nenhum foi editado.** As propostas estão na seção 5.

## Arquitetura escolhida (resumo)

- **Anexos.**
  - Upload com o corpo cru, autenticado, para disco privado no host do backend.
  - Tipo validado pelos bytes, imagem recodificada sem metadados, SHA-256, cota e retenção de 7 dias.
  - Imagens vão ao Hermes como parte nativa de visão (data URL montada no servidor). Documentos vão como texto extraído, num bloco com nonce, como dado não confiável.
  - **Sem migration nova:** a referência do anexo cabe em `execucao.contexto` (jsonb da v27_01).
- **Streaming.** `/chat/stream` do Hermes → buffer em memória → SSE para o navegador.
  - Passam só deltas. Um evento de ferramenta aborta o turno.
  - O texto final oficial continua sendo o do ledger, depois da auditoria de leitura.
  - Se o SSE cair, o navegador volta a sondar o servidor.
- **Comandos.** O catálogo cobre todos os 82 comandos do registro e as 48 skills, em 5 classes.
  - Rodam só os 7 comandos da web: 6 locais e `/status`, que é só leitura e tem rota tipada.
  - Texto que começa com `/` dá 422.

Detalhes em `ANEXOS-E-STREAMING.md` e `CATALOGO-COMANDOS.md`.

## Testes (por camada)

| Camada | Resultado |
|---|---|
| Backend da Bia (`test_agente_bia*.py`) | **159 passaram**, 4 pulados (laboratório de Postgres, opt-in) |
| Front da Bia (vitest) | **43 passaram**, 1 pulado (bundle, opt-in) |
| Prova de bundle (`VOLC_PROVA_DE_BUNDLE=1`, vite build real) | **10/10** |
| Suíte inteira do front | 8 arquivos com falha, **todas herdadas** (tráfego/Meta/work-road, `useLocation` fora de Router), nenhuma da Bia |
| `tsc -p tsconfig.app.json` | 76 erros, todos herdados do webgo; 0 na Bia |
| eslint em `src/features/bia` e `tools/bia-harness` | 0 erros (só avisos de fast-refresh) |
| gitleaks `321266a8..HEAD` | nenhum vazamento |
| Bancada visual (Playwright) | 375, 768, 1024 e 1440 px, claro e escuro, 10 cenas, mais zoom 200% e movimento reduzido: 0 overflow, contraste ≥ 4,5:1 em tudo, 0 animações com movimento reduzido |

## 5. Patches propostos para arquivos compartilhados (não aplicados)

1. **`backend/requirements.txt`**: falta `pypdf`. Hoje o PDF funciona só porque o pacote está instalado no Python do Mac. Em ambiente limpo, o upload de PDF falha fechado (`pdf_indisponivel`).
   ```diff
   +# Bia: texto de PDF anexado (missão 3). Sem ele, PDF é recusado com pdf_indisponivel.
   +pypdf>=6.0
   ```
   `python-docx==1.2.0` e `Pillow>=11.0` já estão lá.
2. **`backend/requirements-dev.txt`**: os testes geram PDF com `fitz`.
   ```diff
   +PyMuPDF>=1.24   # testes da Bia geram PDF real
   ```
3. **`.env.example` / runbook de implantação do backend**: variável nova e opcional, `BIA_ANEXOS_DIR`. O padrão é `~/.volc-os/bia-anexos`. Em servidor, aponte para um volume privado e persistente, com modo 0700.
4. `Layout.tsx`, `App.tsx`, `main.py` e `package-lock.json` **não precisam de mudança**. O router e o lazy load são os da missão 1, e `react-markdown`/`remark-gfm` já estão no lock.

## Migrations

**Nenhuma** candidata nova, e nada foi aplicado no Supabase oficial nesta missão. O estado continua o da missão 2: v20_01 e v27_01 aplicadas, com recibos em `provas/producao/`.

## Hermes / Telegram

**Nada foi alterado no VPS nesta missão.** Foram só leituras: `state.db` em modo somente leitura, `gateway_state.json`, `config.yaml`, código-fonte.

Comparado com o fim da missão 2:
- o processo é o mesmo (pid `1537673`, sem reinício);
- o `config.yaml` tem o mesmo sha256 do recibo da missão 2;
- as sessões ativas do Telegram continuam com 137 e 90 mensagens;
- nenhuma mensagem nova no Telegram;
- web com 0 ferramentas.

Recibo: `provas/telegram-depois-missao3-20261015.json`.

## Rollback

1. **Desligar sem tirar código.**
   - Para esconder: `VITE_BIA_ENABLED=false` e reiniciar o Vite.
   - Para desligar o servidor: `BIA_ENABLED=0` e reiniciar o FastAPI; `/api/agent/*` passa a dar 404.
2. **Código.** Reverter os commits `3ab33b77`, `7a29a471`, `f6e170b4`, `4213e6e5` e `3213b243`, nessa ordem (ou só o front: `4213e6e5`, `3ab33b77` e a parte front de `7a29a471`). A fundação da missão 2 volta inteira.
3. **Dados.**
   - Para apagar os anexos: `rm -rf "${BIA_ANEXOS_DIR:-$HOME/.volc-os/bia-anexos}"`. São só cópias com 7 dias de vida, e o ledger guarda apenas a referência.
   - Execuções que referenciam anexo apagado continuam legíveis. Reenviar uma delas falharia com `anexo_indisponivel`, e isso nunca acontece sozinho.
4. **Hermes.** Não há o que reverter nesta missão. O rollback da superfície API é o da missão 2: `/root/bia-volc/api_default.py reverter /root/.hermes/backups-bia/20261016-004014`.

## Riscos restantes

- **R9 (decisão do dono).**
  - O `session_search` do agente do Telegram, que tem ferramentas, enxerga sessões `api_server`. O texto de um arquivo de terceiros mandado na web pode voltar numa busca do Telegram.
  - Ao contrário do que se registrou na missão 2 (R3/R7), turnos web **não** disparam revisão automática de memória ou skill. Isso foi verificado no código da v0.18.0.
  - Opções: aceitar (operador único, arquivos próprios); restringir anexos; pedir uma fonte oculta ao Hermes; ou separar o profile (recusado na missão 2).
- **Anexos em disco local do Mac.** Ao implantar o FastAPI fora do Mac, use um volume persistente ou o adapter de Supabase Storage. O Storage exige bucket e política no Supabase oficial e, por isso, um checkpoint explícito.
- **O buffer de streaming é por processo.** Com mais de um worker, o SSE pode cair num processo sem parcial. A tela continua correta, mas sem "digitando". Use 1 worker ou uma afinidade.
- **`/status` depois de reiniciar o backend** não conhece a sessão da conversa até o próximo envio, porque a v27_01 não tem RPC para isso. A tela avisa.
- **Não provado em dispositivo real:** teclado virtual de iOS/Android e leitor de tela.
- **Miniatura no histórico:** se o mesmo arquivo for reanexado e depois removido da fila antes do envio, a miniatura da mensagem antiga mostra "expirada". O texto da conversa não é afetado.

## Delta para Roadmap e curadoria (não aplicado; aplicar uma vez, depois do merge)

| Tarefa | Hoje | Proposto | Prova |
|---|---|---|---|
| P09-T04 "Integrar Bia em modo leitura e sugestão" | todo (no main) / partial (missões 1–2) | **partial**: chat completo provado localmente; falta implantar o FastAPI fora do Mac | `provas/PROVA-CHAT-20261015.md`; 159 + 43 testes; bundle 10/10 |

O grafo não foi regenerado (regra da lane).

## QA humano (5 minutos)

App: **http://localhost:8091** (Vite da worktree; FastAPI em `:8031` e túnel em `:18642` estão no ar).

1. Entre com seu usuário ADMIN e clique em **Bia**, no canto inferior direito.
2. Mande uma mensagem; o texto deve aparecer sendo digitado.
3. Anexe uma imagem pelo clipe, arraste um arquivo ou cole uma imagem. Pergunte sobre ela.
4. Digite `/` e use as setas e o Enter. Experimente um comando bloqueado, como `/model`.
5. Celular: no DevTools, ative o modo dispositivo (375 px). O painel deve ocupar a tela. Pelo telefone, via rede local, a origem é recusada pelo CORS exato, que só aceita `http://localhost:8091`; para testar no aparelho, inclua a origem da rede em `BIA_ALLOWED_ORIGINS` e em `ALLOWED_ORIGINS`.
6. No Telegram, mande uma mensagem à Bia e confira que ela responde normalmente.
