# Riscos restantes

1. `validate_only` cobre as raízes independentes (campaign e creative); AdSet e
   Ad dependem dos IDs reais dos pais e só podem ser validados degrau a degrau
   numa criação autorizada.
2. A migration de saga foi provada apenas em PostgreSQL descartável; ainda
   precisa de uma janela oficial separada.
3. A ponte provisória usa token no Keychain local; o Cofre produtivo permanece
   pendente.
4. A receita não cobre categorias especiais, Sales/Leads, pixel/custom
   conversion, Advantage+, vídeo, catálogo ou upload de asset.
5. Uma resposta remota após timeout precisa ser reconciliada por leitura antes
   de qualquer nova tentativa; não existe retry automático.
