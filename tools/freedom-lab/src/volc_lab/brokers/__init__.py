"""Brokers de capacidade: cada um entrega a um agente só o que ele precisa.

O agente recebe resultado e recibo sanitizado (IDs mascarados, hash de payload,
sem token). GTM/GA4 recebem só access token reduzido a readonly. Google Ads usa
o google-ads.yaml de escopo cheio: ali a barreira é o caminho de código (sem
mutar/destravar) mais a trava de dois fatores de volc_ads.gads.modo.
Os brokers são bibliotecas no processo do agente, não fronteira de processo.
"""
