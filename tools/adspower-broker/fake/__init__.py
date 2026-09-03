"""Duplês do AdsPower — só para prova hermética, nunca importados em produção.

Este pacote é o oposto do `broker`: ele existe para que o broker possa ser
exercido de ponta a ponta sem tocar num AdsPower real, num perfil real ou num
navegador real. Nada aqui deve ser importado por `broker/*`, e o teste
`test_adspower_broker_hermetico.py` prova essa direção da dependência.
"""
