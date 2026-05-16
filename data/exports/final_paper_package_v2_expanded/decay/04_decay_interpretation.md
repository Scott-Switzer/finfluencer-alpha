# V2 Event-Time Decay Interpretation

## all
- 0_5: mean AR `0.000635`, p `0.619611`
- 6_20: mean AR `0.001187`, p `0.593389`
- 21_63: mean AR `0.043252`, p `0.000000`
- 64_126: mean AR `0.044387`, p `0.000000`
- 127_252: mean AR `0.089330`, p `0.000000`
- 253_504: mean AR `0.104136`, p `0.000000`
- 505_end_of_sample: mean AR `0.100658`, p `0.000000`

## top5
- 0_5: mean AR `0.004406`, p `0.013094`
- 6_20: mean AR `0.011755`, p `0.000030`
- 21_63: mean AR `0.081246`, p `0.000000`
- 64_126: mean AR `0.092228`, p `0.000000`
- 127_252: mean AR `0.135155`, p `0.000000`
- 253_504: mean AR `0.143758`, p `0.000000`
- 505_end_of_sample: mean AR `0.155985`, p `0.000000`

## non_top
- 0_5: mean AR `-0.004715`, p `0.008177`
- 6_20: mean AR `-0.013990`, p `0.000080`
- 21_63: mean AR `-0.012572`, p `0.002870`
- 64_126: mean AR `-0.028580`, p `0.000002`
- 127_252: mean AR `0.011608`, p `0.212040`
- 253_504: mean AR `0.032618`, p `0.119959`
- 505_end_of_sample: mean AR `-0.003357`, p `0.923164`

Reversal rows compare later intervals with the first post-event week. Negative values imply fade; positive values imply drift.

This decomposition separates the first-week attention effect from later drift or reversal. It remains associative because event timing can coincide with momentum and public news.
