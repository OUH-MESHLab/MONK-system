"""
Tests for monklib parsing correctness against the MFER protocol spec.

Each test constructs a minimal valid MWF binary blob targeting a specific
parser behaviour and asserts the correct decoded value.

Bugs covered:
  Bug 1 – EVT duration read as uint16 (2 bytes) instead of uint32 (4 bytes)
  Bug 2 – SEN exponent sign inverted  (256-byte instead of byte-256)
  Bug 3 – SEN base read as big-endian instead of little-endian
  Bug 4 – AGE birth month off by one  (tm_mon is 0-based; spec is 1-based)
  Bug 5 – ECG_ECG1/ECG_ECG2 lead codes wrong  (0x0001/0x0002 → 0xC001/0xC002)
  Bug 6 – NULL sample value 0x8000 (-32768) not filtered in waveform data
  Bug 7 – LDN::getLeadInfo throws std::out_of_range for unknown lead codes
"""

import math
import os
import struct
import tempfile

import pytest
import monklib

# ── Minimal MWF binary builder ────────────────────────────────────────────────

def tlv(tag_id: int, contents: bytes) -> bytes:
    """Standard TLV record with a 1-byte length field."""
    assert len(contents) <= 255, f"content too long ({len(contents)} bytes)"
    return bytes([tag_id, len(contents)]) + contents


def att(channel_idx: int, inner: bytes) -> bytes:
    """ATT tag (0x3F): channel-index byte then length+content."""
    assert len(inner) <= 255
    return bytes([0x3F, channel_idx, len(inner)]) + inner


def wav(contents: bytes) -> bytes:
    """WAV tag (0x1E) with 4-byte BER-TLV length (wordLength = 0x84).

    wordLength=0x84 → 0x84-128=4 length bytes, read by WAV::WAV as
    lengthBytes.toInt<uint32_t>() which requires exactly 4 bytes.
    Using 2 bytes (0x82) triggers UB: memcpy reads beyond the 2-byte
    vector into garbage memory, corrupting the length field.
    """
    n = len(contents)
    return bytes([0x1E, 0x84]) + struct.pack(">I", n) + contents


def mwf(*tags: bytes) -> bytes:
    """
    Assemble a minimal MWF binary:  BLE(little-endian) + *tags + END.

    BLE byte 0x01 → ByteOrder::ENDIAN_LITTLE.
    END byte 0x80 has no length field (END::END does not pop from the stack).
    """
    return tlv(0x01, bytes([0x01])) + b"".join(tags) + bytes([0x80])


def channel_block(lead_code: int, *, null_sample: bool = False) -> bytes:
    """
    Convenience: return (SEQ + CHN + ATT + WAV) for a single-channel,
    single-sample INT_16_S waveform.  If null_sample is True the one
    sample value is 0x8000 (-32768, the MFER NULL marker).
    """
    inner = (
        tlv(0x09, struct.pack("<H", lead_code))   # LDN
        + tlv(0x0A, bytes([0x00]))                 # DTP: INT_16_S
        + tlv(0x04, struct.pack("<I", 1))           # BLK: 1 sample per sequence
    )
    seq  = tlv(0x06, struct.pack("<H", 1))         # SEQ: 1 sequence
    chn  = tlv(0x05, bytes([1]))                   # CHN: 1 channel
    ch   = att(0, inner)
    sample = struct.pack("<h", -32768 if null_sample else 100)
    return seq + chn + ch + wav(sample)


def channel_block_with_sen(lead_code: int, sen_bytes: bytes) -> bytes:
    """Like channel_block but includes a SEN attribute (4 bytes)."""
    inner = (
        tlv(0x09, struct.pack("<H", lead_code))
        + tlv(0x0A, bytes([0x00]))
        + tlv(0x04, struct.pack("<I", 1))
        + tlv(0x0C, sen_bytes)
    )
    seq = tlv(0x06, struct.pack("<H", 1))
    chn = tlv(0x05, bytes([1]))
    ch  = att(0, inner)
    return seq + chn + ch + wav(struct.pack("<h", 100))


