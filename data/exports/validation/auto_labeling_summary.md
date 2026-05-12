# Automated Event Labeling Summary

- Source file: `data/exports/validation/event_validation_sample.csv`
- Auto-labeled output: `data/exports/validation/event_validation_sample_auto_labeled.csv`
- Total rows: 524
- Rows auto-labeled yes/no/unclear: 177 / 281 / 66
- Rows labeled by rules: 524
- Rows labeled by LLM: 0
- Rows needing review: 111
- Average confidence: 0.765

## Confidence Distribution

- 0.00-0.49: 66
- 0.50-0.74: 45
- 0.75-0.89: 340
- 0.90-1.00: 73

## Top False-Positive Reasons

- news_or_business_context_without_creator_recommendation: 119
- third_party_attribution_not_creator_recommendation: 110
- historical_or_retrospective_context: 33
- macro_or_index_commentary_without_tradeable_recommendation: 19

## High-Confidence Yes Examples

- 91 | Kenan Grace | AMZN | confidence=0.93 | revenue for the company. So I say that to say this, this is a hidden play. And that's why I'm buying Amazon stock. Now, you thought the things with the trading and the oil was getting weird. I got something els
- 92 | Kenan Grace | AMZN | confidence=0.93 | revenue for the company. So I say that to say this, this is a hidden play. And that's why I'm buying Amazon stock. Now, you thought the things with the trading and the oil was getting weird. I got something els
- 42 | Kenan Grace | META | confidence=0.93 | and I bought it at 539, family, guess what? I told everybody back here on March 27th that I'm buying heavy, right? I'm buying heavy. I bought like $50,000 worth of it. But I'm telling you where and exactly when
- 299 | Financial Education | NFLX | confidence=0.93 | thinking about buying Netflix stock you're like what am I buying here before it was easy I'm buying Netflix now it's like okay I'm going to get all these different properties maybe maybe not some people might
- 516 | Ticker Symbol: YOU | NVDA | confidence=0.93 | re AI revolution, but not in the way most investors think, and of course, which AI stocks I'm buying as a result. There's a ton to talk about. So, let's start with the story that's on everybody's mind. About a

## High-Confidence No Examples

- 430 | Financial Education | AMD | confidence=0.89 | my other stocks that are paying fortunes of money to AMD over the next several years like Meta and a and Amazon and Google that are going to be buying so many dang GPUs and CPUs from AMD it's not even funny. and then the open AIS and Anthro
- 432 | Ale's World of Stocks | NVDA | confidence=0.89 | se unfortunately. Uh, but we also have a ton of individual stock news to cover, including Tesla selling much fewer vehicles than expected. We've got Nvidia buying brand new stock into another AI company. We've got Nike's horrible earnings t
- 431 | Ale's World of Stocks | TSLA | confidence=0.89 | se unfortunately. Uh, but we also have a ton of individual stock news to cover, including Tesla selling much fewer vehicles than expected. We've got Nvidia buying brand new stock into another AI company. We've got Nike's horrible earnings t
- 520 | Best of Us Investors | AMZN | confidence=0.89 | it. Uh, and why am I not buying Broadcom? Well, you you and I know that uh Meta, Google, Microsoft, and Amazon are spending some of their money with Broadcom for the purpose of buying a chip that costs less than Jensen's GPUs because they d
- 73 | Everything Money | MSFT | confidence=0.89 | story. Think about the numbers. What does the future hold? Because at the end of the day, Microsoft's selling for $400 a share. If the stock analyzer tool comes out and says it's worth a dollar per share, are you going

## Examples Needing Review

- 32 | CNBC Television | AAPL | confidence=0.35 | we made a commitment uh to essentially move 10% of the resources of Berkshire Hathaway. uh we turned it over to another uh person who was not that well known at the time. And we did that uh by spending uh roughly $35 billion uh buying uh st
- 523 | Financial Education | SOFI | confidence=0.35 | regards to platform accounts. Right from 160 million down to 158 million, then down to 128 million. They just actually reversed that and grew to 133 million. So, I think that something worth paying attention to maybe on top of that insanely
- 106 | Kenan Grace | AAPL | confidence=0.35 | here. This red line, 200 day moving average line. And it's on an uptrend and it still is. We just got a new CEO and we bounced off of this line two times. One here and one here. So this is our 250. Again, if we come back down to 250, you sh
- 144 | Meet Kevin | TSLA | confidence=0.35 | his personal vendetta against Sam Alman. But what happens next? Well, this tells you how bad the bailin is. Not only do we have a hundred billion dollars potentially getting raised to bail in OpenAI where existing investors are throwing in
- 149 | Meet Kevin | AAPL | confidence=0.35 | employment. >> What about if we take all that as as as fact and and we don't see uh you know at the end of the day as many job losses as as some are are projecting. What about the so-called brain drain? the the fact that our our lives are g

## Research Note

These auto labels are generated by an automated deterministic/optional-LLM workflow. The final paper should describe them transparently as automated and, when LLMs are enabled, model-assisted labels. Low-confidence and unclear rows are separated into a review queue rather than treated as validated ground truth.
