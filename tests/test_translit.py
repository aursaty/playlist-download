from playlist_download.translit import phonetic_key


def test_ukrainian_artist_matches_latin_spelling():
    assert phonetic_key("Тартак") == phonetic_key("Tartak")


def test_boombox_matches_cyrillic_spelling():
    assert phonetic_key("БумБокс") == phonetic_key("Boombox")


def test_punctuation_and_case_ignored():
    assert phonetic_key("Hip-Hop") == phonetic_key("hip hop")


def test_empty_string():
    assert phonetic_key("") == ""


def test_other_scripts_kept_not_dropped():
    assert phonetic_key("夜に駆ける") != ""


def test_different_names_have_different_keys():
    assert phonetic_key("Тартак") != phonetic_key("Boombox")
