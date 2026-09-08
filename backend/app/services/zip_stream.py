"""Bounded-memory ZIP streaming primitives.

The college 匯出申請資料 ZIP can run into the gigabytes (issue #1376). Building
it in a ``BytesIO`` and handing that to ``StreamingResponse`` kept the whole
archive in RAM and — because ``iter(BytesIO)`` iterates line by line — pushed
millions of tiny chunks through the threadpool. These helpers let ``zipfile``
write straight into a sink the response generator drains in fixed-size blocks,
and copy object-storage streams into entries chunk by chunk.
"""

import io
import time
import zipfile
from typing import Iterable, Iterator, Optional

# Size of each chunk handed to the ASGI server. 1 MiB keeps the number of
# send() round-trips for a multi-GB archive in the low thousands.
STREAM_BLOCK_SIZE = 1 << 20

# Read size per iteration when copying an object-storage stream into the ZIP.
COPY_CHUNK_SIZE = 256 * 1024


class ZipStreamSink(io.RawIOBase):
    """Write-only, unseekable byte sink for ``zipfile.ZipFile(..., "w")``.

    Because ``seek()`` is unsupported, zipfile switches to streaming mode and
    trails every entry with a data descriptor instead of seeking back to patch
    the local header — so bytes can leave as soon as they are written. The
    producer drains the sink between entries via ``take_blocks()`` (whole
    blocks) and ``take_all()`` (the tail once the archive is closed), which
    keeps the pending buffer bounded by one entry rather than the archive.

    The internal buffer is the one place bytes are mutated in place: it is an
    I/O buffer, private to this class, and drained by the owner.
    """

    def __init__(self, block_size: int = STREAM_BLOCK_SIZE) -> None:
        super().__init__()
        if block_size <= 0:
            raise ValueError("block_size must be positive")
        self._block_size = block_size
        self._pending = bytearray()
        self._position = 0

    def writable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def tell(self) -> int:
        # zipfile records entry offsets via tell(); IOBase's default tell()
        # seeks, which this sink cannot do.
        return self._position

    def write(self, data) -> int:
        view = memoryview(data)
        self._pending += view
        self._position += view.nbytes
        return view.nbytes

    @property
    def pending_bytes(self) -> int:
        """Bytes written but not yet taken by the producer."""
        return len(self._pending)

    def take_blocks(self) -> Iterator[bytes]:
        """Yield every complete block currently pending; the remainder stays."""
        while len(self._pending) >= self._block_size:
            block = bytes(self._pending[: self._block_size])
            del self._pending[: self._block_size]
            yield block

    def take_all(self) -> bytes:
        """Return and clear everything pending (the tail after ZipFile.close())."""
        tail = bytes(self._pending)
        self._pending = bytearray()
        return tail


def write_stream_entry(
    zf: zipfile.ZipFile,
    zip_path: str,
    chunks: Iterable[bytes],
    *,
    expected_size: Optional[int] = None,
    keep_bytes: bool = False,
) -> Optional[bytes]:
    """Write ``chunks`` as one ZIP entry without materialising them first.

    ``expected_size`` (the object's Content-Length when known) only steers the
    ZIP64 decision; an unknown size forces ZIP64 so an entry over 2 GiB cannot
    fail at close time. With ``keep_bytes`` the content is also accumulated
    and returned, for callers that still need the whole document afterwards
    (the merged PDF). Returns the bytes when kept, else ``None``.

    Blocking (deflate + whatever ``chunks`` reads from): run in a worker thread.
    """
    info = zipfile.ZipInfo(zip_path, date_time=time.localtime(time.time())[:6])
    info.compress_type = zf.compression
    if expected_size is not None:
        info.file_size = expected_size
    kept = bytearray() if keep_bytes else None
    with zf.open(info, "w", force_zip64=expected_size is None) as dest:
        for chunk in chunks:
            dest.write(chunk)
            if kept is not None:
                kept += chunk
    return bytes(kept) if kept is not None else None
