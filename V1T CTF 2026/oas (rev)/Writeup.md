---
title: "OAS"
category: reverse
difficulty: hard

---

# OAS

**Final flag:**

```text
v1t{0555c2b516f9c4db8c0f64c224ef99e4d0d390855ff5b9d2548706d7027f59d341fe35d127ff949d65149cc8a39f42e97e5f4cd80a428f80c51d012b853db87a}
```

## How to Read This Writeup

This writeup is basically the path I used to reconstruct the solve, not just a short summary of the final steps. I wanted it to be reproducible from the original files: `oas`, `quiz.oas`, and the Dockerfile. I included the commands that actually mattered, and I also kept the terminal outputs that helped confirm whether I was going in the right direction. 

The general process was:

1. **Figure out that `oas` was an encoder, not a decoder.** The Dockerfile ran `./oas quiz`, so the missing `quiz` file was what got packed into `quiz.oas`.
2. **Check if the archive was actually damaged.** The long zero runs looked way too structured to just be normal ciphertext or padding.
3. **Use the archive's repair data to fix the damaged bytes.** The CAPS records were basically XOR equations over PAYL blocks.
4. **Build a known-good oracle before decoding the real target.** A same-shape fake archive gave known boundaries for LZSS, RS, the scrambler, and the record format.
5. **Decode entry 0 first, but don't trust it too much.** It gave useful context values, but its `flag.py` was just a decoy.
6. **Use LZSS validity to recover the final block permutation.** The real entry's permutation depended on plaintext I did not have, so I treated the block order like an assignment problem.

## Challenge

> The file was lost during the download due to a network issue. Please recover the file and print the flag.

The challenge gave a stripped Linux binary named `oas`, a damaged archive named `quiz.oas`, and a Dockerfile showing how the archive was created. There was no remote server or anything like that.

## Summary

`oas` ended up being an encoder for a custom archive format. The downloaded archive had two main problems. First, 14,328 PAYL bytes had been replaced with long zero runs. Second, one byte inside the CAPS repair data was also wrong. The CAPS records had redundant XOR equations, so after recovering the equation schedule and the payload mask from the encoder, I could solve the missing PAYL bytes with Gaussian elimination.

After repairing the archive, there were still a lot of layers left. The final decoder had to undo:

1. a masked 64-byte header with integrity checks;
2. a global Fisher-Yates permutation of 2,514 PAYL blocks;
3. an entry-local block permutation that depended on plaintext;
4. a nine-round 64-byte block mixer;
5. an LZSS packet stream;
6. a 17-data/6-parity GF(256) erasure layer;
7. a five-round byte permutation and feedback scrambler;
8. a stateful record format with filenames and payloads.

The hardest part was definitely the real entry's plaintext-dependent block permutation. For each source block index, I decrypted every unused stored block using that source index's mixer seed. Then I rejected blocks that could not continue a valid LZSS stream and picked the valid candidate that produced the smallest decompressed output. That recovered the record stream, which had ten small ELF files and a real `flag.py`. Running that script printed the flag.

# AI Assistance

AI tools were used while solving this challenge, mainly to make the reverse-engineering process faster and to help organize everything as the solve got more complicated. The challenge still needed a lot of actual checking though. I had to understand the archive format, test different ideas, figure out which paths were wrong, and make sure the final flag came from the recovered files instead of just some random guess. AI was also used in this writeup.

AI was most useful for:

- writing and cleaning up Python scripts for parsing the archive, fixing corrupted bytes, reversing encoding layers, and checking intermediate outputs
- helping make sense of GDB traces, memory dumps, and disassembly around the custom mixer, local permutation, LZSS decoder, RS-like layer, scrambler, and record format
- suggesting next steps when something failed, like checking whether the entry-0 `flag.py` was a decoy or treating the entry-1 permutation like an assignment problem
- helping write and debug small helper tools, including the incremental LZSS state machine and the C batch mixer that made candidate testing a lot faster


