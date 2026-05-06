from finfluencer_alpha.creator_taxonomy import assign_creator_taxonomy, load_creator_taxonomy_seed


def test_creator_taxonomy_assignment_from_seed_csv() -> None:
    assert assign_creator_taxonomy("x", "realMeetKevin") == "stock_picker"
    assert assign_creator_taxonomy("x", "unusual_whales") == "news_attention"
    assert assign_creator_taxonomy("youtube", "Ben Felix") == "analytical_control"


def test_creator_taxonomy_seed_loads_x_and_youtube_candidates() -> None:
    records = load_creator_taxonomy_seed()
    platforms = {record.platform for record in records}
    assert {"x", "youtube"} <= platforms
    assert len(records) >= 20
