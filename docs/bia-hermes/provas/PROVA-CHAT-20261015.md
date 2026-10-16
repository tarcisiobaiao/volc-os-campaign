# Prova real do chat da Bia (missão 3) — 15/10/2026

Topologia, a mesma da missão 2: frontend da worktree (Vite `:8091`) → FastAPI da worktree (`:8031`) → túnel SSH (`127.0.0.1:18642` → VPS `127.0.0.1:8642`) → Hermes v0.18.0, profile `default`, superfície `api_server` com **zero** toolsets. Ledger no Supabase oficial (`agente_bia`, v27_01, já aplicada; **nenhuma migration nova nesta missão**). Operador: Tarcisio (ADMIN), logado no próprio navegador, numa aba separada da aba dele.

## Provas 1–12

| # | Prova | Como | Resultado |
|---|---|---|---|
| 1 | Mensagem simples | "Responda em uma lista de 3 itens curtos…" | fila → "Digitando…" com deltas reais → resposta em Markdown (lista numerada). **OK** |
| 2 | Foto real | wallpaper do macOS (suculentas) convertido para JPEG 1400 px; "Descreva esta foto…" | "suculentas de folhas longas e pontiagudas, iluminadas em tons dominantes de vermelho e rosa… fundo preto" — correto. Miniatura servida pelo stream autenticado. **OK** |
| 3 | PDF + TXT reais | `relatorio-teste.pdf` + `notas-reuniao.txt` | "Meta de CPA: R$ 18,20. Palavra-chave secreta: girassol. Código de conferência: TUCANO-7." — os três fatos, de dois arquivos. **OK** |
| 4 | Texto + dois (três) anexos | DOCX + CSV + WebP numa mensagem | "JABUTICABA. Maior CPA: Cactos (31,75). Cores: verde e amarelo." **OK** |
| 5 | Comando seguro | `/status` | nota "/status · somente leitura": mensagens, falhas, "Bia (Hermes) no ar · v0.18.0"; `POST /api/agent/comandos/status` 200; nada enviado à Bia. **OK** |
| 6 | Comando bloqueado | `/compress` | nota com o motivo ("Reescreve o histórico da sessão com outro modelo; fora da V1. Nada foi enviado à Bia."); nenhuma chamada a `/messages`. **OK** |
| 7 | Reload no processamento | recarregar a página com a mensagem "na fila" | a conversa voltou pelo id salvo, a resposta apareceu **uma** vez, nenhum POST novo. **OK** |
| 8 | Falha de rede sem duplicar | túnel SSH derrubado (`kill`) 7 s depois do envio de uma resposta longa | tela: **"Resultado incerto … nada será reenviado automaticamente"**, envio bloqueado na conversa. Túnel religado → "Verificar resposta" (reconciliação por leitura) recuperou a resposta que o Hermes concluiu. No `state.db`: **1** mensagem do operador, **1** resposta, **0** no Telegram. **OK** |
| 9 | Nova conversa não contamina | conversa nova: "Nesta conversa, eu já te enviei algum arquivo ou código de conferência?" | "Não." **OK** |
| 10 | Telegram antes/depois | `telegram-depois-missao3-20261015.json` | mesmo processo (pid 1537673, sem reinício), `connected`; `config.yaml` com o MESMO sha256 do recibo da missão 2; sessões ativas do Telegram com 137 e 90 mensagens (iguais à linha de base); 0 mensagens novas no Telegram; 0 marcadores VOLC exatos em sessões do Telegram; 28 mensagens novas, todas `api_server`, 0 com ferramenta; `platform_toolsets.api_server: []`. **OK** |
| 11 | Varredura de segredos | `gitleaks detect --log-opts 321266a8..HEAD` | "no leaks found". **OK** |
| 12 | Bundle sem chave/URL privada/sessão | `VOLC_PROVA_DE_BUNDLE=1 vitest` (vite build real com a Bia ligada + varredura) | 10/10: nenhuma marca do Hermes (rota, porta, chave, base, host da VPS, `volc_<hex32>`, cabeçalho de sessão). **OK** |

Extra, depois das correções da revisão de segurança (backend reiniciado com `7a29a471`):
- `falso.png` (bytes `MZ…`) → servidor recusou: **"Arquivo recusado: executável Windows."**; sem botão de repetir (4xx), só remover.
- Imagem sintética com texto → "Está escrito "VOLC 42". O retângulo é azul e o círculo é laranja." correto.

## Capturas

Bancada visual (`tools/bia-harness`, API falsa, Playwright) em 375×812, 768×1024, 1024×768, 1440×900, claro e escuro, 10 cenas cada (vazio, longa, fila, preparando, digitando, incerta, erro, upload, paleta, conversas) + zoom 200% + movimento reduzido. Seleção em `capturas-20261015/`; medições em `capturas-20261015/medicoes.json`:

- overflow horizontal de página/painel: **0** em todas as combinações (inclusive 640 px = zoom 200% de 1280);
- contraste de texto dentro do painel: **todos ≥ 4,5:1** (claro e escuro);
- alvos < 44 px no celular: só o link inline dentro de parágrafo (exceção de alvo inline do WCAG 2.5.8);
- movimento reduzido: **0** animações ativas.

Captura real: `capturas-20261015/real-1496-docx-csv-webp.jpg` (prova 4).

## O que não foi provado aqui

- Teclado virtual de celular real (iOS/Android): o painel usa `visualViewport` e `100dvh`, provado só em viewport emulado.
- Leitor de tela real (VoiceOver/NVDA): papéis, nomes e regiões vivas estão nos testes; a escuta humana não foi feita.
- Mensagem do operador no Telegram depois da missão: o estado `connected` e as contagens estão provados; a conferência humana fecha.
