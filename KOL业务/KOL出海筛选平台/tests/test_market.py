import pytest

from app.market import normalize_market


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("UK", "GB"),
        ("英国", "GB"),
        ("FR", "FR"),
        ("法国", "FR"),
        ("DE", "DE"),
        ("德国", "DE"),
        ("MULTI", "MULTI"),
    ],
)
def test_normalize_market(raw, expected):
    assert normalize_market(raw) == expected


def test_normalize_market_rejects_unsupported_value():
    with pytest.raises(ValueError, match="Unsupported market"):
        normalize_market("US")
