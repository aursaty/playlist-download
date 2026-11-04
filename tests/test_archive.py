import zipfile

from playlist_download.archive import write_archive


def test_archive_contains_only_final_mp3s_in_order(tmp_path):
    folder = tmp_path / "My List"
    folder.mkdir()
    (folder / "02 - B - Two.mp3").write_bytes(b"two")
    (folder / "01 - A - One.mp3").write_bytes(b"one")
    (folder / "03 - Привіт 🎵.mp3").write_bytes(b"three")
    (folder / ".04.part.mp3").write_bytes(b"partial")
    (folder / "report.json").write_text("{}")
    (folder / "failed.txt").write_text("x")

    out = tmp_path / "out.zip"
    with out.open("wb") as fh:
        count = write_archive(folder, fh)

    assert count == 3
    with zipfile.ZipFile(out) as z:
        assert z.namelist() == ["My List/01 - A - One.mp3", "My List/02 - B - Two.mp3", "My List/03 - Привіт 🎵.mp3"]
        assert z.read("My List/01 - A - One.mp3") == b"one"
        assert z.testzip() is None


def test_archive_of_empty_folder_has_zero_entries(tmp_path):
    folder = tmp_path / "Empty"
    folder.mkdir()
    out = tmp_path / "out.zip"
    with out.open("wb") as fh:
        assert write_archive(folder, fh) == 0
