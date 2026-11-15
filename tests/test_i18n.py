import re

import pytest

import i18n


@pytest.fixture(autouse=True)
def reset_language():
    yield
    i18n.set_language("en")


def placeholders(text):
    return sorted(re.findall(r"\{(\w+)\}", text))


def test_every_string_has_all_languages():
    for key, entry in i18n.STRINGS.items():
        assert set(entry) == set(i18n.LANGUAGES), key


def test_placeholders_match_across_languages():
    """A translation that drops or renames a {placeholder} crashes t() at runtime."""
    for key, entry in i18n.STRINGS.items():
        for lang in ("fa", "ru"):
            assert placeholders(entry[lang]) == placeholders(entry["en"]), f"{key} [{lang}]"


def test_unknown_language_falls_back_to_english():
    i18n.set_language("xx")
    assert i18n.LANG == "en"
    assert not i18n.RTL


def test_only_farsi_is_rtl():
    for lang in i18n.LANGUAGES:
        i18n.set_language(lang)
        assert i18n.RTL == (lang == "fa")


def test_t_formats_placeholders():
    i18n.set_language("en")
    assert i18n.t("tests_n", n=5) == "5 tests"
    i18n.set_language("fa")
    assert "5" in i18n.t("tests_n", n=5)


def test_num_uses_non_breaking_space_for_russian_only():
    i18n.set_language("en")
    assert i18n.num(1234567) == "1,234,567"
    i18n.set_language("ru")
    assert i18n.num(1234567) == "1 234 567"


@pytest.mark.parametrize("seconds, expected", [(5, "5 s"), (75, "1 min"), (3700, "1 h 01 min"), (-3, "0 s")])
def test_duration(seconds, expected):
    i18n.set_language("en")
    assert i18n.duration(seconds) == expected


def test_vis_is_a_no_op_outside_farsi():
    i18n.set_language("en")
    assert i18n.vis("Windscribe CLI") == "Windscribe CLI"
    i18n.set_language("ru")
    assert i18n.vis("Привет") == "Привет"


def test_vis_keeps_latin_words_intact_in_farsi():
    i18n.set_language("fa")
    shown = i18n.vis("Windscribe CLI آماده است")
    assert "Windscribe CLI" in shown


def test_wrap_breaks_on_width():
    text = "aa bb cc dd"
    assert i18n.wrap(text, measure=len, width=5) == "aa bb\ncc dd"