## Files and Tooling

The starting directory looked like this:

```text
$ find . -maxdepth 1 -type f -printf '%f\t%s bytes\n' | sort
Dockerfile.txt                         194 bytes
oas                                102176 bytes
quiz.oas                          830552 bytes
```

These were the original challenge file hashes:

```text
$ sha256sum oas quiz.oas Dockerfile
e6021dcd09e2c3dc6abab4730c07e4fcf485b7c4a95c7622137e3ee86753b941  oas
b8feb78310d9eba5e38819be397c19a049c9b670dd892a45be81592d5f3a4389  quiz.oas
726251b86b92a2976e9dd36722cc1f92d005fa9a3fb23a72ed5c436649f6f54c  Dockerfile
```

The main tools I used were:

- `file`, `xxd`, `strings`, `binwalk`, and `checksec` for the first pass;
- `objdump` and `radare2` for static analysis;
- GDB Python breakpoints and memory dumps for encoder oracles;
- Python for parsing, GF(256), Gaussian elimination, and decoding;
- a small C shared library to speed up the mixer search.

The final historical scripts from the solve workspace had these hashes:

```text
$ sha256sum solve.py solve_perm.py mixer_batch.c notes.md
fdc82e289afeb702510aff75a6db5a1107135f339a4f762ca2a5a14890376838  solve.py
ac0639b83a39fb18d998026ceb2d920c63bd264ccf46915bf45393587e84db58  solve_perm.py
5c4ff95ec341c3723ced28757351d6d8e64e3952cd59b82499026dc00b8f47c5  mixer_batch.c
9cc333146e4e560d0a3101eead2dff4711730fb7507fead07f2302b8a145482b  notes.md
```

There were also some GDB helper scripts under `historical_gdb/`. The important ones were `oas_tail_log.gdb`, `oas_tail_target_keystream_preq2.gdb`, and `oas_tail_self_keystream.gdb`, which were used for the CAPS schedule and the corrected keystream oracle.

Some binary checkpoints like `quiz_repaired.oas`, `target_perm_prefix.bin`, and `target_lzss_prefix.bin` were generated during the solve. They were not original challenge files, but I kept the hashes and terminal output so the process could still be recreated.

## 1. Initial Triage

I started by checking whether this was some normal damaged archive format. It was not.

```bash
file *
checksec --file=oas
binwalk quiz.oas
strings -a -n 4 oas | head -100
strings -a -n 4 quiz.oas | head -100
xxd -g1 -l 256 quiz.oas
xxd -g1 -s -256 quiz.oas
```

Important output:

```text
oas:      ELF 64-bit LSB executable, x86-64, dynamically linked, stripped
quiz.oas: data

RELRO       STACK CANARY      NX enabled   PIE       Symbols
No RELRO    No canary found   Yes          No PIE    No Symbols
```

`quiz.oas` had entropy around `7.973301`, no useful `binwalk` signatures, and no direct `v1t{` string. There were also Zone Identifier files, but those were just Windows download metadata and did not matter.

The Dockerfile was the first really useful clue:

```dockerfile
FROM ubuntu:18.04@sha256:152dc042452c496007f07ca9127571cb9c29697f42acbfad72324b2bb2e43c98

WORKDIR /v1t

COPY oas ./oas
COPY quiz ./quiz

RUN chmod +x ./oas
RUN ./oas quiz

CMD ["./oas", "quiz"]
```

This showed that `quiz` was the original input, and `quiz.oas` was created by running the encoder. So running `./oas quiz` was not going to decode anything because `quiz` was missing. Also, if I renamed `quiz.oas` to `quiz` or ran `./oas quiz.oas`, it just encoded the archive again.

Static analysis also found strings like `%s.oas`, `%s/%s`, `opendir`, `readdir`, `qsort`, `open`, `read`, and `write`, which made it look like a directory packer. The binary also had special `.py` handling and generated Python- and ELF-looking records.

