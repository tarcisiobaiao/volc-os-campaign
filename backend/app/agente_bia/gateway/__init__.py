"""VOLC Agent Gateway — capacidades de negócio tipadas, chamadas pelo servidor.

Não confundir com o gateway do Hermes (o processo que roda o agente). Este é o
lado VOLC: cada capacidade tem entrada e saída Pydantic estritas, papel mínimo,
efeito declarado e implementação que reusa os serviços canônicos.

Na V1 o catálogo só aceita `efeito="leitura"` (`catalogo.py` recusa o resto no
registro) e a única capacidade é `volc_get_campaign_context`. Quem a invoca é o
backend, em nome do usuário autenticado: o Hermes NÃO recebe ferramenta, MCP
ou credencial — recebe o resultado como dado delimitado dentro da mensagem.
"""
