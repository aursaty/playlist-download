import zipfile
from pathlib import Path
from typing import BinaryIO


def write_archive(folder: Path, fileobj: BinaryIO) -> int:
    """Zip the finished mp3s of a playlist folder (no reports, no partial files). Returns the file count."""
    files = sorted(f for f in folder.glob("*.mp3") if not f.name.startswith("."))
    with zipfile.ZipFile(fileobj, "w", zipfile.ZIP_STORED) as z:  # mp3 does not compress
        for f in files:
            z.write(f, f"{folder.name}/{f.name}")
    return len(files)
