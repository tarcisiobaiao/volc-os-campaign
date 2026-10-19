# Bia web: anexos, streaming e estados

Decisões da missão 3 (15/10/2026). Delta mínimo sobre a fundação aprovada: **nenhuma migration nova**, nenhuma mudança no Hermes, nenhum toolset.

## 1. O que o Hermes v0.18.0 aceita de verdade (medido)

| Entrada no `POST /api/sessions/{id}/chat` | Resultado |
|---|---|
| `input` string | aceito |
| `input` lista de partes `{type:"text"}` | aceito |
| parte `{type:"image_url", image_url:{url:"data:image/…;base64,…"}}` | aceito; o modelo do profile `default` **vê** a imagem (prova real abaixo) |
| parte `input_file` / documento nativo | **recusado** pelo api_server |
| URL remota de imagem | não usamos: o servidor nunca passa URL arbitrária ao Hermes |

Consequência: imagens vão como **parte nativa de visão** (data URL montada no servidor a partir do arquivo saneado); documentos vão como **texto extraído no servidor**, dentro de bloco delimitado como dado não confiável.

## 2. Matriz de formatos

| Formato | Limite | Tratamento | Estado |
|---|---|---|---|
| PNG | 3 MB, 40 Mpx, lado ≤ 8000 | recodificado (sem EXIF/ICC), lado maior ≤ 2048 | **provado real** (foto descrita corretamente) |
| JPEG | 3 MB, idem | idem; orientação EXIF aplicada antes de descartar | **provado real** (foto real e "VOLC 42" lido) |
| WebP | 3 MB, idem | idem | **provado real** (cores verde/amarelo) |
| PDF | 10 MB, ≤ 300 páginas | texto por página (`pypdf`), até 20 000 caracteres | **provado real** (meta de CPA e palavra-chave lidas) |
| TXT / MD | 2 MB | UTF-8, recaída cp1252, controle removido | **provado real** (código TUCANO-7) |
| CSV | 2 MB | linhas como `a \| b \| c` | **provado real** (maior CPA = Cactos) |
| DOCX | 10 MB | parágrafos + tabelas (`python-docx`); ≤ 2000 entradas, ≤ 40 MB descompactado | **provado real** (JABUTICABA) |
| PDF digitalizado (sem texto) | — | **recusado** `pdf_sem_texto` (V1 sem OCR) | recusado |
| PDF com senha | — | **recusado** `pdf_protegido` | recusado |
| DOCX com macro/objeto embutido | — | **recusado** `docx_com_conteudo_ativo` | recusado |
| Executável, script, HTML, SVG, ZIP genérico, polyglot | — | **recusado** pelos bytes (`tipo_proibido`/`tipo_divergente`) | recusado (real: "executável Windows" disfarçado de `.png`) |
| Qualquer outro | — | recusado no navegador antes de subir e no servidor | recusado |

Por mensagem: até 4 anexos, até 3 imagens e 6 MB de imagem, até 40 000 caracteres de documentos.

## 3. Armazenamento e segurança

- **Onde:** disco privado do host do backend, `BIA_ANEXOS_DIR` (padrão `~/.volc-os/bia-anexos`), pasta por dono = `sha256(user_id)[:24]`, modo 0700, arquivos 0600, gravação atômica (tmp + rename), metadado gravado por último (sem `.json` o anexo não existe).
- **Por que não Supabase Storage agora:** exigiria bucket/política nova no Supabase oficial (checkpoint explícito). O código fala com uma porta (`Armazem`); trocar por Storage é um adapter novo. Ver `HANDOFF.md`.
- **Tipo pelos bytes**, conferido contra extensão e Content-Type; nome só para exibição (sem caminho, sem controle, sem colchetes, sem marcas bidi, NFC, ≤ 120).
- **SHA-256** do original (deduplicação) e do saneado (integridade no envio).
- **Cota por usuário:** 40 anexos / 80 MB ativos. **Retenção:** 7 dias (reenvio do mesmo arquivo renova). Limpeza na escrita, sob trava por dono (thread + `flock`); temporário/órfão só é varrido depois de 10 min.
- **Dono:** toda leitura passa por `Armazem.obter(dono, id)`; de outro usuário → 404.
- **Entrega ao navegador:** stream autenticado (`GET /anexos/{id}` com o bearer da sessão), `nosniff`, `no-store`, `CSP: sandbox`; o front faz `blob:` local e revoga ao desmontar.
- **Prompt:** documentos e nomes de imagem em blocos `[ANEXOS VOLC <nonce>] … [FIM DOS ANEXOS VOLC <nonce>]` e `[IMAGENS ANEXADAS <nonce>] …`, nonce aleatório por mensagem; linhas do arquivo que imitam a moldura são neutralizadas (`(citação do arquivo) …`). Nunca no system prompt.
- **Log:** só tipo e tamanho. Nunca conteúdo, nunca nome de arquivo.

## 4. Streaming

```
navegador ──GET /runs/{id}/fluxo (SSE, bearer)──▶ FastAPI ──POST /api/sessions/{s}/chat/stream──▶ Hermes
                ▲                                    │
                └──── estado / parcial / aviso ◀─────┴─ BufferDeFluxo (memória do processo)
```

- O turno roda em background no FastAPI (como antes). Com `ao_delta`, o adapter usa `/chat/stream` e repassa **só** `assistant.delta`. `tool.started/completed/failed` ou `tool.progress` que não seja `_thinking` → turno abortado (`hermes_usou_ferramenta`), conexão fechada. `error` → `uncertain` (`hermes_erro_no_turno`): o Hermes pode ter gravado parte do turno, então nada é repetido. Sem `assistant.completed` → `uncertain`.
- O parcial é filtrado com o mesmo filtro da resposta final, sem `<think>`, e retém os últimos 64 caracteres até o fim (um segredo não vaza pelo prefixo).
- O texto final oficial continua sendo o do ledger, depois da auditoria de leitura (`verificar_sem_ferramentas`). O parcial é descartável: reinício do backend perde o parcial e a tela volta ao estado do ledger.
- Desconectar o navegador não cancela nem repete o turno. Reassinar é leitura.
- Se o fluxo SSE falhar, o front cai para sondagem (`GET /runs/{id}` a cada 1,5 s). Sem deltas reais, a tela diz "preparando a resposta", nunca "digitando".

## 5. Estados na tela

| Estado | Texto | Onde |
|---|---|---|
| enviando (POST em voo) | botão com ícone girando, `aria-label="Enviando…"`; texto continua no campo | compositor |
| `queued` | "Mensagem na fila" + pontos | sob a mensagem do operador e no cabeçalho |
| `running` sem delta | "Bia está preparando a resposta…" | no lugar da resposta |
| `running` com delta | texto parcial + "Bia está digitando…" (`aria-busy`) | no lugar da resposta |
| `succeeded` | Markdown sanitizado + Copiar | resposta |
| `failed` | causa pública + próximo passo + "Reaproveitar o texto" (só preenche o campo) | resposta |
| `uncertain` | "Resultado incerto… nada será reenviado automaticamente" + Verificar resposta / Nova conversa; envio bloqueado na conversa | resposta + compositor |
| upload | barra de progresso por arquivo (`role=progressbar`), separada do estado da mensagem | fila de anexos |

Movimento: só opacidade (`animate-pulse` nos pontos) e transform; parados com `prefers-reduced-motion` (medido: 0 animações ativas). Esqueleto só depois de 300 ms.
