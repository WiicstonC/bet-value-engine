# Markets are grouped by sport and ordered from broad/high-coverage to more
# specialized markets. The scanner never requests a market blindly: it first
# asks the provider which markets exist for the event, then intersects with
# this catalog.

FEATURED_MARKETS = {
    "tennis": ["h2h", "spreads", "totals"],
    "football": ["h2h", "spreads", "totals"],
    "nba": ["h2h", "spreads", "totals"],
}

DEEP_MARKETS = {
    "tennis": [
        # The Odds API currently documents limited tennis coverage beyond
        # winner/spreads/totals. These keys are retained for providers that
        # expose tennis player props; unavailable keys are never requested.
        "player_aces",
        "player_double_faults",
        "alternate_spreads",
        "alternate_totals",
    ],
    "football": [
        "alternate_totals_corners",
        "alternate_spreads_corners",
        "corners_1x2",
        "alternate_totals_cards",
        "alternate_spreads_cards",
        "player_to_receive_card",
        "player_to_receive_red_card",
        "player_shots",
        "player_shots_on_target",
        "player_assists",
        "player_goal_scorer_anytime",
        "player_tackles",
        "player_fouls",
        "btts",
        "double_chance",
        "draw_no_bet",
        "alternate_team_totals_corners",
    ],
    "nba": [
        "player_points",
        "player_rebounds",
        "player_assists",
        "player_threes",
        "player_blocks",
        "player_steals",
        "player_turnovers",
        "player_points_rebounds_assists",
        "player_points_rebounds",
        "player_points_assists",
        "player_rebounds_assists",
        "player_points_alternate",
        "player_rebounds_alternate",
        "player_assists_alternate",
        "player_threes_alternate",
        "player_blocks_alternate",
        "player_steals_alternate",
        "player_turnovers_alternate",
    ],
}

# Maximum number of deep markets requested in a single event-odds call.
# One region = one credit per returned unique market. This keeps the free
# quota usable while still allowing the engine to hunt for props.
DEEP_MARKET_LIMIT = {
    "tennis": 3,
    "football": 5,
    "nba": 6,
}


def select_deep_markets(sport: str, available: set[str]) -> list[str]:
    ordered = DEEP_MARKETS.get(sport, [])
    limit = DEEP_MARKET_LIMIT.get(sport, 4)
    return [market for market in ordered if market in available][:limit]
