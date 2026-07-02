#!/usr/bin/env python3
import argparse
import ctypes
import heapq
import struct
from dataclasses import dataclass
from pathlib import Path


MASK64 = (1 << 64) - 1
MASK32 = (1 << 32) - 1
GOLDEN = 0x9E3779B97F4A7C15
SM64_A = 0xBF58476D1CE4E5B9
SM64_B = 0x94D049BB133111EB

HEADER_MASK = bytes.fromhex(
    "523c779517ca728c2c1f885c44587944"
    "e311947aef44ceacb697205620ec4ec3"
    "fe73c869b246216fcfb372178d4ff419"
    "ef3502451eb8926640ad016c42786cd4"
)
HEADER_C0 = 0x91A7F06D3C2B5E18
HEADER_C1 = 0xBDB86DE98BCD0D12
HEADER_C2 = 0xB5A62D9C4107F3EE
HEADER_C3 = 0x47D3E2A91CB8056F
HEADER_C4 = 0xD819AB344CE60771
HEADER_C5 = 0xE1CB9103595F316A
GLOBAL_PERM_CONST = 0x4749445052504449
LZSS_CTRL_CONST = 0x4C5A535344495233
MIXER_LAZY_SEED = 0x58289CA92C4E18C4
WAVE_DIR_CONST = 0x574156455F444952
MIXER_TABLE = (
    0xC205A1395B05834C, 0xA7FD58B11AE8E85E,
    0x1D0A773680B75582, 0xE9B4142326822D3D,
    0x02F68B2B7380123C, 0x9697329DA3A2BD4D,
    0xB91D71D3F3E8D23B, 0xE1DA4CA11512A096,
)
FAKE_MIXER_FIELDS = (
    0x0A9DD1D50687E546, 0x4D58495111C647E4,
    0xA67C94A05917E592, 0xF4D35CD218631377,
    0x30054F47CC425CD7,
)
SCRAMBLE_DECOY_CONST = 0x6465636F795F6272

RS_ORDER = [0, 7, 14, 21, 5, 12, 19, 3, 10, 17, 1, 8, 15, 22,
            6, 13, 20, 4, 11, 18, 2, 9, 16]

SCRAMBLE_REAL_CONST = 0x7265616C5F627261
SCRAMBLE_PERM_CONST = 0x7065726D5F627261
SCRAMBLE_XOR_CONST = 0x786F725F62726164
SCRAMBLE_C1_CONST = 0x62726169645F6331
SCRAMBLE_C2_CONST = 0x62726169645F6332
SCRAMBLE_STEP = 0x2917014799A6026D
SCRAMBLE_NEG_STEP = 0xD6E8FEB86659FD93

RECORD_HASH_CONST = 0x6F61735F64697233
RECORD_INIT_CONST = 0x6F61735F6673746D
RECORD_NAME_CONST = 0x6E616D65


def sm64(value):
    value = (value + GOLDEN) & MASK64
    value = ((value ^ (value >> 30)) * SM64_A) & MASK64
    value = ((value ^ (value >> 27)) * SM64_B) & MASK64
    return (value ^ (value >> 31)) & MASK64


def rol64(value, count):
    return ((value << count) | (value >> (64 - count))) & MASK64


@dataclass(frozen=True)
class Header:
    words: tuple
    entry_count: int
    total_blocks: int
    seed_a: int
    seed_b: int


def parse_header(archive):
    if len(archive) < 64:
        raise ValueError("archive is shorter than its header")
    plain = bytes(a ^ b for a, b in zip(archive[:64], HEADER_MASK))
    words = struct.unpack("<8Q", plain)
    count = words[0] ^ HEADER_C0
    total = words[1] ^ sm64(HEADER_C1 ^ count)
    expected2 = sm64(HEADER_C2 ^ words[1]) ^ ((total * 3 + 0x43) & MASK64)
    seed_a = words[3] ^ sm64(HEADER_C3 ^ words[2])
    seed_b = words[4] ^ sm64(HEADER_C4 ^ words[1] ^ words[3])
    expected5 = sm64(HEADER_C5 ^ count ^ words[2] ^ words[4])
    if words[2] != expected2 or words[5] != expected5:
        raise ValueError("header integrity checks failed")
    if not count or not total or total % count:
        raise ValueError("invalid entry or block count in header")
    return Header(words, count, total, seed_a, seed_b)


def make_global_archive_to_logical(total, seed_a, seed_b):
    seed = seed_a ^ seed_b ^ GLOBAL_PERM_CONST
    perm = list(range(total))
    for index in range(total):
        other = index + sm64(index ^ seed) % (total - index)
        perm[index], perm[other] = perm[other], perm[index]
    inverse = [0] * total
    for index, logical in enumerate(perm):
        inverse[logical] = index
    return inverse


def global_unshuffle(archive, header):
    payl_end = 64 + header.total_blocks * 64
    if len(archive) < payl_end:
        raise ValueError("archive has a truncated PAYL section")
    payl = archive[64:payl_end]
    archive_to_logical = make_global_archive_to_logical(
        header.total_blocks, header.seed_a, header.seed_b
    )
    logical = [None] * header.total_blocks
    for archive_index, logical_index in enumerate(archive_to_logical):
        start = archive_index * 64
        logical[logical_index] = payl[start:start + 64]
    blocks_per_entry = header.total_blocks // header.entry_count
    blob = b"".join(logical)
    size = blocks_per_entry * 64
    return [blob[index * size:(index + 1) * size]
            for index in range(header.entry_count)]


