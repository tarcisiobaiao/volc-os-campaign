"""Broker de acesso: 1Password -> AdsPower, dentro da fronteira do Cofre.

P03-T11. Ele mora aqui, e nao em `tools/`, por uma razao de autoridade: o Cofre
e quem sabe QUAL perfil pertence a QUAL ativo e ONDE a credencial esta
registrada. Um broker fora dessa fronteira precisaria de uma segunda copia
dessas respostas — e duas copias divergem.

O que ele NAO e: um cofre. Ele nao guarda segredo, nao le `op://` e nao resolve
endereco nenhum. Ele CONSOME um segredo que o 1Password injetou no processo
(`op run --`) e o usa uma vez, num socket de loopback, para perguntar coisas.

⚠️ Nesta versao ele so PERGUNTA. Abrir perfil, iniciar navegador ou executar
acao de sessao exige um checkpoint de autorizacao que ainda nao foi concedido —
e o catalogo de acoes recusa essas operacoes pelo NOME, para que a recusa seja
"isto precisa de autorizacao" e nao "acao desconhecida".
"""
