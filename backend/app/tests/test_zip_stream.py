"""Unit tests for the bounded-memory ZIP streaming primitives (issue #1376)."""

import io
import zipfile

import pytest

from app.services.zip_stream import STREAM_BLOCK_SIZE, ZipStreamSink, write_stream_entry

# General-purpose bit 3: sizes/CRC follow the entry data in a data descriptor,
# which is how zipfile writes when it cannot seek back into the output.
_DATA_DESCRIPTOR_FLAG = 0x08


class TestZipStreamSink:
    def test_is_write_only_and_refuses_to_seek(self):
        sink = ZipStreamSink()
        assert sink.writable()
        assert not sink.seekable()
        assert not sink.readable()
        # zipfile probes seek() once and, on this error, switches to streaming mode.
        with pytest.raises(io.UnsupportedOperation):
            sink.seek(0)

    def test_tell_tracks_total_bytes_written(self):
        sink = ZipStreamSink()
        assert sink.write(b"abc") == 3
        assert sink.write(memoryview(b"defg")) == 4
        assert sink.tell() == 7
        # Draining must not move the write position — zipfile's entry offsets
        # are archive-absolute.
        sink.take_all()
        assert sink.tell() == 7

    def test_take_blocks_yields_full_blocks_and_keeps_the_remainder(self):
        sink = ZipStreamSink(block_size=4)
        sink.write(b"abcdefghij")
        assert list(sink.take_blocks()) == [b"abcd", b"efgh"]
        assert sink.pending_bytes == 2
        assert list(sink.take_blocks()) == []
        assert sink.take_all() == b"ij"
        assert sink.pending_bytes == 0
        assert sink.take_all() == b""

    def test_rejects_non_positive_block_size(self):
        with pytest.raises(ValueError):
            ZipStreamSink(block_size=0)

    def test_default_block_size_is_one_mebibyte(self):
        assert STREAM_BLOCK_SIZE == 1 << 20

    def test_zipfile_streams_through_the_sink_and_the_output_round_trips(self):
        sink = ZipStreamSink(block_size=64)
        chunks = []
        with zipfile.ZipFile(sink, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("a.txt", b"hello " * 50)
            chunks.extend(sink.take_blocks())
            zf.writestr("b.txt", b"world")
            chunks.extend(sink.take_blocks())
        chunks.extend(sink.take_blocks())
        chunks.append(sink.take_all())

        assert all(len(chunk) == 64 for chunk in chunks[:-1])
        assert 0 < len(chunks[-1]) < 64
        with zipfile.ZipFile(io.BytesIO(b"".join(chunks))) as zf:
            assert zf.testzip() is None
            assert zf.read("a.txt") == b"hello " * 50
            assert zf.read("b.txt") == b"world"
            # Streaming mode: zipfile never seeked back to patch a local header.
            assert all(info.flag_bits & _DATA_DESCRIPTOR_FLAG for info in zf.infolist())


class TestWriteStreamEntry:
    @staticmethod
    def _round_trip(**kwargs):
        sink = ZipStreamSink()
        with zipfile.ZipFile(sink, "w", zipfile.ZIP_DEFLATED) as zf:
            returned = write_stream_entry(zf, "docs/x.bin", **kwargs)
        return returned, zipfile.ZipFile(io.BytesIO(sink.take_all()))

    def test_consumes_the_chunk_iterable_lazily_without_keeping_bytes(self):
        seen = []

        def chunks():
            for piece in (b"ab", b"cd", b"e"):
                seen.append(piece)
                yield piece

        returned, zf = self._round_trip(chunks=chunks(), expected_size=5)
        assert returned is None
        assert seen == [b"ab", b"cd", b"e"]
        assert zf.read("docs/x.bin") == b"abcde"
        assert zf.testzip() is None

    def test_keep_bytes_returns_the_full_content(self):
        returned, zf = self._round_trip(chunks=iter([b"ab", b"cd"]), expected_size=4, keep_bytes=True)
        assert returned == b"abcd"
        assert zf.read("docs/x.bin") == b"abcd"

    def test_unknown_size_still_produces_a_readable_entry(self):
        # No Content-Length → ZIP64 is forced so a >2 GiB object cannot fail at
        # close time; small entries must remain perfectly ordinary to read.
        returned, zf = self._round_trip(chunks=iter([b"xyz"]))
        assert returned is None
        assert zf.read("docs/x.bin") == b"xyz"
        assert zf.testzip() is None

    def test_entry_carries_a_real_timestamp_and_the_archive_compression(self):
        _, zf = self._round_trip(chunks=iter([b"payload"]), expected_size=7)
        info = zf.getinfo("docs/x.bin")
        # zipfile stamps bare-name entries 1980-01-01; ours get the current time
        # like writestr() does, so extractors show a sensible date.
        assert info.date_time[0] > 1980
        assert info.compress_type == zipfile.ZIP_DEFLATED
