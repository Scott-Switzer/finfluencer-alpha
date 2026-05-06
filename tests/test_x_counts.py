from finfluencer_alpha.x_counts import X_COUNTS_ALL_URL, parse_counts_response, x_stockpick_query


def test_x_counts_response_parsing_fixture() -> None:
    payload = {
        "data": [
            {
                "start": "2020-01-01T00:00:00.000Z",
                "end": "2020-02-01T00:00:00.000Z",
                "tweet_count": 12,
            },
            {
                "start": "2020-02-01T00:00:00.000Z",
                "end": "2020-03-01T00:00:00.000Z",
                "tweet_count": 8,
            },
        ],
        "meta": {"total_tweet_count": 20},
    }
    total, periods = parse_counts_response(payload)
    assert total == 20
    assert [period["tweet_count"] for period in periods] == [12, 8]


def test_x_counts_uses_full_archive_counts_endpoint() -> None:
    assert X_COUNTS_ALL_URL == "https://api.x.com/2/tweets/counts/all"


def test_x_stockpick_query_is_filtered_not_full_timeline() -> None:
    query = x_stockpick_query("realMeetKevin")
    assert "from:realMeetKevin" in query
    assert "lang:en" in query
    assert "-is:retweet" in query
    assert "has:cashtags" in query
    assert "buy" in query
    assert query != "from:realMeetKevin lang:en -is:retweet"
