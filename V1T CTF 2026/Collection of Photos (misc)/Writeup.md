# CTF Writeup: New Ways to Store my CP (Collection of Photos)

## Overview

This challenge started with a Pastebin that had a normal YouTube link, a bunch of blank space, and then some weird text at the bottom. At first, the YouTube video just looked like TV static, but it was actually storing data inside the video frames.

The solve ended up having three main parts:

1. Getting the password from invisible Unicode characters in the Pastebin.
2. Decoding the hidden data from the YouTube video frames.
3. Decrypting part of the recovered encrypted data to get the flag.

The final flag was:

```text
v1t{Quack_Quack_Quack_1_l0ve_Qu4cking_r34l_much_br}
```

---

## Step 1: Finding the Hidden Pastebin Payload

The Pastebin had one obvious YouTube link, then a really large blank area. After the blank space, there was this suspicious line:

```text
Yo u r here? That's awesome. I wanna show u my new cloak my friend R4wr bought me last week (and a little gift 4 u also):
MY [invisible chars] NEW CLOAK HEHEHE
```

The main hint was:

```text
new cloak
```

This made me think of StegCloak, because StegCloak hides data in text using invisible Unicode characters. The text looked normal, but between `MY` and `NEW`, there were actually invisible characters.

The characters were:

```text
U+2064 INVISIBLE PLUS
U+2061 FUNCTION APPLICATION
U+2062 INVISIBLE TIMES
U+200C ZERO WIDTH NON-JOINER
U+2063 INVISIBLE SEPARATOR
U+200D ZERO WIDTH JOINER
```

These characters do not show up normally, but they can still encode binary data. I extracted the invisible characters with Python and decoded them like a StegCloak-style zero-width payload.

The decoded text was slightly corrupted in the middle, probably because some of the invisible characters got messed up from copy/paste. The raw decoded text looked like this:

```text
5h0ut_\xc4\x04t0_Brandon
```

Even though the middle was broken, the intended password was still pretty clear:

```text
5h0ut_0ut_t0_Brandon
```

I ended up testing that password against the encrypted video data, and it worked, so that confirmed it was the right one.

---

## Step 2: Looking at the YouTube Video

The downloaded video file was:

```text
YTDown_YouTube_I-store-my-CP-here_Media_hLX0Igh-DKg_001_1080p(1).mp4
```

At first, the video just looked like random TV static. But the static looked very regular, so it seemed like the noise was probably structured data instead of actual random noise.

I checked the video metadata with `ffprobe`:

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,nb_frames,r_frame_rate,duration \
  -of default=nw=1 \
  "YTDown_YouTube_I-store-my-CP-here_Media_hLX0Igh-DKg_001_1080p(1).mp4"
```

The output was:

```text
width=1920
height=1080
r_frame_rate=30/1
duration=1.800000
nb_frames=54
```

So the video had:

```text
54 frames
1920x1080 resolution
30 FPS
1.8 seconds duration
```

After that, I extracted every frame from the video:

```bash
ffmpeg -i "YTDown_YouTube_I-store-my-CP-here_Media_hLX0Igh-DKg_001_1080p(1).mp4" \
  /mnt/data/vid_frames/frame_%04d.png
```

---

## Step 3: Decoding the Video Frames

The frames were not random static. Each frame was split into `4x4` pixel cells, and each cell stored one bit.

The way it worked was by comparing the brightness of the left half and right half of each `4x4` cell:

* If the right half was brighter than the left half, that was one bit value.
* If the left half was brighter than the right half, that was the other bit value.

This was the working extraction script:

```python
from PIL import Image
import numpy as np
from pathlib import Path

out = bytearray()

