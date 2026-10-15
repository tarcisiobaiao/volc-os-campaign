# Instalação do aviso editorial global (MU-plugins)

Arquivos, sempre juntos e sempre com estes nomes, em `wp-content/mu-plugins/`:

**Nunca copiar `validate-*.php` para `mu-plugins/`**: são testes isolados que redeclaram funções do WordPress (`add_filter`, `add_action`…) e dão fatal no site inteiro. Rodam fora do WordPress (`php validate-notice-owner.php`) ou via `wpcli eval-file /tmp/<arquivo>.php` (função `wpcli` abaixo), a partir de `/tmp`.

| Arquivo | Versão | Papel |
|---|---|---|
| `creditoup-compliance-hardening.php` | 1.2.0 | imprime o aviso global no `wp_footer` (ou antes de `</body>` se o template não chamar `wp_footer`) e só então emite `volc_editorial_disclosure_rendered`; fecha comentários |
| `creditoup-compliance-hardening.css` | 1.2.0 | estilo do aviso global; sem ele, nenhum `<link>` é emitido |
| `volc-editorial-notice-owner.php` | 1.1.0 | no fim da resposta, se o sinal existiu, retira o aviso CANÔNICO do motor; sem o sinal, não toca em nada |

Nada aqui foi instalado no Creditoup. Instalar exige aprovação explícita do Tarcisio com o SHA.

## Regra de exatamente um aviso

Provado no WordPress descartável (`FF-corretiva-evidencias/cenarios-aviso.out`), LP V1, página interna com o prefixo do motor, LP V2 e página comum, com e sem `wp_footer`:

| Instalado | LP V1 / interna | LP V2 / comum |
|---|---|---|
| hardening 1.2.0 + dono 1.1.0 | 1 (global) | 1 (global) |
| só o dono 1.1.0 | 1 (motor) | 0 do plugin (a LP V2 conta com o rodapé institucional do tema, por configuração do motor) |
| só o hardening 1.2.0 | **2** | 1 |
| nenhum | 1 (motor) | 0 do plugin |

Por isso: **instalar e remover os três arquivos juntos**. O hardening sem o dono duplica o aviso.
A combinação anterior (hardening 1.1.0 de 42f04aed + dono 1.0.0) também dava 2: o dono decidia durante o conteúdo, antes de o sinal existir.

## WP-CLI como root ou como outro usuário

Todo comando `wp` deste documento passa por `wpcli`, que acrescenta `--allow-root` só quando o shell é root (`id -u` = 0); sem isso, o WP-CLI recusa rodar como root.

```bash
wpcli() {
  if [ "$(id -u)" -eq 0 ]; then
    wp --allow-root --path=/var/www/creditoup.com.br "$@"
  else
    wp --path=/var/www/creditoup.com.br "$@"
  fi
}
# exemplos: wpcli eval 'echo "ok";'   |   wpcli eval-file /tmp/validate-published-content.php
```

## 1. Inventário antes de qualquer instalação (somente leitura)

```bash
set -euo pipefail
WP=/var/www/creditoup.com.br
cd "$WP/wp-content/mu-plugins"
ls -la
sha256sum -- *.php *.css
grep -l -E "class (Creditoup_Compliance_Hardening|Volc_Editorial_Notice_Owner)" -- *.php || echo "nenhuma classe encontrada"
```

Comparar com os hashes do commit aprovado (`sha256sum` dos três arquivos da branch). Registrar no recibo: nome, tamanho, hash e versão (`Version:` no cabeçalho) de cada arquivo existente, e escolher as 4 URLs de referência do passo 5 (uma LP V1, uma página interna com o prefixo do motor, uma LP V2, uma página comum).

## 2. Pré-condição obrigatória: buffers de terceiros (aborta se houver achado)

O dono do aviso decide num buffer aberto em `template_redirect`. Código que fecha **todos** os buffers durante a página tira esse buffer antes do fim, e a LP V1 fica com 2 avisos (provado no simulador PHP do revisor sobre cadf0d73; não reproduzido no WordPress descartável). Antes de instalar:

```bash
cd /var/www/creditoup.com.br
grep -rnE "ob_end_flush|ob_end_clean|ob_get_clean|ob_get_flush|while.*ob_get_level" \
  /var/www/creditoup.com.br/wp-content/plugins /var/www/creditoup.com.br/wp-content/themes \
  /var/www/creditoup.com.br/wp-content/mu-plugins || echo "nenhuma ocorrência"
```

**Qualquer ocorrência em código que rode numa requisição de página pública ABORTA a instalação até análise** (qual plugin, em que hook, se fecha o buffer de outros). Ocorrência descartada só com justificativa escrita no recibo (ex.: código só de admin, CLI ou download). Sem essa análise, não seguir para o passo 4.

## 3. Detecção de cópia duplicada

O `grep` do passo 1 tem de devolver no máximo **um arquivo por classe**. Se devolver dois:

- as versões 1.2.0/1.1.0 têm guarda `class_exists` na declaração: uma cópia nova a mais não derruba o site (provado no WordPress descartável: 1 aviso, 0 fatal);
- uma cópia ANTIGA sem guarda (hardening 1.0.0/1.1.0 anterior) que carregue DEPOIS da nova, em ordem alfabética, dá `Cannot declare class` e HTTP 500 no site inteiro, wp-admin inclusive (provado no WordPress descartável). A guarda do arquivo novo não alcança o arquivo antigo.

Portanto toda cópia extra sai ANTES da instalação, para o backup (passo 4), nunca deixada com outro nome.

## 4. Instalação / atualização

Os três arquivos aprovados ficam em `/tmp/ff-hardening/` (só eles; nunca `validate-*.php`). `EXTRAS` lista as cópias duplicadas achadas no passo 3 (vazio se não houver).

```bash
set -euo pipefail
MU=/var/www/creditoup.com.br/wp-content/mu-plugins
NOMES="creditoup-compliance-hardening.php creditoup-compliance-hardening.css volc-editorial-notice-owner.php"
EXTRAS=""            # ex.: EXTRAS="creditoup-compliance-hardening-antigo.php"
TS=$(date +%Y%m%d-%H%M%S)
B=/var/backups/creditoup-hardening/$TS
install -d -m 0750 "$B/antes" "$B/desinstalado"
cd "$MU"
# backup: só o que existe, sem engolir erro (set -e interrompe se a cópia falhar)
: > "$B/existiam.txt"
for f in $NOMES; do
  if [ -e "$f" ]; then cp -p -- "$f" "$B/antes/$f"; echo "$f" >> "$B/existiam.txt"; fi
done
# nenhum dos três existia: marcador explícito (arquivo vazio é inválido no rollback)
[ -s "$B/existiam.txt" ] || echo "nenhum" > "$B/existiam.txt"
# cópias extras: backup e registro à parte (o rollback NÃO as devolve sozinho)
: > "$B/extras.txt"
for f in $EXTRAS; do cp -p -- "$f" "$B/antes/$f"; echo "$f" >> "$B/extras.txt"; done
# cópias extras saem de mu-plugins (já estão no backup)
for f in $EXTRAS; do mv -- "$f" "$B/desinstalado/$f"; done
# troca atômica, no MESMO nome de arquivo
for f in $NOMES; do
  install -o www-data -g www-data -m 0644 "/tmp/ff-hardening/$f" "./.$f.novo"
  mv -f -- "./.$f.novo" "./$f"
done
sha256sum $NOMES
echo "$B"            # anotar no recibo: é o argumento do rollback
```

Os hashes impressos têm de ser os do commit aprovado. Depois, purge do WP Rocket (como no `README.md`).

## 5. Verificação pós-instalação

```bash
URLS="<URL da LP V1> <URL da página interna com prefixo> <URL da LP V2> <URL da página comum>"
for u in $URLS; do
  n=$(curl -s "$u" | grep -oE 'class="creditoup-editorial-disclosure"|aria-label="Identidade editorial"' | wc -l)
  echo "$u avisos=$n"
done
```