def parse(mwf_bytes: bytes):
    """Write *mwf_bytes* to a temp file and parse with monklib.get_header()."""
    fd, path = tempfile.mkstemp(suffix=".mwf")
    try:
        os.write(fd, mwf_bytes)
        os.close(fd)
        return monklib.get_header(path)
    finally:
        os.unlink(path)


def parse_data(mwf_bytes: bytes):
    """Return a monklib.Data instance for *mwf_bytes*."""
    fd, path = tempfile.mkstemp(suffix=".mwf")
    try:
        os.write(fd, mwf_bytes)
        os.close(fd)
        return monklib.Data(path), path
    except Exception:
        os.unlink(path)
        raise


# ── Bug 1: EVT duration field is 4 bytes, not 2 ──────────────────────────────

class TestEVTDuration:
    def test_nibp_event_duration_4_bytes(self):
        """
        MWF_EVT layout (spec): eventCode(2) + startTime(4) + duration(4) + info(54).
        The buggy code reads duration as uint16_t (2 bytes), corrupting the field
        and mis-aligning all subsequent reads.
        """
        evt_content = (
            struct.pack("<H", 1)           # eventCode = 1
            + struct.pack("<I", 0)         # startTime = 0
            + struct.pack("<I", 65536)     # duration = 65536  (needs uint32)
            + bytes(54)                    # info (54 bytes)
        )
        header = parse(mwf(tlv(0x41, evt_content)))
        assert len(header.events) == 1
        assert header.events[0].duration == 65536


# ── Bug 2 & 3: SEN exponent sign and base endianness ─────────────────────────

class TestSENSamplingResolution:
    """
    SEN bytes layout (spec): [skip(1)] [exponent(1)] [base_lo(1)] [base_hi(1)]
    exponent = signed: stored as (exponent + 256) mod 256 → decoded as byte - 256
    base is little-endian.

    The tests access Channel.samplingResolutionValue (float), which requires
    that attribute to be exposed in pybind.cpp.
    """

    def test_ecg_resolution_sign_and_value(self):
        """
        ECG SEN bytes: 00 FA 02 00
          exponent byte 0xFA = 250 → 250 - 256 = -6
          base bytes 02 00 LE → 2
          expected resolution = 2 × 10^-6
        """
        sen = bytes([0x00, 0xFA, 0x02, 0x00])
        # ECG I lead code 0x0001
        header = parse(mwf(channel_block_with_sen(0x0001, sen)))
        assert len(header.channels) == 1
        sr = header.channels[0].samplingResolutionValue
        assert abs(sr - 2e-6) < 1e-9, f"expected 2e-6, got {sr}"

    def test_spo2_resolution_little_endian_base(self):
        """
        SpO₂ SEN bytes: 00 F9 D9 17
          exponent byte 0xF9 = 249 → 249 - 256 = -7
          base bytes D9 17 LE → 0x17D9 = 6105
          expected resolution = 6105 × 10^-7
        """
        sen = bytes([0x00, 0xF9, 0xD9, 0x17])
        # SPO2 lead code 0xC008
        header = parse(mwf(channel_block_with_sen(0xC008, sen)))
        assert len(header.channels) == 1
        sr = header.channels[0].samplingResolutionValue
        expected = 6105 * (10 ** -7)
        assert abs(sr - expected) / expected < 1e-5, f"expected {expected}, got {sr}"


# ── Bug 4: AGE birth month off by one ────────────────────────────────────────