At one point I noticed that the total size could be written as `24 + 12977*64`. That was not the real format, but it was still a decent hint that 64-byte blocks mattered. Later reversing showed the real layout.

## 2. Reverse the Archive Layout

I focused on the writer and the transformation functions:

```bash
objdump -d -M intel --start-address=0x40d010 --stop-address=0x40d7a0 oas
objdump -d -M intel --start-address=0x407800 --stop-address=0x407a70 oas
objdump -d -M intel --start-address=0x409cf0 --stop-address=0x40a160 oas
objdump -d -M intel --start-address=0x40a130 --stop-address=0x40a860 oas
r2 -Aq -c 'afl' -c 's main; pdf' oas
```

The `r2` decompiler command did not work because `r2dec` was not installed, so I ended up using disassembly, GDB, and small Python replicas instead. The final layout was:

```text
offset       size                  purpose
0x000000     64                    masked header
0x000040     2514 * 64 = 160896    PAYL/direct blocks
0x0274c0     7609 * 88 = 669592    CAPS repair records
total                              830552 bytes
```

Each CAPS record looked like this:

```text
q0:      8 bytes
q1:      8 bytes
q2:      8 bytes
payload: 64 bytes
```

The header is XORed with a fixed 64-byte mask. Its integrity equations recover the entry count, block count, and two global seeds. The important parser code was:

```python
plain = bytes(a ^ b for a, b in zip(archive[:64], HEADER_MASK))
words = struct.unpack("<8Q", plain)
count = words[0] ^ 0x91A7F06D3C2B5E18
total = words[1] ^ sm64(0xBDB86DE98BCD0D12 ^ count)
seed_a = words[3] ^ sm64(0x47D3E2A91CB8056F ^ words[2])
seed_b = words[4] ^ sm64(0xD819AB344CE60771 ^ words[1] ^ words[3])
```

The decoded target values were:

```text
entry_count = 2
total_blocks = 2514
blocks per entry = 1257
seed_a = 0x0867944c73fc1153
seed_b = 0x40fe2443a3750795
```

## 3. Identify the Download Damage

Since the prompt said there was a network issue, I scanned the PAYL section for long zero runs:

```python
from collections import Counter
from pathlib import Path

data = Path("quiz.oas").read_bytes()
runs = []
i = 0
while i < len(data):
    if data[i] != 0:
        i += 1
        continue
    j = i
    while j < len(data) and data[j] == 0:
        j += 1
    if j - i >= 8:
        runs.append((i, j - i))
    i = j

print(len(runs), sum(length for _, length in runs))
print(Counter(length for _, length in runs))
```

Output:

```text
465 14328
Counter({31: 448, 32: 9, 19: 8})
```

The first runs started at offsets `261`, `517`, `965`, and `1221`. The pattern was too regular to ignore. A lot of the zero runs were 31 bytes long and happened at similar spots inside 64-byte blocks, so it looked like erased ciphertext bytes, not normal padding.

## 4. Recover the CAPS Equation Schedule

The CAPS records were the repair system. I used GDB to trace the encoder's CAPS loop and log which logical block indices were used in each record:

```bash
gdb -q -nx -batch -x /tmp/oas_tail_log.gdb ./oas
```

The log was converted into `/tmp/oas_tail_schedule.tsv`. It covered every CAPS record:

```text
records 7609 minmax 0 7608 entries 22669
arity distribution:
  2 blocks: 3827 records
  3 blocks: 1313 records
  4 blocks: 1265 records
  5 blocks: 1203 records
  1 block:     1 record
missing 0
```

The arity was also encoded in the metadata:

```python
arity = q1 ^ sm64(q0)
```

After removing the payload mask, each CAPS payload was just the XOR of some scheduled 64-byte logical blocks:

```python
raw_caps[record] = XOR(logical_block[i] for i in schedule[record])
```

So each CAPS record gave one XOR equation per byte position.