for frame in sorted(Path("/mnt/data/vid_frames").glob("frame_*.png")):
    img = Image.open(frame).convert("L")
    arr = np.asarray(img)
    h, w = arr.shape

    cells = arr.reshape(h // 4, 4, w // 4, 4)

    left = cells[:, :, :, :2].mean(axis=(1, 3))
    right = cells[:, :, :, 2:].mean(axis=(1, 3))

    bits = (right > left).astype(np.uint8)

    # The correct stream was inverted.
    bits ^= 1

    out.extend(np.packbits(bits.reshape(-1), bitorder="big").tobytes())

Path("/mnt/data/work/video_decoded_raw.bin").write_bytes(out)
```

One important thing was that the bitstream had to be inverted:

```python
bits ^= 1
```

Without that, the decoded data did not parse correctly.

After decoding the frames, the raw output started with this magic value:

```text
SFTY
```

That was a big clue. The `SFTY` magic matched the upstream `yt-media-storage` format. This format stores files inside videos so they can be uploaded to video platforms. It basically uses the video frames as a data transport layer. It can also use Wirehair fountain-code redundancy and optional libsodium XChaCha20-Poly1305 encryption.

---

## Step 4: Understanding the Packet Structure

After decoding the raw video stream, the data was split into packets.

The important values were:

```text
frames:              54
frame size:          1920 x 1080
cell size:           4 x 4
bits per frame:      480 * 270 = 129600
bytes per frame:     16200
packet size:         306 bytes
packets per frame:   52
total packets:       2808
```

Each frame had:

```text
1920 / 4 = 480 cells across
1080 / 4 = 270 cells down
480 * 270 = 129600 bits
129600 / 8 = 16200 bytes
```

Each packet was `306` bytes, so each frame had:

```text
16200 / 306 = 52 packets
```

Across `54` frames, that gave:

```text
54 * 52 = 2808 packets
```

This was the packet header layout I used:

```text
offset  size  field
0       4     magic = "SFTY"
4       1     version = 2
5       1     flags
6       16    file id / salt
22      4     chunk index
26      4     chunk size
30      2     symbol size
32      4     K / source symbol count
36      4     ESI / block id
40      2     payload length
42      4     original size
46      4     CRC32
50      ...   payload
```

After parsing the packets, the stats looked like this:

```text
file id:             000102030405060708090a0b0c0d0e0f
chunk index:         0
chunk size:          120243
original size:       120243
symbol size:         256
K/source symbols:    470
ESI range:           1..2808
payload lengths:     256 for almost all packets, 179 for ESI 469
flags:               6 for first 470 packets, 7 for the repair packets
```

One annoying detail was that the official encoder starts the Wirehair block ID at `1`, not `0`.

So this means:

```text
ESI 1 corresponds to chunk bytes 256..511
ESI 2 corresponds to chunk bytes 512..767
...
```

That also means the first source block, which would be chunk bytes `0..255`, was missing from the direct source packets. To fully recover the original encrypted chunk, I would have needed Wirehair reconstruction.

But I ended up not needing the full file.

---

## Step 5: Skipping Full Wirehair Reconstruction

A full solve could probably rebuild the original file with Wirehair. But I realized I could still solve the challenge without doing that.

The source packets were available from `ESI 1` through `ESI 469`. That gave almost the entire encrypted chunk, except for the first `256` bytes.

I concatenated the direct source payloads:

```python
tail = b"".join(payload_for_esi_1_to_469)
```

This gave:

```text
tail length = 119987
expected    = 120243 - 256
```

So I had the encrypted chunk starting from byte offset `256`.

The encrypted chunk format was basically:

```text
4-byte plaintext length || ciphertext || 16-byte Poly1305 tag
```

Since my known tail started at encrypted chunk offset `256`, and the first `4` bytes were the plaintext length, the known ciphertext started at ciphertext offset:

```text
256 - 4 = 252
```

The last `16` bytes of the known tail were the Poly1305 authentication tag. Since I was only stream-decrypting the known suffix, I stripped off the tag before decrypting.

---

## Step 6: Decrypting the Known Suffix

The password from the Pastebin was:

```text
5h0ut_0ut_t0_Brandon
```

The salt/file ID from the packets was:

```text
000102030405060708090a0b0c0d0e0f
```

The nonce was made like this:

```text
file_id || little_endian(chunk_index) || four zero bytes
```

Since the chunk index was `0`, the nonce was:

```text
000102030405060708090a0b0c0d0e0f0000000000000000
```

The encryption used libsodium-compatible logic:

```text
Argon2id13 interactive password hashing
XChaCha20-Poly1305 stream encryption
```

The useful values were:

```python
salt = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
nonce = salt + (0).to_bytes(4, "little") + b"\x00" * 4
password = b"5h0ut_0ut_t0_Brandon"
```

Because the known ciphertext suffix started at offset `252`, I had to start the XChaCha20 stream at the right place:

```python
ciphertext_offset = 252
counter = 1 + ciphertext_offset // 64
skip = ciphertext_offset % 64
```

This lined up the stream with the ciphertext I actually had.

After decrypting the suffix, most of the plaintext was just filler text:

```text
Quack Quack Quack Quack Quack ...
```

That was actually useful because it showed that the decryption was working and that the stream alignment was probably correct.

---

## Step 7: Getting the Flag

After decrypting the suffix, I searched the plaintext for `{`, since flags usually have braces.

The useful part looked like this:

```text
... continuing Quack: V Quack 1 Quack T{Quack_Quack_Quack_1_l0ve_Qu4cking_r34l_much_br} okay lets continue Quack ...
```

At first, the prefix looked kind of broken:

```text
V Quack 1 Quack T{
```

But `Quack` was just filler between the real characters. Removing the filler gives:

```text
V1T{
```

The expected flag format was lowercase, so I normalized it to:

```text
v1t{
```

The rest of the flag was already visible:

```text
Quack_Quack_Quack_1_l0ve_Qu4cking_r34l_much_br
```

So the final flag was:

```text
v1t{Quack_Quack_Quack_1_l0ve_Qu4cking_r34l_much_br}
```

---

## Final Flag

```text
v1t{Quack_Quack_Quack_1_l0ve_Qu4cking_r34l_much_br}
```