1. `wpcli eval 'echo "ok";'` sem erro (função `wpcli` acima: funciona como root e como outro usuário).
2. `curl -s -o /dev/null -w '%{http_code}' https://creditoup.com.br/` = 200, e `https://creditoup.com.br/wp-admin/` responde (302 para login).
3. Cada uma das 4 URLs com `avisos=1`. O padrão conta o aviso global, o aviso canônico do motor e o aviso curto do V2 (os dois do motor têm `aria-label="Identidade editorial"`).
4. O CSS do aviso responde 200 em `/wp-content/mu-plugins/creditoup-compliance-hardening.css`.
5. Log de erro do PHP sem `Fatal`, `Cannot declare` ou `Cannot redeclare` desde a troca.

Qualquer item falhando: rollback imediato.

## 6. Rollback (estado exato do inventário, sempre os três juntos)

O rollback **valida `existiam.txt` antes de tocar em qualquer arquivo**. Aborta sem alterar nada se o arquivo faltar, estiver vazio, tiver linha fora da allowlist dos três nomes (ou `nenhum`, sozinho), nome repetido, ou se algum nome listado não estiver em `$B/antes/`.

```bash
set -euo pipefail
MU=/var/www/creditoup.com.br/wp-content/mu-plugins
NOMES="creditoup-compliance-hardening.php creditoup-compliance-hardening.css volc-editorial-notice-owner.php"
B=/var/backups/creditoup-hardening/<TS da instalação>      # o diretório anotado no passo 4
L="$B/existiam.txt"
aborta() { echo "ROLLBACK ABORTADO, nada foi alterado: $*" >&2; exit 1; }
# --- validação (somente leitura) ---
[ -d "$B/antes" ] || aborta "sem $B/antes"
[ -f "$L" ] || aborta "sem $L"
[ -s "$L" ] || aborta "$L vazio"
RESTAURAR=""
if [ "$(cat "$L")" = "nenhum" ]; then
  :   # nenhum dos três existia antes: só retirar
else
  while IFS= read -r f || [ -n "$f" ]; do
    case " $NOMES " in *" $f "*) ;; *) aborta "nome fora da allowlist: '$f'";; esac
    case " $RESTAURAR " in *" $f "*) aborta "nome repetido: '$f'";; esac
    [ -f "$B/antes/$f" ] || aborta "backup ausente: $B/antes/$f"
    RESTAURAR="$RESTAURAR $f"
  done < "$L"
  [ -n "$RESTAURAR" ] || aborta "$L sem nomes"
fi
# --- mutação (só depois de validar) ---
install -d -m 0750 "$B/desinstalado"
cd "$MU"
# 1) retira os três instalados (nunca só um: o par misto não foi provado)
for f in $NOMES; do
  if [ -e "$f" ]; then mv -- "$f" "$B/desinstalado/$f.novo"; fi
done
# 2) devolve exatamente os que existiam antes, no mesmo nome
for f in $RESTAURAR; do
  install -o www-data -g www-data -m 0644 "$B/antes/$f" "./$f"
done
ls -la
for f in $RESTAURAR; do sha256sum -- "$f"; done
```

Os hashes têm de bater com os do inventário do passo 1. Purge do WP Rocket e repetir o passo 5 (esperado: o estado anterior). Nenhum dado de post ou opção é alterado por esses arquivos.

Cópias extras (`$B/extras.txt`) não voltam sozinhas: eram duplicatas da mesma classe e uma cópia antiga sem guarda ao lado de outra dá fatal (passo 3). Devolver uma delas é decisão manual, registrada no recibo, depois de conferir que nenhuma outra cópia da classe está em `mu-plugins/`.

## Limites conhecidos

- `ob_flush()` de terceiro no meio da página **funciona**: os buffers continuam abertos, o aviso global entra no pedaço final e o dono decide no fim. Provado no simulador PHP do revisor sobre cadf0d73 (sempre 1 aviso, com flush antes ou depois do conteúdo); não reproduzido no WordPress descartável.
- O caso que falha é um terceiro que **fecha todos os buffers** logo depois do `<head>`: LP V1 com 2 avisos (o global no topo). É a pré-condição do passo 2, que aborta a instalação.
- "Exatamente um aviso" vale para os cenários provados no WordPress descartável (tabela acima). Tema, cache e plugins do site real só se confirmam no passo 5.
- No Elementor, retirar o aviso do motor deixa o container branco vazio que o envolvia.
