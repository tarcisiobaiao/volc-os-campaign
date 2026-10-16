"""VOLC Data Intelligence Lab — bancada hermética (replay, estatística, swarm, surrogate).

Fronteira: nenhum módulo deste pacote faz I/O de rede, lê segredo, acessa Supabase,
Google Ads, n8n ou qualquer API produtiva. Entradas são fixtures/snapshots locais;
saídas são relatórios e propostas em modo shadow, nunca mutações.
"""

__version__ = "0.1.0"