def mixer_block_seed(block_index, chain_value, entry_context,
                     lazy_seed=MIXER_LAZY_SEED):
    if len(entry_context) != 0x108:
        raise ValueError("mixer entry context must be 0x108 bytes")
    field98, fielda0, fielda8, fieldb0, fieldb8 = (
        struct.unpack_from("<Q", entry_context, offset)[0]
        for offset in (0x98, 0xA0, 0xA8, 0xB0, 0xB8)
    )
    table = struct.unpack_from("<8Q", entry_context, 0xC8)
    state = chain_value ^ lazy_seed ^ fielda0 ^ field98
    state ^= rol64(fielda8, 9) ^ rol64(fieldb0, 17)
    state ^= rol64(table[0], 1) ^ block_index ^ fieldb8
    state ^= table[block_index & 7]
    state = sm64(state)
    for table_index in range(1, 8):
        state = sm64(
            rol64(table[table_index], table_index + 1)
            ^ table[(block_index + table_index) & 7]
            ^ state
        )
    return state


def mixer_block(block, seed):
    if len(block) != 64:
        raise ValueError("mixer blocks must be 64 bytes")
    output = bytearray(block)
    for position in range(64):
        value = sm64(
            (rol64(seed, position & 31) + seed + position * GOLDEN) & MASK64
        )
        output[position] ^= (value ^ (value >> 23)) & 0xFF
    for round_index in range(9):
        round_key = sm64(
            rol64(seed, round_index + 3) ^ round_index ^ seed
        )
        for position in range(32):
            value = sm64(
                (position << 9) ^ round_key ^ output[position + 32]
            )
            output[position] = (
                output[position] + (value & 0xFF) + ((value >> 29) & 0xFF)
            ) & 0xFF
        for position in range(32):
            value = sm64((position << 17) ^ round_key ^ output[position])
            output[position + 32] ^= (value ^ (value >> 31)) & 0xFF
    return bytes(output)


def inverse_mixer_block(block, seed):
    if len(block) != 64:
        raise ValueError("mixer blocks must be 64 bytes")
    output = bytearray(block)
    for round_index in range(8, -1, -1):
        round_key = sm64(
            rol64(seed, round_index + 3) ^ round_index ^ seed
        )
        for position in range(32):
            value = sm64((position << 17) ^ round_key ^ output[position])
            output[position + 32] ^= (value ^ (value >> 31)) & 0xFF
        for position in range(32):
            value = sm64(
                (position << 9) ^ round_key ^ output[position + 32]
            )
            output[position] = (
                output[position] - (value & 0xFF) - ((value >> 29) & 0xFF)
            ) & 0xFF
    for position in range(64):
        value = sm64(
            (rol64(seed, position & 31) + seed + position * GOLDEN) & MASK64
        )
        output[position] ^= (value ^ (value >> 23)) & 0xFF
    return bytes(output)


_MIXER_BATCH_LIBRARY = None


def inverse_mixer_blocks(mixed, seed):
    global _MIXER_BATCH_LIBRARY
    if len(mixed) % 64:
        raise ValueError("mixed blocks are not block aligned")
    library_path = Path(__file__).with_name("mixer_batch.so")
    if not library_path.exists():
        return b"".join(
            inverse_mixer_block(mixed[offset:offset + 64], seed)
            for offset in range(0, len(mixed), 64)
        )
    if _MIXER_BATCH_LIBRARY is None:
        library = ctypes.CDLL(str(library_path))
        library.inverse_mixer_blocks.argtypes = (
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint64,
        )
        library.inverse_mixer_blocks.restype = None
        _MIXER_BATCH_LIBRARY = library
    source = ctypes.create_string_buffer(mixed, len(mixed))
    output = ctypes.create_string_buffer(len(mixed))
    _MIXER_BATCH_LIBRARY.inverse_mixer_blocks(
        source, output, len(mixed) // 64, seed,
    )
    return output.raw


def inverse_mixer_entry(mixed, input_length, chain_value,
                        entry_context, permutation):
    if len(mixed) % 64:
        raise ValueError("mixed entry length is not block aligned")
    block_count = len(mixed) // 64
    if len(permutation) != block_count or sorted(permutation) != list(range(block_count)):
        raise ValueError("invalid local mixer permutation")
    if not 0 <= input_length <= len(mixed):
        raise ValueError("invalid pre-mixer input length")
    output = bytearray()
    for source_index, stored_index in enumerate(permutation):
        start = stored_index * 64
        seed = mixer_block_seed(
            source_index, chain_value, entry_context
        )
        output.extend(inverse_mixer_block(mixed[start:start + 64], seed))
    return bytes(output[:input_length])


