#!/usr/bin/env python3
import argparse
import hashlib
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


def decode_target_real(entries, header, chain_value, real_context):
    permutation_data = Path("target_perm_prefix.bin").read_bytes()
    block_count = len(entries[1]) // 64
    if len(permutation_data) != block_count * 8:
        raise ValueError("target permutation file does not contain every block")
    permutation = struct.unpack(f"<{block_count}Q", permutation_data)
    packets = inverse_mixer_entry(
        entries[1], len(entries[1]), chain_value, real_context, permutation
    )
    encoded, packet_length = decompress_lzss(packets)

    valid = []
    for candidate in candidate_rs_input_lengths(len(encoded), header.seed_a):
        try:
            scrambled = inverse_rs(encoded, candidate)
            record_stream = inverse_scramble(
                scrambled,
                header.seed_a ^ candidate ^ SCRAMBLE_REAL_CONST,
            )
            valid.append((candidate, unpack_records(record_stream, header.seed_a)))
        except ValueError:
            continue
    if len(valid) != 1:
        raise ValueError(f"expected one valid real record stream, found {len(valid)}")

    record_length, records = valid[0]
    output_dir = Path("recovered_real")
    output_dir.mkdir(exist_ok=True)
    expected_names = set()
    for raw_name, data in records:
        name = raw_name.decode("ascii")
        if Path(name).name != name or name in expected_names:
            raise ValueError(f"unsafe or duplicate record name: {name!r}")
        expected_names.add(name)
        path = output_dir / name
        path.write_bytes(data)
        if data.startswith(b"#!"):
            path.chmod(0o755)
    actual_names = {path.name for path in output_dir.iterdir() if path.is_file()}
    if actual_names != expected_names:
        raise ValueError("recovered_real contains files outside the validated record set")

    flag_script = (output_dir / "flag.py").read_bytes()
    marker = b'print("v1t{" + h.hexdigest() + "}")'
    if marker not in flag_script:
        raise ValueError("validated records do not contain the expected flag generator")
    digests = sorted(
        hashlib.sha3_512((output_dir / name).read_bytes()).digest()
        for name in expected_names
    )
    digest = hashlib.sha3_512()
    for value in digests:
        digest.update(value)
    flag = f"v1t{{{digest.hexdigest()}}}"
    return packet_length, len(encoded), record_length, records, flag


def main():
    parser = argparse.ArgumentParser(description="Decode the repaired OAS challenge archive")
    parser.add_argument("archive", nargs="?", default="quiz_repaired.oas")
    parser.add_argument("--oracle-self-test", action="store_true")
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
    real_packet_length, real_rs_length, real_record_length, records, flag = (
        decode_target_real(entries, header, chain_value, real_context)
    )
    print(
        f"target real decode: packets={real_packet_length} rs={real_rs_length} "
        f"record_stream={real_record_length}"
    )
    print(
        "validated real records: "
        + ", ".join(
            f"{name.decode(errors='replace')} ({len(data)})"
            for name, data in records
        )
    )
    print(f"verified flag: {flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