## 5. Generate the Correct CAPS Payload Keystream

The CAPS payload was also masked by a stream that depended on `q0` and `q2`. To recover that mask, I used a same-shape encoder run as an oracle. The idea was to make GDB replace the source payload with zero bytes, so the output payload would just be the mask.

The first oracle was close but still wrong. It matched `q0` and `q1` for all 7,609 records, but `q2` differed for 745 records:

```text
q0 mismatches 0 []
q2 mismatches 745 [3, 33, 46, 63, 64, 67, 71, 72, 76, 82]
q1 mismatches 0 []
```

After checking the disassembly and comparing controlled runs, I found a post-mask `q2` toggle:

```python
toggled = ((q0 & 63) == 42) or (arity == 5 and (q0 & 7) == 3)
pre_q2 = stored_q2 ^ (0xFEEDFACE if toggled else 0)
seed = 0x40FE2443A3750795 ^ q0 ^ pre_q2
```

That predicate matched exactly the 745 mismatches. After that, the corrected GDB hook patched the pre-toggle `q2` and seed, then zeroed the 64-byte input at the CAPS masking point. This produced `/tmp/oas_keystream_oracle2/quiz.oas` with the target metadata and target-specific payload masks.

## 6. Solve the Missing PAYL Bytes

I marked the unknown bytes from the 465 long zero runs. One early mistake was indexing equations in archive PAYL order, which gave thousands of inconsistencies. A clean self-oracle showed that CAPS uses globally unshuffled logical order instead.

The global permutation was a Fisher-Yates shuffle:

```python
seed = seed_a ^ seed_b ^ 0x4749445052504449
perm = list(range(total_blocks))
for i in range(total_blocks):
    j = i + sm64(i ^ seed) % (total_blocks - i)
    perm[i], perm[j] = perm[j], perm[i]
```

So the damaged archive bytes had to be mapped from archive block positions back to logical block indices before solving. For each byte position `p` in a 64-byte block, I built equations like this:

```python
row = 0
rhs = raw_caps[record][p]
for logical_block in schedule[record]:
    if byte_is_unknown(logical_block, p):
        row ^= 1 << variable_number(logical_block, p)
    else:
        rhs ^= known_logical_block[logical_block][p]
```

Then I reduced the rows using XOR Gaussian elimination. The coefficients were binary, but each right-hand side was a full byte, so XORing rows solved all eight bit planes at the same time. All 14,328 erased bytes were full-rank and uniquely determined.

After the direct repair, one CAPS record still failed:

```text
solved 14328 under_count 0
eq failures [4615]
```

This ended up not being a PAYL byte issue. CAPS record 4615 had one bad byte in its own payload:

```text
file offset 567105
old byte 0x78
required byte 0x75
```

After applying that correction, everything verified:

```text
marked long runs 465 unknown bytes 14328
direct solved 14328 under_count 0
residuals before tail patch [(4615, 1, 223, 210)] count 1
patched tail record 4615 pos 1 off 567105 old 0x78 new 0x75
residuals after tail patch [] count 0
wrote /tmp/quiz_repaired.oas
98b9c17a21eca5ed3e3a63d733e21b0460c90639fc6169cb59645b6eaf28a7c7  /tmp/quiz_repaired.oas
long zero runs >=8 0 [] []
```

This was a big checkpoint. At this point, all 7,609 CAPS equations passed and the long zero holes were gone.

## 7. Build a Same-Shape Decoder Oracle

Since `oas` only encoded files, I used controlled inputs to learn the inverse of each layer. A size probe showed that 61,081 bytes of `A` produced the same archive shape as the target: 2,514 blocks total and 1,257 blocks per entry.

Then GDB dumped the important boundaries:

```text
/tmp/tgtshape_out1.bin                  mixed real-entry blocks, 80448 bytes
/tmp/tgtshape_perm1.bin                 oracle local permutation
/tmp/tgtshape_entries_real_blockctx.bin entry contexts
/tmp/tgtshape_real_plus68.bin           pre-LZSS bytes, 80431 bytes
/tmp/tgtshape_real_plus60.bin           post-LZSS/RS bytes, 71510 bytes
/tmp/tgtshape_real_40a130_input.bin     pre-scrambler bytes, 61097 bytes
/tmp/tgtshape_real_pre400f60.bin        record bytes, 61097 bytes
```

The oracle self-test had to reproduce every stage exactly and recover the original `A` input:

```bash
python3 solve.py --oracle-self-test
```

Output:

```text
oracle self-test: header, unshuffle, LZSS, RS, scrambler, records OK
```

This was important because a partial decode could look believable and still be wrong. I wanted every inverse layer to have a known byte-for-byte answer before using it on the real archive.

## 8. Reverse the Downstream Layers

### 8.1 Global PAYL unshuffle

`global_unshuffle()` applies the inverse of the header-seeded Fisher-Yates permutation. After that, it splits the 2,514 logical blocks into two 80,448-byte entries. Entry 0 is the generated decoy stream, and entry 1 is the real stream.

### 8.2 The `0x408650` block mixer

Each source block gets a seed based on the source index, the previous entry's chain value, five context qwords, an eight-qword table, and a lazy global seed:

```python
state = chain ^ MIXER_LAZY_SEED ^ a0 ^ f98
state ^= rol64(a8, 9) ^ rol64(b0, 17)
state ^= rol64(table[0], 1) ^ block_index ^ b8
state ^= table[block_index & 7]
state = sm64(state)
for t in range(1, 8):
    state = sm64(
        rol64(table[t], t + 1)
        ^ table[(block_index + t) & 7]
        ^ state
    )
```

The mixer XORs a per-position stream into a 64-byte block and then runs nine rounds of operations on the lower and upper 32-byte halves. To invert it, I ran the rounds backward from 8 to 0, undid the upper-half XOR, undid the lower-half additions, and then removed the position stream.

The local permutation direction was easy to mess up. The verified meaning was:

```text
source block j -> stored block permutation[j]
```

### 8.3 LZSS

The LZSS control bytes are masked using the absolute compressed offset:

```python
control = data[offset] ^ (sm64(0x4C5A535344495233 ^ offset) & 0xff)
```

Each control byte has eight bits. A zero bit means a literal, and a one bit means a two-byte reference. A reference is decoded like this:

```python
token = low | high << 8
if token == 0xffff:
    end_stream()
length = (token >> 12) + 3
distance = (token & 0xfff) + 1
```

The copy has to be byte-by-byte because overlapping backreferences are allowed.

### 8.4 Reed-Solomon-like erasure layer

The next layer uses 17 data columns and 6 parity columns over GF(256), with polynomial `0x11d`. The columns are serialized in this order:

```python
RS_ORDER = [0, 7, 14, 21, 5, 12, 19, 3, 10, 17, 1, 8,
            15, 22, 6, 13, 20, 4, 11, 18, 2, 9, 16]
```

The archive drops a seed-dependent suffix of the column stream. The decoder has to try possible original lengths, reconstruct missing data columns from complete parity columns by inverting a GF(256) matrix, and then let the later record trailer choose the one valid length.

### 8.5 Byte scrambler

Function `0x400f60` runs five rounds. To reverse it, I went in reverse round order and undid:

1. a backward XOR-feedback pass;
2. a seed-derived byte permutation;
3. a forward additive-feedback pass.

The real and decoy branches use different seed constants:

```python
real_seed  = seed_a ^ input_length ^ 0x7265616C5F627261
decoy_seed = seed_a ^ input_length ^ 0x6465636F795F6272
```

### 8.6 Record unpacking

The final stream stores a masked name length, masked payload length, encrypted filename, encrypted payload, and a state update for each record. The decoder rejects invalid names and lengths, and then verifies a two-byte trailer:

```python
expected_trailer = sm64(len(records) ^ state) & 0xffff
```

That trailer was a strong validator when testing the possible RS input lengths.

## 9. Decode Entry 0 and Reject the Decoy

Entry 0 uses chain value `4`, which is the length of the filename `quiz`. Its local permutation can be generated directly from `b"quiz"`, and its context is fixed.

The partial target decoder produced:

```text
target context: fake_packets=74228 chain=65999 record_stream=61674
validated decoy records:
  03e7c2a91b5d8f40 (6120)
  16af9042d83c7b51 (6120)
  ... eight more 6120-byte records ...
  flag.py (195)
```

The ten numbered files were small ELF programs. The 195-byte `flag.py` was just one comment line with a 128-character hex digest. It ran with no output, and none of the entry-0 files had a verified flag pattern. So this branch was a decoy.

Entry 0 still gave two values needed for entry 1:

```text
entry 1 chain value = len(entry0_rs) = 65999
entry 1 a8 = wave_dir(entry0_rs, 65999, MIXER_TABLE, 1 ^ 1257)
          = 0x750835934041c232
```

## 10. Recover the Target Entry-1 Context

The remaining entry fields were not just written directly somewhere. To get them, I replayed the encoder under GDB while injecting `/tmp/target_fake_rs.bin`, which was the exact decoded target entry-0 RS stream, before the metadata callbacks.

The callback order was:

```text
0x40aea0 -> a0
0x40ad40 -> a8
0x40a840 -> b0
0x406fb0 -> b8
```

That produced the full target context:

```text
f98 = 0xbfe12dc426c20772
a0  = 0xa83b423ee014c752
a8  = 0x750835934041c232
b0  = 0x7435ee6517001031
b8  = 0xeea1176a5255accd
chain = 65999
```

The calculated `a8` matched the replayed value exactly, which was a good sanity check.

## 11. Discover Why the Real Permutation Could Not Be Reused

The local shuffle is generated like this:

```python
for i in range(block_count):
    other = i + wave_dir(data, length, table, i) % (block_count - i)
    permutation[i], permutation[other] = permutation[other], permutation[i]
```

Controlled all-`A` and random oracles had different entry-1 permutations even though the lengths and archive shapes were the same. GDB showed why: `wave_dir` read a 65,999-byte global span:

```text
bytes 0..6751:      globals and metadata
bytes 6752..65998:  59247 bytes of the original source payload verbatim
```

So the target permutation was actually keyed by unavailable plaintext. It could not be reconstructed just from the header or CAPS metadata.

Two obvious guesses failed right away:

```text
same-shape all-A permutation:
  ValueError: invalid LZSS distance 3559 at output offset 1

decoy-directory permutation forced to 1257 blocks:
  ValueError: invalid LZSS distance 2846 at output offset 1
```

I also checked whether applying the binary's decoy transform twice would act like an inverse. It did not. Only `237 / 61081` bytes matched the known all-`A` source.

## 12. Turn LZSS Validation into a Permutation Oracle

For each source position `j`, the mixer seed is known even if the matching stored block is not. That means every source/stored pairing can be tested:

```python
seed_j = mixer_block_seed(j, 65999, target_real_context)
candidate_plain = inverse_mixer_block(entry1_mixed[k], seed_j)
```

The correct block sequence has to parse as one continuous LZSS stream. I implemented an incremental 64-byte LZSS transducer with this state:

```python
@dataclass(frozen=True)
class LZSSBoundaryState:
    out_len: int
    tail: bytes              # last at most 4096 output bytes
    control: int | None
    bit_index: int
    ref_low: int | None      # split reference token at a block boundary
    done: bool
    end_offset: int | None
    source_offset: int       # needed for control-byte masking
```

It rejected:

- a distance larger than the current output;
- truncated or malformed tokens;
- reused stored blocks;
- a terminator before the final source block;
- nonzero bytes after a terminator;
- a final block without a terminator.