def find_full_zero_anchors(mixed, chain_value, entry_context):
    if len(mixed) % 64:
        raise ValueError("mixed entry length is not block aligned")
    stored = {}
    for index in range(len(mixed) // 64):
        block = mixed[index * 64:(index + 1) * 64]
        stored.setdefault(block, []).append(index)
    anchors = []
    for source_index in range(len(mixed) // 64):
        seed = mixer_block_seed(source_index, chain_value, entry_context)
        encrypted_zero = mixer_block(b"\0" * 64, seed)
        for stored_index in stored.get(encrypted_zero, ()):
            anchors.append((source_index, stored_index))
    return anchors


def wave_dir(data, length, table, index):
    if length <= 0 or len(data) < length:
        raise ValueError("wave_dir needs the complete input memory span")
    state = WAVE_DIR_CONST ^ index ^ table[1]
    cursor_base = index * 17
    stop_seed = index + 0x5B
    for bit in range(7, -1, -1):
        stop = stop_seed % length
        zero_bits = 0
        prefix_bits = 0
        shifted_bytes = 0
        cursor = cursor_base
        for position in range(length):
            value = data[cursor % length]
            selected = (value >> bit) & 1
            zero_bits += (~selected) & 1
            if position <= stop:
                prefix_bits += selected
            shifted_bytes ^= value << ((bit + position) & 7)
            cursor += 0x83
        mixed = state ^ table[bit] ^ shifted_bytes
        mixed ^= (zero_bits << (bit + 1)) & MASK64
        mixed ^= (prefix_bits << 33) & MASK64
        state = sm64(mixed)
        stop_seed -= 13
    return state


def make_local_permutation(block_count, data, length, table):
    permutation = list(range(block_count))
    for index in range(block_count):
        other = index + wave_dir(data, length, table, index) % (block_count - index)
        permutation[index], permutation[other] = permutation[other], permutation[index]
    return tuple(permutation)


def make_mixer_context(fields, table=MIXER_TABLE):
    context = bytearray(0x108)
    for offset, value in zip((0x98, 0xA0, 0xA8, 0xB0, 0xB8), fields):
        struct.pack_into("<Q", context, offset, value)
    struct.pack_into("<8Q", context, 0xC8, *table)
    return bytes(context)


def make_target_real_context(derived_a8):
    expected_a8 = 0x750835934041C232
    if derived_a8 != expected_a8:
        raise ValueError(
            f"target a8 mismatch: got 0x{derived_a8:016x}, "
            f"expected 0x{expected_a8:016x}"
        )
    return make_mixer_context((
        0xBFE12DC426C20772,
        0xA83B423EE014C752,
        expected_a8,
        0x7435EE6517001031,
        0xEEA1176A5255ACCD,
    ))


@dataclass(frozen=True)
class LZSSBoundaryState:
    out_len: int
    tail: bytes
    control: int | None
    bit_index: int
    ref_low: int | None
    done: bool
    end_offset: int | None
    source_offset: int

    @classmethod
    def initial(cls):
        return cls(0, b"", None, 0, None, False, None, 0)


@dataclass(frozen=True)
class PermutationBeamNode:
    state: LZSSBoundaryState
    used: int
    path: tuple


def advance_lzss_block(state, block):
    output = bytearray(state.tail)
    out_len = state.out_len
    control = state.control
    bit_index = state.bit_index
    ref_low = state.ref_low
    done = state.done
    end_offset = state.end_offset
    cursor = 0

    if done:
        if any(block):
            raise ValueError("nonzero LZSS padding after end marker")
        return LZSSBoundaryState(
            out_len, bytes(output), control, bit_index, ref_low,
            done, end_offset, state.source_offset + len(block),
        )

    while cursor < len(block):
        if control is None:
            absolute_offset = state.source_offset + cursor
            control = block[cursor] ^ (
                sm64(LZSS_CTRL_CONST ^ absolute_offset) & 0xFF
            )
            bit_index = 0
            cursor += 1
            if cursor == len(block):
                break

        is_reference = bool(control & (1 << bit_index))
        if not is_reference:
            output.append(block[cursor])
            out_len += 1
            cursor += 1
        else:
            if ref_low is None:
                ref_low = block[cursor]
                cursor += 1
                if cursor == len(block):
                    break
            token = ref_low | (block[cursor] << 8)
            ref_low = None
            cursor += 1
            if token == 0xFFFF:
                done = True
                end_offset = state.source_offset + cursor
                if any(block[cursor:]):
                    raise ValueError("nonzero LZSS padding after end marker")
                cursor = len(block)
                break
            length = (token >> 12) + 3
            distance = (token & 0xFFF) + 1
            if distance > out_len:
                raise ValueError(
                    f"invalid LZSS distance {distance} at output offset {out_len}"
                )
            for _ in range(length):
                output.append(output[-distance])
                out_len += 1
                if len(output) > 4096:
                    del output[:-4096]

        if len(output) > 4096:
            del output[:-4096]
        bit_index += 1
        if bit_index == 8:
            control = None
            bit_index = 0

    return LZSSBoundaryState(
        out_len, bytes(output), control, bit_index, ref_low,
        done, end_offset, state.source_offset + len(block),
    )


def decompress_lzss(data):
    output = bytearray()
    offset = 0
    while offset < len(data):
        control_offset = offset
        control = data[offset] ^ (sm64(LZSS_CTRL_CONST ^ offset) & 0xFF)
        offset += 1
        for bit in range(8):
            if control & (1 << bit):
                if offset + 2 > len(data):
                    raise ValueError("truncated LZSS token")
                token = data[offset] | (data[offset + 1] << 8)
                offset += 2
                if token == 0xFFFF:
                    return bytes(output), offset
                length = (token >> 12) + 3
                distance = (token & 0xFFF) + 1
                if distance > len(output):
                    raise ValueError(
                        f"invalid LZSS distance {distance} at output offset {len(output)}"
                    )
                for _ in range(length):
                    output.append(output[-distance])
            else:
                if offset >= len(data):
                    raise ValueError("truncated LZSS literal")
                output.append(data[offset])
                offset += 1
    raise ValueError("LZSS end marker was not found")


def make_gf_tables():
    exponent = [0] * 512
    logarithm = [0] * 256
    value = 1
    for index in range(255):
        exponent[index] = value
        logarithm[value] = index
        value <<= 1
        if value & 0x100:
            value ^= 0x11D
    for index in range(255, 512):
        exponent[index] = exponent[index - 255]
    return exponent, logarithm


GF_EXP, GF_LOG = make_gf_tables()


def gf_mul(left, right):
    if not left or not right:
        return 0
    return GF_EXP[GF_LOG[left] + GF_LOG[right]]


def gf_inv(value):
    if not value:
        raise ValueError("zero has no GF(256) inverse")
    return GF_EXP[255 - GF_LOG[value]]


def rs_coefficient(parity_index, data_index):
    power = 3 + 32 * parity_index + data_index * (8 + parity_index)
    return GF_EXP[power % 255]


def invert_gf_matrix(matrix):
    size = len(matrix)
    augmented = [
        row[:] + [1 if row_index == column else 0 for column in range(size)]
        for row_index, row in enumerate(matrix)
    ]
    for column in range(size):
        pivot = next(
            (row for row in range(column, size) if augmented[row][column]),
            None,
        )
        if pivot is None:
            raise ValueError("singular GF(256) reconstruction matrix")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = gf_inv(augmented[column][column])
        augmented[column] = [gf_mul(value, scale) for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            scale = augmented[row][column]
            if scale:
                augmented[row] = [
                    left ^ gf_mul(scale, right)
                    for left, right in zip(augmented[row], augmented[column])
                ]
    return [row[size:] for row in augmented]


def rs_output_length(input_length, seed_a):
    rows = (input_length + 16) // 17
    full_length = 23 * rows
    mixed_length = input_length ^ seed_a
    head = sm64(mixed_length ^ 0x666F675F636F6C73)
    tail = sm64(mixed_length ^ 0x666F675F7461696C)
    drop = ((head % 3) + 2) * rows + (tail % rows)
    return full_length - drop


def candidate_rs_input_lengths(output_length, seed_a):
    minimum_rows = max(1, (output_length + 20) // 21 - 1)
    maximum_rows = output_length // 17 + 2
    candidates = []
    for rows in range(minimum_rows, maximum_rows + 1):
        for length in range(17 * (rows - 1) + 1, 17 * rows + 1):
            if rs_output_length(length, seed_a) == output_length:
                candidates.append(length)
    return candidates


def inverse_rs(encoded, input_length):
    rows = (input_length + 16) // 17
    columns = {}
    offset = 0
    for column in RS_ORDER:
        take = min(rows, len(encoded) - offset)
        if take <= 0:
            break
        columns[column] = bytearray(encoded[offset:offset + take])
        offset += take
    if offset != len(encoded):
        raise ValueError("RS column stream has trailing data")

    missing = [index for index in range(17)
               if len(columns.get(index, b"")) < rows]
    parity = [index for index in range(6)
              if len(columns.get(17 + index, b"")) == rows]
    if len(missing) > len(parity):
        raise ValueError("not enough complete parity columns for RS reconstruction")

    if missing:
        selected = parity[:len(missing)]
        matrix = [[rs_coefficient(p, d) for d in missing] for p in selected]
        inverse = invert_gf_matrix(matrix)
        for data_index in missing:
            columns[data_index] = bytearray(rows)
        known = [index for index in range(17) if index not in missing]
        for row in range(rows):
            rhs = []
            for parity_index in selected:
                value = columns[17 + parity_index][row]
                for data_index in known:
                    value ^= gf_mul(
                        rs_coefficient(parity_index, data_index),
                        columns[data_index][row],
                    )
                rhs.append(value)
            solved = []
            for inverse_row in inverse:
                value = 0
                for coefficient, right in zip(inverse_row, rhs):
                    value ^= gf_mul(coefficient, right)
                solved.append(value)
            for data_index, value in zip(missing, solved):
                columns[data_index][row] = value

    output = bytearray()
    for row in range(rows):
        output.extend(columns[column][row] for column in range(17))
    return bytes(output[:input_length])


def inverse_scramble(data, seed):
    output = bytearray(data)
    length = len(output)
    seed_length = seed ^ length
    permutation_seed = seed ^ SCRAMBLE_PERM_CONST
    xor_seed = seed ^ SCRAMBLE_XOR_CONST

    for round_index in range(4, -1, -1):
        state = sm64(SCRAMBLE_C2_CONST ^ seed_length ^ round_index) & MASK32
        base = ((round_index << 29) & MASK64) ^ xor_seed
        counter = (length * SCRAMBLE_NEG_STEP + SCRAMBLE_STEP) & MASK64
        for index in range(length - 1, -1, -1):
            key = sm64(base ^ counter)
            original = output[index] ^ (state & 0xFF) ^ (key & 0xFF)
            state ^= original ^ (key & MASK32)
            state &= MASK32
            state = (state + ((key >> 31) & MASK32)) & MASK32
            output[index] = original
            counter = (counter + SCRAMBLE_STEP) & MASK64

        round_seed = permutation_seed ^ round_index
        for index in range(length - 1, -1, -1):
            other = index + sm64(index ^ round_seed) % (length - index)
            output[index], output[other] = output[other], output[index]

        state = sm64(SCRAMBLE_C1_CONST ^ seed_length ^ round_index) & MASK32
        base = ((round_index << 37) & MASK64) ^ seed_length
        counter = 0
        for index in range(length):
            key = sm64(base ^ counter)
            original = (output[index] - (state & 0xFF) - (key & 0xFF)) & 0xFF
            state = (state + original + (key & MASK32)) & MASK32
            state ^= (key >> 23) & MASK32
            output[index] = original
            counter = (counter + GOLDEN) & MASK64
    return bytes(output)


def record_fold(value):
    return (value ^ (value >> 19) ^ (value >> 43)) & 0xFF


def record_hash(seed, data):
    state = seed
    for index, value in enumerate(data):
        mixed = (((index << 11) + value) & MASK64) ^ state
        state = sm64((mixed >> 7) ^ rol64(mixed, 9))
    return state


def unpack_records(data, seed_a):
    state = seed_a ^ RECORD_INIT_CONST
    records = []
    offset = 0
    while offset < len(data) - 2:
        index = len(records)
        if offset + 10 > len(data) - 2:
            raise ValueError("truncated record header")
        tag = int.from_bytes(data[offset:offset + 2], "little")
        offset += 2
        name_length = tag ^ (sm64(index ^ state) & 0xFFFF)
        if not 1 <= name_length <= 95:
            raise ValueError(f"invalid record name length {name_length}")
        encoded_length = int.from_bytes(data[offset:offset + 8], "little")
        offset += 8
        if offset + name_length > len(data) - 2:
            raise ValueError("truncated record name")
        name = bytes(
            data[offset + byte_index] ^ record_fold(
                sm64(state ^ (index ^ RECORD_NAME_CONST) ^
                     ((byte_index * SCRAMBLE_NEG_STEP) & MASK64))
            )
            for byte_index in range(name_length)
        )
        offset += name_length
        name_hash = record_hash(
            RECORD_HASH_CONST ^ (index ^ state) ^ name_length, name
        )
        length = encoded_length ^ sm64(index ^ state ^ name_hash)
        if length > len(data) - offset - 2:
            raise ValueError(f"record payload length {length} exceeds remaining stream")
        payload = bytes(
            data[offset + byte_index] ^ record_fold(
                sm64(name_hash ^ length ^ state ^
                     ((byte_index * SCRAMBLE_NEG_STEP) & MASK64))
            )
            for byte_index in range(length)
        )
        offset += length
        content_hash = record_hash(RECORD_HASH_CONST ^ length ^ state, payload)
        state = sm64(content_hash ^ name_hash ^ length ^ state)
        records.append((name, payload))

    if offset != len(data) - 2:
        raise ValueError("record stream does not end at its two-byte trailer")
    trailer = int.from_bytes(data[offset:], "little")
    expected = sm64(len(records) ^ state) & 0xFFFF
    if trailer != expected:
        raise ValueError(
            f"record trailer mismatch: got 0x{trailer:04x}, expected 0x{expected:04x}"
        )
    return records


def oracle_self_test():
    root = Path("/tmp")
    required = {
        "archive": root / "oas_len_probe/quiz.oas",
        "mixed": root / "tgtshape_out1.bin",
        "entry_context": root / "tgtshape_entries_real_blockctx.bin",
        "permutation": root / "tgtshape_perm1.bin",
        "fake_permutation": root / "tgtshape_perm0.bin",
        "lzss": root / "tgtshape_real_plus68.bin",
        "rs": root / "tgtshape_real_plus60.bin",
        "scrambled": root / "tgtshape_real_40a130_input.bin",
        "records": root / "tgtshape_real_pre400f60.bin",
        "plain": root / "oas_len_probe/quiz",
    }
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        raise ValueError("missing oracle files: " + ", ".join(missing))

    archive = required["archive"].read_bytes()
    header = parse_header(archive)
    entries = global_unshuffle(archive, header)
    assert entries[1] == required["mixed"].read_bytes()
    contexts = required["entry_context"].read_bytes()
    context = contexts[0x108:0x210]
    chain_value = struct.unpack_from("<Q", contexts, 0x78)[0]
    permutation_data = required["permutation"].read_bytes()
    permutation = struct.unpack(f"<{len(permutation_data) // 8}Q", permutation_data)
    table = struct.unpack_from("<8Q", contexts, 0xC8)
    assert make_local_permutation(len(permutation), b"quiz", 4, table) == tuple(
        struct.unpack("<1257Q", required["fake_permutation"].read_bytes())
    )
    source_block = required["lzss"].read_bytes()[:64]
    block_seed = mixer_block_seed(0, chain_value, context)
    assert inverse_mixer_blocks(entries[1][:128], block_seed) == b"".join(
        inverse_mixer_block(entries[1][offset:offset + 64], block_seed)
        for offset in range(0, 128, 64)
    )
    stored_start = permutation[0] * 64
    assert mixer_block(source_block, block_seed) == entries[1][stored_start:stored_start + 64]
    synthetic = b"".join(
        mixer_block(b"\0" * 64, mixer_block_seed(index, chain_value, context))
        for index in range(2)
    )
    assert find_full_zero_anchors(synthetic, chain_value, context) == [(0, 0), (1, 1)]
    unmixed = inverse_mixer_entry(
        entries[1],
        len(required["lzss"].read_bytes()),
        chain_value,
        context,
        permutation,
    )
    assert unmixed == required["lzss"].read_bytes()
    decoded, used = decompress_lzss(required["lzss"].read_bytes())
    assert used == len(required["lzss"].read_bytes())
    assert decoded == required["rs"].read_bytes()
    stream_state = LZSSBoundaryState.initial()
    padded_lzss = required["lzss"].read_bytes().ljust(
        ((len(required["lzss"].read_bytes()) + 63) // 64) * 64, b"\0"
    )
    for offset in range(0, len(padded_lzss), 64):
        stream_state = advance_lzss_block(stream_state, padded_lzss[offset:offset + 64])
    assert stream_state.done
    assert stream_state.end_offset == len(required["lzss"].read_bytes())
    assert stream_state.out_len == len(decoded)
    assert stream_state.tail == decoded[-4096:]
    scrambled = required["scrambled"].read_bytes()
    assert inverse_rs(decoded, len(scrambled)) == scrambled
    seed = header.seed_a ^ len(scrambled) ^ SCRAMBLE_REAL_CONST
    records = inverse_scramble(scrambled, seed)
    assert records == required["records"].read_bytes()
    unpacked = unpack_records(records, header.seed_a)
    assert unpacked == [(b"quiz", required["plain"].read_bytes())]
    print("oracle self-test: header, unshuffle, LZSS, RS, scrambler, records OK")


def probe_target_context(entries, header):
    block_count = len(entries[0]) // 64
    fake_context = make_mixer_context(FAKE_MIXER_FIELDS)
    fake_permutation = make_local_permutation(
        block_count, b"quiz", 4, MIXER_TABLE
    )
    fake_packets = inverse_mixer_entry(
        entries[0], len(entries[0]), 4, fake_context, fake_permutation
    )
    fake_rs, packet_length = decompress_lzss(fake_packets)

    decoy_records = None
    record_length = None
    for candidate in candidate_rs_input_lengths(len(fake_rs), header.seed_a):
        try:
            scrambled = inverse_rs(fake_rs, candidate)
            records = inverse_scramble(
                scrambled,
                header.seed_a ^ candidate ^ SCRAMBLE_DECOY_CONST,
            )
            decoy_records = unpack_records(records, header.seed_a)
            record_length = candidate
            break
        except ValueError:
            continue
    if decoy_records is None:
        raise ValueError("target entry 0 did not produce a valid decoy record stream")

    real_a8 = wave_dir(
        fake_rs, len(fake_rs), MIXER_TABLE, 1 ^ block_count
    )
    real_context = make_target_real_context(real_a8)
    return (packet_length, len(fake_rs), record_length, real_a8,
            real_context, decoy_records)


def trailing_zero_count(block):
    return len(block) - len(block.rstrip(b"\0"))


def target_zero_anchor_diagnostic(mixed, chain_value, entry_context):
    block_count = len(mixed) // 64
    anchors = find_full_zero_anchors(mixed, chain_value, entry_context)
    sources = [source for source, _ in anchors]
    contiguous_suffix = bool(sources) and sources == list(range(sources[0], block_count))
    print(f"full-zero anchors: {len(anchors)}")
    print(f"first source index: {sources[0] if sources else 'none'}")
    print(f"last source index: {sources[-1] if sources else 'none'}")
    print(f"contiguous suffix: {contiguous_suffix}")
    print(f"first 10 anchors: {anchors[:10]}")
    print(f"last 10 anchors: {anchors[-10:] if anchors else []}")

    pivot = sources[0] if sources else block_count - 1
    source_indices = range(max(0, pivot - 2), min(block_count, pivot + 3))
    candidates = []
    for source_index in source_indices:
        seed = mixer_block_seed(source_index, chain_value, entry_context)
        for stored_index in range(block_count):
            start = stored_index * 64
            plain = inverse_mixer_block(mixed[start:start + 64], seed)
            suffix = trailing_zero_count(plain)
            if suffix:
                candidates.append((suffix, source_index, stored_index, plain[-16:].hex()))
    candidates.sort(reverse=True)
    print("partial zero-suffix candidates:")
    for suffix, source_index, stored_index, tail in candidates[:20]:
        print(
            f"  source={source_index} stored={stored_index} "
            f"zero_suffix={suffix} tail16={tail}"
        )


def search_lzss_permutation(mixed, chain_value, entry_context, beam_width,
                            depth, anchors=None, expected=None):
    block_count = len(mixed) // 64
    if len(mixed) % 64 or not 0 < depth <= block_count:
        raise ValueError("invalid permutation search dimensions")
    anchors = anchors or {}
    nodes = [PermutationBeamNode(LZSSBoundaryState.initial(), 0, ())]
    for source_index in range(depth):
        seed = mixer_block_seed(source_index, chain_value, entry_context)
        forced = anchors.get(source_index)
        stored_indices = (forced,) if forced is not None else range(block_count)
        if forced is None:
            decrypted = inverse_mixer_blocks(mixed, seed)
            plain_blocks = {
                stored_index: decrypted[stored_index * 64:(stored_index + 1) * 64]
                for stored_index in stored_indices
            }
        else:
            start = forced * 64
            plain_blocks = {
                forced: inverse_mixer_block(mixed[start:start + 64], seed)
            }
        best = []
        serial = 0
        survivors = 0
        for node in nodes:
            for stored_index, plain in plain_blocks.items():
                bit = 1 << stored_index
                if node.used & bit:
                    continue
                try:
                    next_state = advance_lzss_block(node.state, plain)
                except ValueError:
                    continue
                if next_state.done and source_index != block_count - 1:
                    continue
                survivors += 1
                rank = (next_state.out_len, stored_index)
                item_key = (-rank[0], -rank[1])
                if len(best) >= beam_width and item_key <= best[0][:2]:
                    continue
                next_node = PermutationBeamNode(
                    next_state, node.used | bit, node.path + (stored_index,)
                )
                item = (item_key[0], item_key[1], serial, next_node)
                serial += 1
                if len(best) < beam_width:
                    heapq.heappush(best, item)
                else:
                    heapq.heapreplace(best, item)
        nodes = [item[3] for item in best]
        nodes.sort(key=lambda node: (node.state.out_len, node.path))
        correct_retained = None
        if expected is not None:
            prefix = tuple(expected[:source_index + 1])
            correct_retained = any(node.path == prefix for node in nodes)
        if source_index < 8 or (source_index + 1) % 16 == 0:
            suffix = (
                f" correct_retained={correct_retained}"
                if correct_retained is not None else ""
            )
            print(
                f"depth={source_index + 1} valid={survivors} "
                f"kept={len(nodes)} best_out={nodes[0].state.out_len if nodes else 'none'}"
                f"{suffix}"
            )
        if not nodes:
            raise ValueError(f"permutation beam exhausted at depth {source_index + 1}")
        if correct_retained is False:
            raise ValueError(
                f"known entry-0 path dropped at depth {source_index + 1}"
            )
    return nodes


def permutation_search_self_test(entries, beam_width, depth, entry_index):
    if entry_index != 0:
        raise ValueError("the solved permutation self-test is available only for entry 0")
    block_count = len(entries[0]) // 64
    context = make_mixer_context(FAKE_MIXER_FIELDS)
    expected = make_local_permutation(block_count, b"quiz", 4, MIXER_TABLE)
    state = LZSSBoundaryState.initial()
    used = 0
    tested_depth = min(depth, block_count)
    worst_rank = 0
    for source_index in range(tested_depth):
        seed = mixer_block_seed(source_index, 4, context)
        decrypted = inverse_mixer_blocks(entries[0], seed)
        candidates = []
        correct_state = None
        for stored_index in range(block_count):
            if used & (1 << stored_index):
                continue
            start = stored_index * 64
            plain = decrypted[start:start + 64]
            try:
                next_state = advance_lzss_block(state, plain)
            except ValueError:
                continue
            if next_state.done and source_index != block_count - 1:
                continue
            candidates.append((next_state.out_len, stored_index, next_state))
            if stored_index == expected[source_index]:
                correct_state = next_state
        if correct_state is None:
            raise ValueError(
                f"known entry-0 block rejected at depth {source_index + 1}"
            )
        candidates.sort(key=lambda item: (item[0], item[1]))
        correct_rank = next(
            rank for rank, item in enumerate(candidates, 1)
            if item[1] == expected[source_index]
        )
        worst_rank = max(worst_rank, correct_rank)
        if correct_rank > beam_width:
            raise ValueError(
                f"known entry-0 block rank {correct_rank} exceeds beam "
                f"at depth {source_index + 1}"
            )
        state = correct_state
        used |= 1 << expected[source_index]
        if source_index < 8 or (source_index + 1) % 16 == 0:
            print(
                f"depth={source_index + 1} valid={len(candidates)} "
                f"correct_rank={correct_rank} out={state.out_len}",
                flush=True,
            )
    print(
        f"entry-0 permutation search self-test: correct local path retained "
        f"through depth {tested_depth}; worst_rank={worst_rank}"
    )


def target_first_block_census(mixed, chain_value, entry_context):
    seed = mixer_block_seed(0, chain_value, entry_context)
    decrypted = inverse_mixer_blocks(mixed, seed)
    survivors = []
    for stored_index in range(len(mixed) // 64):
        start = stored_index * 64
        plain = decrypted[start:start + 64]
        try:
            state = advance_lzss_block(LZSSBoundaryState.initial(), plain)
        except ValueError:
            continue
        if state.done:
            continue
        survivors.append((state.out_len, stored_index, plain, state))
    survivors.sort(key=lambda item: (item[0], item[1]))
    print(f"target first-block survivors: {len(survivors)}")
    for out_len, stored_index, plain, state in survivors[:20]:
        print(
            f"  stored={stored_index} first16={plain[:16].hex()} "
            f"out={out_len} control={state.control!r} bit={state.bit_index} "
            f"ref_low={state.ref_low!r} done={state.done}"
        )
    return survivors


def save_target_prefix(path, plain):
    Path("target_perm_prefix.bin").write_bytes(
        struct.pack(f"<{len(path)}Q", *path)
    )
    Path("target_lzss_prefix.bin").write_bytes(plain)


def target_lzss_ranked_search(mixed, chain_value, entry_context, depth,
                              beam_width):
    block_count = len(mixed) // 64
    depth = min(depth, block_count)
    path_file = Path("target_perm_prefix.bin")
    path = []
    state = LZSSBoundaryState.initial()
    used = 0
    plain_output = bytearray()
    if path_file.exists():
        raw_path = path_file.read_bytes()
        if len(raw_path) % 8:
            raise ValueError("saved target permutation prefix is malformed")
        saved = list(struct.unpack(f"<{len(raw_path) // 8}Q", raw_path))
        for source_index, stored_index in enumerate(saved[:depth]):
            if stored_index >= block_count or used & (1 << stored_index):
                raise ValueError("saved target permutation prefix is invalid")
            seed = mixer_block_seed(source_index, chain_value, entry_context)
            start = stored_index * 64
            plain = inverse_mixer_block(mixed[start:start + 64], seed)
            state = advance_lzss_block(state, plain)
            path.append(stored_index)
            used |= 1 << stored_index
            plain_output.extend(plain)
        print(f"resumed validated target prefix at depth {len(path)}")

    for source_index in range(len(path), depth):
        seed = mixer_block_seed(source_index, chain_value, entry_context)
        decrypted = inverse_mixer_blocks(mixed, seed)
        forced = 1089 if source_index == block_count - 1 else None
        best = None
        second = None
        valid_count = 0
        stored_indices = (forced,) if forced is not None else range(block_count)
        for stored_index in stored_indices:
            if used & (1 << stored_index):
                continue
            start = stored_index * 64
            plain = decrypted[start:start + 64]
            try:
                next_state = advance_lzss_block(state, plain)
            except ValueError:
                continue
            if next_state.done and source_index != block_count - 1:
                continue
            if source_index == block_count - 1 and not next_state.done:
                continue
            valid_count += 1
            item = (next_state.out_len, stored_index, next_state, plain)
            if best is None or item[:2] < best[:2]:
                second = best
                best = item
            elif second is None or item[:2] < second[:2]:
                second = item
        if best is None:
            raise ValueError(
                f"target ranked search exhausted at depth {source_index + 1}"
            )
        out_len, stored_index, state, plain = best
        used |= 1 << stored_index
        path.append(stored_index)
        plain_output.extend(plain)
        if source_index < 8 or (source_index + 1) % 16 == 0 or state.done:
            gap = "none" if second is None else str(second[0] - out_len)
            print(
                f"depth={source_index + 1} valid={valid_count} "
                f"chosen={stored_index} out={out_len} second_gap={gap} "
                f"beam_limit={beam_width}",
                flush=True,
            )
        if (source_index + 1) % 64 == 0:
            save_target_prefix(path, plain_output)

    save_target_prefix(path, plain_output)
    print(
        f"saved target ranked prefix: blocks={len(path)} "
        f"bytes={len(plain_output)} out={state.out_len} done={state.done}"
    )
    return tuple(path), bytes(plain_output), state


def rs_systematic_test(mixed, header, record_length):
    block_count = len(mixed) // 64
    context = make_mixer_context(FAKE_MIXER_FIELDS)
    permutation = make_local_permutation(block_count, b"quiz", 4, MIXER_TABLE)
    packets = inverse_mixer_entry(
        mixed, len(mixed), 4, context, permutation
    )
    encoded, _ = decompress_lzss(packets)
    scrambled = inverse_rs(encoded, record_length)
    systematic = encoded[:record_length] == scrambled[:record_length]
    print(f"RS systematic prefix: {systematic}")
    return systematic


def main():
    parser = argparse.ArgumentParser(description="Decode the repaired OAS challenge archive")
    parser.add_argument("archive", nargs="?", default="quiz_repaired.oas")
    parser.add_argument("--oracle-self-test", action="store_true")
    parser.add_argument("--target-zero-anchors", action="store_true")
    parser.add_argument("--target-first-block-census", action="store_true")
    parser.add_argument("--target-lzss-beam", action="store_true")
    parser.add_argument("--rs-systematic-test", action="store_true")
    parser.add_argument("--perm-search-self-test", action="store_true")
    parser.add_argument("--entry", type=int, default=0)
    parser.add_argument("--beam", type=int, default=128)
    parser.add_argument("--depth", type=int, default=128)
    parser.add_argument("--stop-prefix", type=int)
    args = parser.parse_args()

    if args.oracle_self_test:
        oracle_self_test()
        return 0

    archive = Path(args.archive).read_bytes()
    header = parse_header(archive)
    entries = global_unshuffle(archive, header)
    print(
        f"header: entries={header.entry_count} blocks={header.total_blocks} "
        f"seed_a=0x{header.seed_a:016x} seed_b=0x{header.seed_b:016x}"
    )
    print("global PAYL unshuffle: OK")
    print(f"entry sizes: {', '.join(str(len(entry)) for entry in entries)}")
    packet_length, chain_value, record_length, real_a8, real_context, decoys = (
        probe_target_context(entries, header)
    )
    print(
        f"target context: fake_packets={packet_length} chain={chain_value} "
        f"record_stream={record_length} real_a8=0x{real_a8:016x}"
    )
    print(
        "validated decoy records: "
        + ", ".join(f"{name.decode(errors='replace')} ({len(data)})"
                    for name, data in decoys)
    )
    print(
        "target real fields: "
        + ", ".join(
            f"{name}=0x{struct.unpack_from('<Q', real_context, offset)[0]:016x}"
            for name, offset in (("f98", 0x98), ("a0", 0xA0),
                                 ("a8", 0xA8), ("b0", 0xB0),
                                 ("b8", 0xB8))
        )
    )
    if args.target_zero_anchors:
        target_zero_anchor_diagnostic(entries[1], chain_value, real_context)
        return 0
    if args.target_first_block_census:
        target_first_block_census(entries[1], chain_value, real_context)
        return 0
    if args.target_lzss_beam:
        depth = args.depth
        if args.stop_prefix is not None:
            depth = (args.stop_prefix + 63) // 64
        target_lzss_ranked_search(
            entries[1], chain_value, real_context, depth, args.beam
        )
        return 0
    if args.rs_systematic_test:
        rs_systematic_test(entries[0], header, record_length)
        return 0
    if args.perm_search_self_test:
        permutation_search_self_test(entries, args.beam, args.depth, args.entry)
        return 0
    raise SystemExit(
        "target real-entry permutation remains unresolved"
    )


if __name__ == "__main__":
    raise SystemExit(main())