class TestAGEBirthDate:
    """
    AGE tag when years == 0xFF uses a birth-date encoding:
      byte 0: 0xFF  (null-years marker)
      bytes 1-2: ignored
      bytes 3-4: year (uint16, LE)
      byte 5: month (1-based per spec, but tm_mon is 0-based)
      byte 6: day
    """

    def test_birth_month_not_off_by_one(self):
        age_content = (
            bytes([0xFF])              # years = null
            + bytes([0xFF, 0xFF])      # skip
            + struct.pack("<H", 2000)  # year = 2000
            + bytes([7])               # month = July (spec: 1-based)
            + bytes([21])              # day = 21
        )
        header = parse(mwf(tlv(0x83, age_content)))
        assert header.birthDateISO == "2000-07-21", (
            f"expected '2000-07-21', got '{header.birthDateISO}'"
        )

    def test_birth_month_january(self):
        """January (month=1) must not become December of the previous year."""
        age_content = (
            bytes([0xFF])
            + bytes([0xFF, 0xFF])
            + struct.pack("<H", 1995)
            + bytes([1])   # January
            + bytes([15])
        )
        header = parse(mwf(tlv(0x83, age_content)))
        assert header.birthDateISO == "1995-01-15", (
            f"expected '1995-01-15', got '{header.birthDateISO}'"
        )


# ── Bug 5: ECG_ECG1 / ECG_ECG2 wrong lead codes ──────────────────────────────

class TestLDNECGCodes:
    """
    Spec: ECG ECG1 → 0xC001, ECG ECG2 → 0xC002.
    The buggy code has ECG_ECG1 = 0x0001 and ECG_ECG2 = 0x0002, which
    collide with ECG_I and ECG_II in the LeadMap, making 0xC001/0xC002
    absent from the map and causing std::out_of_range.
    """

    def test_ecg_ecg1_resolves_correctly(self):
        header = parse(mwf(channel_block(0xC001)))
        assert len(header.channels) == 1
        assert header.channels[0].attribute == "ECG ECG1"

    def test_ecg_ecg2_resolves_correctly(self):
        header = parse(mwf(channel_block(0xC002)))
        assert len(header.channels) == 1
        assert header.channels[0].attribute == "ECG ECG2"

    def test_ecg_i_still_resolves(self):
        """Fixing ECG_ECG1 must not break ECG I (0x0001)."""
        header = parse(mwf(channel_block(0x0001)))
        assert header.channels[0].attribute == "ECG I"

    def test_ecg_ii_still_resolves(self):
        header = parse(mwf(channel_block(0x0002)))
        assert header.channels[0].attribute == "ECG II"


# ── Bug 6: NULL waveform sample 0x8000 not filtered ──────────────────────────

class TestNullSampleFiltering:
    """
    MFER spec: sample value 0x8000 (-32768 for INT_16_S) means 'no measurement'.
    It should be represented as NaN in channel.data, not as -32768.

    Requires channel.data to be exposed via pybind.
    """

    def test_null_sample_becomes_nan(self):
        header = parse(mwf(channel_block(0x0001, null_sample=True)))
        assert len(header.channels) == 1
        data = header.channels[0].data
        assert len(data) == 1
        assert math.isnan(data[0]), f"expected NaN for null sample, got {data[0]}"

    def test_normal_sample_is_not_nan(self):
        header = parse(mwf(channel_block(0x0001, null_sample=False)))
        data = header.channels[0].data
        assert len(data) == 1
        assert not math.isnan(data[0])
        assert data[0] == 100.0


# ── Bug 7: LDN::getLeadInfo throws on unknown lead codes ─────────────────────

class TestLDNUnknownCode:
    """
    LeadMap.at(code) throws std::out_of_range for any code not in the map.
    After the fix, unknown codes should return a fallback LeadInfo instead
    of crashing.
    """

    def test_unknown_lead_code_does_not_raise(self):
        # 0x9999 is not in the LeadMap
        header = parse(mwf(channel_block(0x9999)))
        assert len(header.channels) == 1

    def test_unknown_lead_code_attribute_describes_code(self):
        header = parse(mwf(channel_block(0x9999)))
        attr = header.channels[0].attribute
        # Should contain some indication it is unknown (case-insensitive)
        assert "unknown" in attr.lower() or "9999" in attr.lower(), (
            f"unexpected attribute for unknown lead: '{attr}'"
        )
