# CreditUp: acesso SSH operacional

## Uso local

Na raiz do repositorio:

```bash
bash scripts/creditoup-ssh-check.sh
```

O helper usa o Python de `backend/.venv`, o `Settings` existente e somente as
sete referencias `CREDITOUP_*` do `.env.local` da raiz. Variaveis do processo
prevalecem. Nao faz `source`, expansao de shell ou dump de configuracao.
Isso nao altera a precedencia de ambiente do backend iniciado em outro diretorio.

`.env.example` documenta os nomes com valores ficticios. `.env.local` deve continuar
ignorado e nao versionado. A chave permanece fora do repositorio: o helper verifica
existencia e permissao 400/600, sem ler seu conteudo. O cliente OpenSSH usa a chave
normalmente para autenticar; o script nao a exporta nem a copia.

## Contrato do verificador

- Resolve `CREDITOUP_SSH_ALIAS` e confere host, usuario e identidade esperados.
- Exige host previamente conhecido; nao aceita automaticamente outra host key.
- Usa BatchMode, ConnectTimeout=10 e limite local de 45 segundos.
- Desliga forwarding, comandos locais e reutilizacao de conexoes multiplexadas.
- Consulta apenas hostname, usuario e existencia da raiz/config do WordPress.
- Se WP-CLI existir, consulta sua versao, `home`, `siteurl` e versao do WordPress.
- Nao aceita argumentos, comandos livres, atualizacoes ou outras options.
- Filtra a saida; erros remotos e valores inesperados nao sao reproduzidos.

O hostname esperado neste helper de um unico site e `wp-arbitragem-volc-01`.
`home` e `siteurl` devem corresponder ao dominio configurado; divergencias exigem
inspecao humana, nunca correcao automatica.

As consultas WP-CLI usam `--skip-plugins --skip-themes`. MU-plugins e drop-ins
ainda podem ser carregados pelo WordPress. Como em qualquer login/consulta,
logs de acesso e efeitos incidentais de runtime podem ocorrer; nao ha comandos
de mutacao de conteudo, configuracao, banco ou arquivos neste helper.

## Tarefas futuras

O acesso interativo preferencial informado pelo operador e `ssh hetzner-wp-volc`.
Ele concede root, nao uma permissao read-only: o limite de leitura e do helper,
nao da credencial. Escritas futuras precisam de escopo e autorizacao explicitos,
backup, verificacao e rollback. Nao abra nem imprima wp-config.php para obter
credenciais. Nao use este acesso para manutencao automatica.

## Provas locais

```bash
backend/.venv/bin/python -m unittest discover -s scripts/tests -p 'test_creditoup_ssh_check.py'
git check-ignore -v .env.local
```

Os testes usam arquivos vazios como identidades e SSH simulado, sem rede.
