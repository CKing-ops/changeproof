import pytest

from changeproof.markets import DEFAULT_MARKET, MARKETS


def test_general_is_the_default_market():
    assert DEFAULT_MARKET == "general"


def test_the_three_profiles_exist():
    assert set(MARKETS) == {"general", "us-defense", "eu-dora"}


@pytest.mark.parametrize("market", sorted(MARKETS))
def test_every_profile_is_self_consistent(market):
    profile = MARKETS[market]
    assert profile.name == market
    assert profile.default_classification in profile.classifications
    assert profile.no_egress_classifications <= set(profile.classifications)
    assert profile.default_classification not in profile.no_egress_classifications
    assert profile.frameworks


@pytest.mark.parametrize("market", sorted(MARKETS))
def test_every_profile_keeps_some_classification_off_the_network(market):
    assert MARKETS[market].no_egress_classifications


def test_general_profile_is_anchored_on_common_change_management_controls():
    assert {"soc2", "iso-27001"} <= set(MARKETS["general"].frameworks)


def test_only_dora_restricts_processing_region():
    assert MARKETS["eu-dora"].allowed_regions == frozenset({"eea", "adequacy"})
    assert MARKETS["general"].allowed_regions is None
    assert MARKETS["us-defense"].allowed_regions is None
