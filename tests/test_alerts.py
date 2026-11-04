import pytest

from sajag import alerts as A


@pytest.mark.parametrize("language", ["hi", "mai", "bho", "en"])
@pytest.mark.parametrize("level", [1, 2, 3])
def test_every_sms_fits_one_message_for_every_district(language, level):
    for district in A.DISTRICT_HI:
        text = A.render(language, level, district, 7)
        assert len(text) <= A.SMS_LIMIT[language], (district, len(text), text)


def test_all_38_districts_have_a_hindi_name():
    assert len(A.DISTRICT_HI) == 38


@pytest.mark.parametrize("language", ["hi", "mai", "bho", "en"])
def test_every_message_gives_the_helpline(language):
    for level in (1, 2, 3):
        for kind in ("sms", "voice"):
            assert "1070" in A.TEMPLATES[language][str(level)][kind]
