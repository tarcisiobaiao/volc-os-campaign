# Bia web × cérebro: atalhos "Cérebro" e "Salvar no cérebro"

Pedido de 16/10/2026, a partir de uma conversa com a própria Bia. O Tarcisio escolheu a opção **A + B**. A Bia redige; um executor determinístico grava depois da confirmação. A Bia web continua **sem nenhuma ferramenta**.

## Por que não rodar `/salve` e `/cerebro` direto na web

As duas skills existem no profile `default` (`~/.hermes/skills/note-taking/{salve,cerebro}`) e trabalham com ferramentas do agente:
- `/salve` usa `read_file`, `patch` e `write_file` nos três repositórios. Isso inclui `cerebro-pessoal/SOUL.md`, `IDENTITY.md` e `AGENTS.md`. Depois roda `git diff`.
- `/cerebro` roda `git fetch` e `git pull --ff-only` e executa `cerebro_status.py`.

Rodá-las pela web exigiria ferramentas de arquivo e terminal na superfície `api_server`. A web recebe anexos de terceiros; um conteúdo malicioso poderia levar o agente a reescrever a própria identidade num repositório versionado.

## O que está ligado agora (fase A)

| Atalho | Onde | O que faz |
|---|---|---|
| **Salvar no cérebro** (ícone de disquete; `/salvar`) | compositor | Envia a intenção tipada `rascunho_cerebro`. O **servidor** monta o pedido (`cerebro/dominio.py:pedido_de_rascunho`). A Bia responde com JSON (`destino`, `titulo`, `tipo`, `resumo`, `decisoes`, `aprendizados`, `pendencias`, `hipoteses`, `tags`), e a tela o transforma numa **prévia editável**: cérebro, tipo, título e texto, com o selo "Rascunho — ainda não salvo". |
| **Cérebro** (ícone de cérebro; `/cerebro`) | compositor | Pede o status dos três cérebros, só leitura. |
| `/salve` e `/cerebro` digitados | paleta | `/cerebro` é o comando da web. `/salve` mostra o motivo e aponta para `/salvar`. |

Prova real em 16/10: na conversa de testes, a Bia devolveu o rascunho no formato pedido e a prévia apareceu. "Salvar" e "Cérebro" responderam **503 com o motivo**, porque o executor ainda não está instalado. Nada foi gravado em lugar nenhum.

## O que falta ligar (fase B): checkpoint para a sua autorização

O código está pronto e testado. O executor real roda nos testes contra três repositórios git temporários (`backend/tests/test_agente_bia_cerebro.py`, 17 testes). A **instalação no VPS não foi feita**: ela cria usuário de sistema e chave SSH, e o ambiente pediu a sua autorização explícita.

### O executor (`deploy/cerebro-web/volc_cerebro_web.py`)

- Python só com a biblioteca padrão. Lê **um** JSON no stdin e devolve **um** JSON no stdout.
- `status`: branch, último commit, alterações, capturas web pendentes, quanto está à frente ou atrás de `origin/main` (pelas refs locais) e data da última busca. Usa `git --no-optional-locks` e não escreve nem o índice. Sem fetch, sem pull.
- `gravar`: cria **um** arquivo novo em `<cérebro>/inbox/bia-web/AAAA-MM-DD-HHMM-<slug>.md`, mais o `.meta.yaml` irmão.
  - Segue a convenção de estação de visitante de `cerebro-volc/inbox/_TEMPLATE`: `autor: bia-web`, `fonte: conversa`, `maturidade: draft`, `request_id`, `sha256`, conversa e execução de origem.
  - Abre com `O_CREAT|O_EXCL|O_NOFOLLOW`: nunca sobrescreve. Recusa estação ausente ou link simbólico.
  - Recusa texto com cara de segredo (os mesmos sinais do `/salve`).
  - O mesmo `request_id` devolve o mesmo arquivo.
  - Sem commit e sem push.

### Operações no VPS (`srv1546019`, nada no Hermes)

