# Automated Event Labeling Summary

- Source file: `data/exports/validation/event_validation_sample.csv`
- Auto-labeled output: `data/exports/validation/event_validation_sample_auto_labeled.csv`
- Total rows: 500
- Rows auto-labeled yes/no/unclear: 155 / 272 / 73
- Rows labeled by rules: 500
- Rows labeled by LLM: 0
- Rows needing review: 115
- Average confidence: 0.755

## Confidence Distribution

- 0.00-0.49: 73
- 0.50-0.74: 42
- 0.75-0.89: 334
- 0.90-1.00: 51

## Top False-Positive Reasons

- news_or_business_context_without_creator_recommendation: 117
- third_party_attribution_not_creator_recommendation: 116
- historical_or_retrospective_context: 25
- macro_or_index_commentary_without_tradeable_recommendation: 14

## High-Confidence Yes Examples

- 5 | Kenan Grace | META | confidence=0.93 | and I bought it at 539, family, guess what? I told everybody back here on March 27th that I'm buying heavy, right? I'm buying heavy. I bought like $50,000 worth of it. But I'm telling you where and exactly when
- 9 | The Plain Bagel | DIS | confidence=0.93 | e whether you get into stocks and stuff, like there are fun ways to do that. Like I think we're going to buy him a stock and kind of give him like something like Disney or something like that where he can kind of learn
- 262 | Financial Education | NFLX | confidence=0.93 | thinking about buying Netflix stock you're like what am I buying here before it was easy I'm buying Netflix now it's like okay I'm going to get all these different properties maybe maybe not some people might
- 338 | Tom Nash | NVDA | confidence=0.93 | plausible paths to get to 3 trillion if you add on additional markets so if somebody says I'm buying Nvidia because I think it's cheap it's not my job to argue with them and tell them that it's not cheap I thin
- 479 | Ticker Symbol: YOU | NVDA | confidence=0.93 | re AI revolution, but not in the way most investors think, and of course, which AI stocks I'm buying as a result. There's a ton to talk about. So, let's start with the story that's on everybody's mind. About a

## High-Confidence No Examples

- 3 | The Plain Bagel | NVDA | confidence=0.89 | rategy an individual should look to replicate it's also publicly known at this point that Nvidia has bought these stocks so buying off of that information is not itself going to earn you excess return um and you have to be careful when you
- 27 | Meet Kevin | NVDA | confidence=0.89 | selling their stock because they have no revenue. They're pre-revenue. Carvana relies on insiders selling the stock to buy the debt that Carvana generates when they sell cars. So you're kind of like creating this cy
- 110 | Meet Kevin | TSLA | confidence=0.89 | ey uh to keep funding Grock and that's why you know SpaceX SpaceX invests in um Grock now Tesla uh Elon hinting at selling Tesla shares uh to pay taxes to be fair which is stupid. He needs the money. Uh and then uh you know SpaceX I
- 132 | Ticker Symbol: YOU | TSLA | confidence=0.89 | cording it's still in the top 10 positions of both the S&P 500 and the NASDAQ and in 2023 Tesla manufactured and sold more than half of all electric vehic I Les in the US and there's no doubt that all of these massive achieveme
- 153 | HyperChange | TSLA | confidence=0.89 | till be less than the Ford pickup series and you think about the model y the model 3 when Tesla enters a vehicle category they are out selling every other vehicle in that category dramatically so if you extrapolate that to the Cyber truck t

## Examples Needing Review

- 11 | New Money | AAPL | confidence=0.35 | look at Michael Murray's notice something it's all over the place the only consistent thing there is inconsistency so take it all with a grain of salt but with that said why would Michael Barry seemingly contradict himself in the same 13f f
- 12 | Chicken Genius Singapore | TSLA | confidence=0.35 | listing in HongKong. At least if crap happens, you will have something to fall back on. Else the risk is in my opinion is not worth it. Are you guys investing in any Chinese stocks or intending to buy any Chinese stocks? Let me know which o
- 13 | Meet Kevin | AMD | confidence=0.35 | these chips on debt? That's all it is. Nvidia is like a bank, you know? It's it's like we take $10 and we turn it into a $100 of chip sales by this circular investing. But the only reason that circular investing happens is because people ar
- 17 | The Plain Bagel | AMZN | confidence=0.35 | other things and there's a very easy explanation as to why the promise of high returns with low effort with some of these strategies doesn't hold any water take Drop Shipping for example the basic idea of Drop Shipping is that you build a s
- 24 | HyperChange | TSLA | confidence=0.35 | and that's a small example but I it's B it's like we it's a tool that's what crypto is it's a tool and it's a tool that makes it more frictionless to organize humans around a cause and so I think that it's an incentive system to organize hu

## Research Note

These auto labels are generated by an automated deterministic/optional-LLM workflow. The final paper should describe them transparently as automated and, when LLMs are enabled, model-assisted labels. Low-confidence and unclear rows are separated into a review queue rather than treated as validated ground truth.
