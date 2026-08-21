from app.engine.market_catalog import select_deep_markets


def test_select_deep_markets_respects_priority_and_limit():
    available = {
        "player_assists",
        "player_points",
        "player_threes",
        "player_rebounds",
        "player_steals",
        "player_blocks",
        "player_turnovers",
    }

    selected = select_deep_markets("nba", available)

    assert selected == [
        "player_points",
        "player_rebounds",
        "player_assists",
        "player_threes",
        "player_blocks",
        "player_steals",
    ]


def test_unknown_markets_are_ignored():
    assert select_deep_markets("football", {"market_that_does_not_exist"}) == []
