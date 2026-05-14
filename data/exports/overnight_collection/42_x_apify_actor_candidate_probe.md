# X Apify actor candidate tiny probe

Started (UTC): `2026-05-14T23:53:06Z`
Max actors: `5`
Session cap USD: `0.1`

Selected for strict canary: `none`

## Probe rows

- `candidate_1` `api-ninja/x-twitter-advanced-search` perm=`LIMITED_PERMISSIONS` started=0 returned=0 decision=`START_FAILED` reason=`Input is not valid: Field input.numberOfTweets must be >= 20`
- `candidate_2` `happitap/twitter-tweet-scraper` perm=`LIMITED_PERMISSIONS` started=1 returned=0 decision=`STARTED_NO_ROWS` reason=`authorization/schema ok but no rows from tiny probe`
- `candidate_3` `mikolabs/twitter-advanced-search-scraper` perm=`LIMITED_PERMISSIONS` started=0 returned=0 decision=`AUTH_OR_PERMISSION_BLOCKED` reason=`You must rent a paid Actor in order to run it after its free trial has expired. To rent this Actor, go to https://console.apify.com/actors/3pTYcqECWebgIaaJv`
- `candidate_4` `mikolabs/x-twitter-advanced-search-tweet-scraper` perm=`LIMITED_PERMISSIONS` started=0 returned=0 decision=`START_FAILED` reason=`Input is not valid: Field input.numberOfTweets must be >= 20`
- `candidate_5` `novi/twitter-x-api` perm=`LIMITED_PERMISSIONS` started=1 returned=0 decision=`STARTED_NO_ROWS` reason=`authorization/schema ok but no rows from tiny probe`