The ranking code was basically:

```python
for source_index in range(block_count):
    seed = mixer_block_seed(source_index, chain, context)
    decrypted = inverse_mixer_blocks(all_stored_blocks, seed)
    candidates = []

    for stored_index in unused_stored_indices:
        plain = decrypted[stored_index * 64:(stored_index + 1) * 64]
        try:
            state2 = advance_lzss_block(state, plain)
        except ValueError:
            continue
        candidates.append((state2.out_len, stored_index, state2, plain))

    _, chosen, state, plain = min(candidates)
    mark_used(chosen)
    save_prefix(chosen, plain)
```

The CLI still had the old name `--target-lzss-beam`, but the successful target path was really a calibrated rank-1 search. I did try a full width-128 branching search, but it was too slow in pure Python.

## 13. Validate the Ranking on the Solved Entry

Before trusting that heuristic on the real entry, I tested it on entry 0 while hiding the known next mapping from the candidate generation. At every tested depth, the correct next block had the smallest resulting decompressed length:

```bash
python3 solve_perm.py --perm-search-self-test --entry 0 --beam 128 --depth 128
```

Selected output:

```text
depth=1 valid=1 correct_rank=1 out=56
depth=16 valid=1 correct_rank=1 out=910
depth=32 valid=1 correct_rank=1 out=1820
depth=48 valid=5 correct_rank=1 out=2730
depth=64 valid=167 correct_rank=1 out=3640
depth=80 valid=1178 correct_rank=1 out=4552
depth=128 valid=1130 correct_rank=1 out=7284
entry-0 permutation search self-test: correct local path retained through depth 128; worst_rank=1
```

The correct compressed blocks usually produced around 56-57 output bytes per 64 input bytes. Random blocks that were syntactically valid usually decoded into long references and made the output grow much more. That is why the smallest-output ranking worked.

## 14. Find the Target Anchors

I added the exact forward mixer and checked it against the oracle. Testing an all-zero plaintext block under every source seed did not find any full-zero source blocks, but it did find one strong partial anchor:

```bash
python3 solve_perm.py --target-zero-anchors
```

```text
full-zero anchors: 0
first source index: none
last source index: none
contiguous suffix: False
partial zero-suffix candidates:
  source=1256 stored=1089 zero_suffix=59 tail16=00000000000000000000000000000000
```

The first source block also had exactly one valid assignment:

```bash
python3 solve_perm.py --target-first-block-census
```

```text
target first-block survivors: 1
  stored=121 first16=347c5898b9142365747ec87fad31dbdf
  out=56 control=0 bit=0 ref_low=None done=False
```

## 15. Accelerate and Recover the Full Permutation

Trying all 1,257 stored blocks for every source position was too slow with the Python mixer. So I wrote `mixer_batch.c`, which implemented the already-verified inverse mixer in C and exposed one function through `ctypes`:

```c
void inverse_mixer_blocks(const uint8_t *input, uint8_t *output,
                          size_t block_count, uint64_t seed);
```

I compiled it with:

```bash
cc -O3 -shared -fPIC -o mixer_batch.so mixer_batch.c
```

The oracle test compared the C output byte-for-byte with the Python inverse. After that, the entry-0 depth-128 calibration dropped from several minutes to around eight seconds.

Then I checkpointed the target search in stages:

```bash
python3 solve_perm.py --target-lzss-beam --beam 256 --depth 128
python3 solve_perm.py --target-lzss-beam --beam 512 --stop-prefix 59247
python3 solve_perm.py --target-lzss-beam --beam 512 --depth 1257
```

The first 128 blocks looked similar to entry 0:

```text
depth=1 valid=1 chosen=121 out=56
depth=2 valid=1 chosen=645 out=113
depth=32 valid=1 chosen=654 out=1820
depth=48 valid=2 chosen=278 out=2730 second_gap=139
depth=64 valid=169 chosen=806 out=3640 second_gap=88
depth=128 valid=1129 chosen=58 out=7282 second_gap=79
saved target ranked prefix: blocks=128 bytes=8192 out=7282 done=False
```

