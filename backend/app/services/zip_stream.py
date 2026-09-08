"""Bounded-memory ZIP streaming primitives.

The college 匯出申請資料 ZIP can run into the gigabytes (issue #1376). Building
it in a ``BytesIO`` and handing that to ``StreamingResponse`` kept the whole
archive in RAM and — because ``iter(BytesIO)`` iterates line by line — pushed
millions of tiny chunks through the threadpool. These helpers let ``zipfile``
write straight into a sink the response generator drains in fixed-size blocks,
and copy spooled object streams into entries chunk by chunk.
"""

import io
import time
import zipfile
from collections import deque
from typing import Deque, Iterable, Iterator, Optional

# Size of each chunk handed to the ASGI server. 1 MiB keeps the number of
# send() round-trips for a multi-GB archive in the low thousands.
STREAM_BLOCK_SIZE = 1 << 20

# Read size per iteration when copying an object-storage stream.
COPY_CHUNK_SIZE = 256 * 1024


class ZipStreamSink(io.RawIOBase):
    """Write-only, unseekable byte sink for ``zipfile.ZipFile(..., "w")``.

    Because ``seek()`` is unsupported, zipfile switches to streaming mode and
    trails every entry with a data descriptor instead of seeking back to patch
    the local header — so bytes can leave as soon as they are written. The
    producer drains the sink via ``take_blocks()`` (whole blocks) and
    ``take_all()`` (the tail once the archive is closed); what stays pending is
    bounded by whatever the producer writes between two drains (one student's
    entries in the export), never by the archive.

    Chunks are kept as memoryviews in a deque and sliced without copying, so a
    drain costs one concatenation per block instead of memmoving the remainder
    on every block. The deque is the one place state is mutated in place: it is
    an I/O buffer, private to this class, and drained by the owner.
    """

    def __init__(self, block_size: int = STREAM_BLOCK_SIZE) -> None:
        super().__init__()
        if block_size <= 0:
            raise ValueError("block_size must be positive")
        self._block_size = block_size
        self._chunks: Deque[memoryview] = deque()
        self._pending = 0
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
        # bytes() is free for bytes and a copy for any buffer the writer might
        # reuse; the memoryview lets _take() slice it without copying.
        chunk = memoryview(bytes(data))
        self._chunks.append(chunk)
        self._pending += chunk.nbytes
        self._position += chunk.nbytes
        return chunk.nbytes

    @property
    def pending_bytes(self) -> int:
        """Bytes written but not yet taken by the producer."""
        return self._pending

    def take_blocks(self) -> Iterator[bytes]:
        """Yield every complete block currently pending; the remainder stays."""
        while self._pending >= self._block_size:
            yield self._take(self._block_size)

    def take_all(self) -> bytes:
        """Return and clear everything pending (the tail after ZipFile.close())."""
        return self._take(self._pending) if self._pending else b""

    def _take(self, size: int) -> bytes:
        parts = []
        remaining = size
        while remaining:
            chunk = self._chunks.popleft()
            if chunk.nbytes > remaining:
                parts.append(chunk[:remaining])
                self._chunks.appendleft(chunk[remaining:])
                remaining = 0
            else:
                parts.append(chunk)
                remaining -= chunk.nbytes
        self._pending -= size
        return b"".join(parts)


def write_stream_entry(
    zf: zipfile.ZipFile,
    zip_path: str,
    chunks: Iterable[bytes],
    *,
    size: int,
    keep_bytes: bool = False,
) -> Optional[bytes]:
    """Write ``chunks`` (``size`` bytes in total) as one ZIP entry.

    The size lets zipfile decide on ZIP64 up front, so an entry over 2 GiB
    cannot fail at close time; in streaming mode the sizes actually written
    are what land in the archive. With ``keep_bytes`` the content is also
    accumulated and returned, for callers that still need the whole document
    afterwards (the merged PDF). Returns the bytes when kept, else ``None``.

    Blocking (deflate + whatever ``chunks`` reads from): run in a worker thread.
    """
    info = zipfile.ZipInfo(zip_path, date_time=time.localtime(time.time())[:6])
    info.compress_type = zf.compression
    info.file_size = size
    kept = bytearray() if keep_bytes else None
    with zf.open(info, "w") as dest:
        for chunk in chunks:
            dest.write(chunk)
            if kept is not None:
                kept += chunk
    return bytes(kept) if kept is not None else None
