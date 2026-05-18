from atlas.intelligence.states.cohorts import cohort_for_stock, sector_cohort_key


def test_cohort_large_cap_by_nifty_100():
    """Stock in Nifty 100 -> large_cap cohort regardless of sector."""
    assert cohort_for_stock(in_nifty_100=True, in_nifty_500=True, sector="IT") == "large_cap"


def test_cohort_mid_cap():
    """Stock in Nifty 500 but not Nifty 100 -> mid_cap."""
    assert cohort_for_stock(in_nifty_100=False, in_nifty_500=True, sector="IT") == "mid_cap"


def test_cohort_small_cap():
    """Stock outside Nifty 500 -> small_cap."""
    assert cohort_for_stock(in_nifty_100=False, in_nifty_500=False, sector="IT") == "small_cap"


def test_sector_cohort_key_lowercase_underscore():
    """Sector name normalized: lowercased, spaces and dashes -> underscore."""
    assert sector_cohort_key("Information Technology") == "sector_information_technology"
    assert sector_cohort_key("Consumer Goods - Durable") == "sector_consumer_goods___durable"
    assert sector_cohort_key("Healthcare") == "sector_healthcare"


def test_sector_cohort_key_handles_none_and_empty():
    assert sector_cohort_key(None) == "sector_unknown"
    assert sector_cohort_key("") == "sector_unknown"