1. **Usuário de sistema:** `useradd --system --home-dir /var/lib/volc-cerebro-web --create-home --shell /bin/sh volc-cerebro-web` e `passwd -l volc-cerebro-web`.
2. **Executor:** `install -o root -g root -m 0755 volc_cerebro_web.py /usr/local/sbin/volc-cerebro-web`.
3. **Chave dedicada**, gerada no Mac (`~/.ssh/volc_bia_cerebro_ed25519`; a chave privada fica só no Mac). No VPS, `~volc-cerebro-web/.ssh/authorized_keys` recebe:
   `restrict,command="/usr/local/sbin/volc-cerebro-web" ssh-ed25519 AAAA… volc-os-bia-cerebro`.
   O `restrict` desliga pty e todo tipo de forwarding; o `command=` impede qualquer outro comando.
4. **`git status` como outro usuário:** `~volc-cerebro-web/.gitconfig` com `[safe] directory = /root/cerebros/<repo>` para os três.
5. **Estações:** `install -d -o volc-cerebro-web -g volc-cerebro-web -m 0755 /root/cerebros/<repo>/inbox/bia-web` nos três repositórios.
   - `cerebro-volc/inbox/` já existe.
   - `cerebro-arbitragem/inbox/` e `cerebro-pessoal/inbox/` **são novos**.
   - O resto dos repositórios continua `root:root`.
6. **Atravessar `/root`:** `setfacl -m u:volc-cerebro-web:x /root` e `setfacl -m u:volc-cerebro-web:rx /root/cerebros`. Só atravessa e lista; não escreve.
7. **No Mac:** em `backend/.env.local`, `BIA_CEREBRO_SSH_DESTINO=volc-cerebro-web@srv1546019.hstgr.cloud` e `BIA_CEREBRO_SSH_CHAVE=~/.ssh/volc_bia_cerebro_ed25519` (caminho absoluto). Depois, reiniciar o FastAPI.

Não há restart do gateway, mudança no `config.yaml`, no `.env` do Hermes nem no `sshd_config` (o `sshd` não restringe usuários: `AllowUsers` ausente).

### Efeito colateral a decidir

Enquanto uma captura web não for promovida ou commitada, o repositório fica com arquivo **não rastreado**. O `/cerebro` do Telegram trata repositório sujo como "não puxar" e só reporta.

Duas saídas:
- (a) aceitar: o `/salve` do Telegram já deixa o repositório sujo do mesmo jeito;
- (b) colocar `inbox/bia-web/` no `.gitignore` de cada cérebro. Isso mexe no `.gitignore`, que é da curadoria.

**Recomendo (a).**

### Rollback

1. Remover as duas variáveis do `backend/.env.local` e reiniciar o FastAPI. As rotas voltam a responder 503.
2. No VPS:
   - `setfacl -x u:volc-cerebro-web /root/cerebros`
   - `setfacl -x u:volc-cerebro-web /root`
   - `rm /usr/local/sbin/volc-cerebro-web`
   - `userdel --remove volc-cerebro-web`
3. As estações vazias são removidas com `rmdir`, assim como `inbox/` onde ela não existia antes. Capturas já gravadas **ficam**, com dono `root`, para promoção ou descarte manual.

### Prova a fazer depois da instalação

1. Status pela web: os três repositórios aparecem e `.git/index` não muda.
2. Gravar uma captura de teste em `volc`. Conferir arquivo e sidecar no VPS, sha256 igual ao recibo, `git log` inalterado e `SOUL.md` intocado.
3. Repetir com o mesmo `request_id`: tem que devolver o mesmo arquivo.
4. Tentar `ssh volc-cerebro-web@… ls`: o comando forçado ignora e só aceita JSON.
5. Telegram: mesmo PID, sessões intactas.

## Lacunas conhecidas

- **Auditoria no ledger:** o v27_01 só aceita os eventos `contexto_lido` e `reconciliacao_inconclusiva`. O rastro da captura fica no sidecar (`request_id`, execução e conversa de origem, sha256) e no log do backend (caminho e sha256, sem conteúdo). Um evento `captura_cerebro` exigiria uma v27_02, ainda candidata e não escrita.
- **"Sincronizar cérebro" com pull:** fica no Telegram. O atalho web é só leitura, por decisão.
- **"Salvar e sincronizar com o GitHub":** fora de escopo. Exigiria uma autorização explícita separada, como a própria Bia sugeriu.
