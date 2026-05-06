from finfluencer_alpha.config import Settings
from finfluencer_alpha.x_collect import collect_x_quote_tweets, search_x_full_archive_posts


def test_full_archive_collection_does_not_call_api_below_page_minimum(monkeypatch) -> None:
    monkeypatch.setattr(
        "finfluencer_alpha.x_collect.get_settings",
        lambda: Settings(x_bearer_token="fake-token"),
    )

    def fail_request(*args, **kwargs):
        raise AssertionError("request_json should not be called below page minimum")

    monkeypatch.setattr("finfluencer_alpha.x_collect.request_json", fail_request)
    assert search_x_full_archive_posts("from:test buy lang:en -is:retweet", None, None, 9) == 0
    assert collect_x_quote_tweets("123", 9) == 0
