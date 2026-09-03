"""Implementacoes da porta. Nenhuma delas e importada por `__init__` do pacote:
o adaptador real puxa `httpx` e o fake puxa o real, e nenhum dos dois precisa
existir para o dominio ser importavel.
"""
