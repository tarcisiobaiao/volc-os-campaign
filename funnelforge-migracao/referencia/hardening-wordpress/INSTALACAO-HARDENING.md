# Instalação do aviso editorial global (MU-plugins)

Arquivos, sempre juntos e sempre com estes nomes, em `wp-content/mu-plugins/`:

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

## 1. Inventário antes de qualquer instalação (somente leitura)

```bash
cd /var/www/creditoup.com.br/wp-content/mu-plugins
ls -la
sha256sum *.php *.css
grep -l "class Creditoup_Compliance_Hardening\|class Volc_Editorial_Notice_Owner" *.php
```

Comparar com os hashes do commit aprovado (`sha256sum` dos três arquivos da branch). Registrar no recibo: nome, tamanho, hash e versão (`Version:` no cabeçalho) de cada arquivo existente.

## 2. Detecção de cópia duplicada

O `grep` acima tem de devolver no máximo **um arquivo por classe**. Se devolver dois:

- as versões 1.2.0/1.1.0 têm guarda `class_exists` na declaração: uma cópia nova a mais não derruba o site (provado: 1 aviso, 0 fatal);
- uma cópia ANTIGA sem guarda (hardening 1.0.0/1.1.0 anterior) que carregue DEPOIS da nova, em ordem alfabética, dá `Cannot declare class` e HTTP 500 no site inteiro, wp-admin inclusive (provado no lab). A guarda do arquivo novo não alcança o arquivo antigo.

Portanto a cópia extra tem de sair ANTES da instalação, movida para fora de `mu-plugins/` (passo 3), nunca deixada com outro nome.

## 3. Instalação / atualização

```bash
TS=$(date +%Y%m%d-%H%M%S)
B=/var/backups/creditoup-hardening/$TS
install -d -m 0750 "$B"
cd /var/www/creditoup.com.br/wp-content/mu-plugins
# backup de tudo que será trocado ou retirado (mesmo nome e cópias extras do inventário)
cp -p creditoup-compliance-hardening.php creditoup-compliance-hardening.css volc-editorial-notice-owner.php "$B"/ 2>/dev/null || true
# cópias extras encontradas no passo 2: mv <arquivo> "$B"/
# troca atômica, no MESMO nome de arquivo
for f in creditoup-compliance-hardening.php creditoup-compliance-hardening.css volc-editorial-notice-owner.php; do
  install -o www-data -g www-data -m 0644 /tmp/ff-hardening/$f "./.$f.novo" && mv -f "./.$f.novo" "./$f"
done
sha256sum creditoup-compliance-hardening.php creditoup-compliance-hardening.css volc-editorial-notice-owner.php
```

Os hashes impressos têm de ser os do commit aprovado. Depois, purge do WP Rocket (como no `README.md`).

## 4. Verificação pós-instalação

1. `php -l` nos dois `.php` (ou `wp eval 'echo "ok";'` sem erro).
2. `curl -s -o /dev/null -w '%{http_code}' https://creditoup.com.br/` = 200, e `https://creditoup.com.br/wp-admin/` responde (302 para login).
3. Para uma LP V1, uma página interna com o prefixo do motor, uma LP V2 e uma página comum:
   `grep -o 'class="creditoup-editorial-disclosure"\|id="volc-editorial-notice"' | wc -l` = **1**.
4. O CSS do aviso responde 200 em `/wp-content/mu-plugins/creditoup-compliance-hardening.css`.
5. Log de erro do PHP sem `Fatal`, `Cannot declare` ou `Cannot redeclare` desde a troca.

Qualquer item falhando: rollback imediato.

## 5. Rollback

```bash
cd /var/www/creditoup.com.br/wp-content/mu-plugins
B=/var/backups/creditoup-hardening/<TS da instalação>
# versão anterior existia: restaura os três a partir do backup, no mesmo nome
for f in creditoup-compliance-hardening.php creditoup-compliance-hardening.css volc-editorial-notice-owner.php; do
  [ -f "$B/$f" ] && install -o www-data -g www-data -m 0644 "$B/$f" "./$f"
done
# não existia: retira os três juntos (nunca só o dono)
# mv creditoup-compliance-hardening.php creditoup-compliance-hardening.css volc-editorial-notice-owner.php "$B"/desinstalado/
```

Purge do WP Rocket e repetir o passo 4. Nenhum dado de post ou opção é alterado por esses arquivos: remover devolve o estado anterior.

## Limites conhecidos

- Um `ob_flush()` de terceiro no meio da página entrega pedaços antes do fim: o aviso global só entra no pedaço final (1.2.0), mas um aviso do motor já enviado num pedaço anterior não pode ser retirado. Nenhum plugin do lab faz isso; conferir no site real no passo 4.
- No Elementor, retirar o aviso do motor deixa o container branco vazio que o envolvia.
