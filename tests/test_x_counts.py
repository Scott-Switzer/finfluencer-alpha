from finfluencer_alpha.x_counts import parse_counts_response


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
