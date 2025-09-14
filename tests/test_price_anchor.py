import re
from meu_app.services.generative_sales_layer import PricingPolicy, price_anchor, OAB_MIN_FEES


def test_price_anchor_respects_oab_minima():
    policy = PricingPolicy(tiers={
        'consulta': 'R$100',
        'medida_extrajudicial': 'R$200',
        'acao_judicial': 'R$1000'
    })
    anchors = price_anchor(policy)
    assert 'Consulta R$%d' % OAB_MIN_FEES['consulta'] in anchors[0]
    assert 'Medida extrajudicial R$%d' % OAB_MIN_FEES['medida_extrajudicial'] in anchors[1]
    assert 'Ação judicial R$%d' % OAB_MIN_FEES['acao_judicial'] in anchors[2]