The 59,247-byte checkpoint finished at 926 blocks and 52,693 LZSS output bytes. The final run ended at the anchored block:

```text
depth=1232 valid=26 chosen=17 out=70104 second_gap=92
depth=1248 valid=10 chosen=11 out=71015 second_gap=124
depth=1257 valid=1 chosen=1089 out=71472 second_gap=none
saved target ranked prefix: blocks=1257 bytes=80448 out=71472 done=True
```

The complete mapping was saved as `target_perm_prefix.bin`, and the pre-LZSS bytes were saved as `target_lzss_prefix.bin`.

## 16. Final Decode and Record Validation

The recovered stream produced:

```text
LZSS bytes consumed: 80389
LZSS output / RS bytes: 71472
candidate RS input lengths: [62015, 65488]
```

Only `62015` survived the inverse scrambler and record trailer:

```text
VALID 62015
  03e7c2a91b5d8f40 (6120)
  16af9042d83c7b51 (6120)
  28bd6f10e4a93c75 (6120)
  3c91be7850a24fd6 (6120)
  4f02d9ac1378e65b (6120)
  5a77c0e21d9348bf (6120)
  6d4b8e2190f3ac57 (6120)
  7e105bca49d2863f (6120)
  8b39f6d042a1ce75 (6120)
  9cf14a72e0d6538b (6120)
  flag.py (536)

65488 rejected: invalid record name length 53300
```

The real `flag.py` was:

```python
#!/usr/bin/env python3
import hashlib
import os

h = hashlib.sha3_512()
root = os.path.dirname(os.path.abspath(__file__))
items = []

for name in os.listdir(root):
    p = os.path.join(root, name)
    if os.path.isfile(p):
        g = hashlib.sha3_512()
        with open(p, "rb") as f:
            while True:
                b = f.read(65536)
                if not b:
                    break
                g.update(b)
        items.append(g.digest())

for d in sorted(items):
    h.update(d)

print("v1t{" + h.hexdigest() + "}")
```

It hashes every recovered file with SHA3-512, sorts the binary digests, hashes that concatenation, and prints it as the flag.

## 17. Final Verification

Once the archive was repaired and the full permutation was recovered, the main decoder command was:

```bash
python3 solve.py
```

Recorded output:

```text
header: entries=2 blocks=2514 seed_a=0x0867944c73fc1153 seed_b=0x40fe2443a3750795
global PAYL unshuffle: OK
entry sizes: 80448, 80448
target context: fake_packets=74228 chain=65999 record_stream=61674 real_a8=0x750835934041c232
validated decoy records: ... flag.py (195)
target real fields: f98=0xbfe12dc426c20772, a0=0xa83b423ee014c752,
                    a8=0x750835934041c232, b0=0x7435ee6517001031,
                    b8=0xeea1176a5255accd
target real decode: packets=80389 rs=71472 record_stream=62015
validated real records: ... flag.py (536)
verified flag: v1t{0555c2b516f9c4db8c0f64c224ef99e4d0d390855ff5b9d2548706d7027f59d341fe35d127ff949d65149cc8a39f42e97e5f4cd80a428f80c51d012b853db87a}
```

The recovered script printed the same thing independently:

```bash
cd recovered_real
./flag.py
```

```text
v1t{0555c2b516f9c4db8c0f64c224ef99e4d0d390855ff5b9d2548706d7027f59d341fe35d127ff949d65149cc8a39f42e97e5f4cd80a428f80c51d012b853db87a}
```




## Flag

```text
v1t{0555c2b516f9c4db8c0f64c224ef99e4d0d390855ff5b9d2548706d7027f59d341fe35d127ff949d65149cc8a39f42e97e5f4cd80a428f80c51d012b853db87a}
```
