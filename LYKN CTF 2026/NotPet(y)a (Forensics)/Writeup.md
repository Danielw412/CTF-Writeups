# NotPet(y)a
## Challenge
Ellie split the flag into four fragments and hid them throughout a VHD image. To make things even more interesting, she deliberately corrupted the image using encryptor.exe.

Follow the echoes, recover the four fragments in sequence, and reconstruct the final flag.

Flag format: LYKNCTF{<uuid>} (<uuid> is a randomly generated UUID string.)

Note: Resist the temptation to skip ahead -- the later fragments may depend on clues uncovered earlier.

[CTF.ZIP]

---

## Summary

This challenge gave us a VHD image and a small Windows executable that acted like a NotPetya-style disk locker. The main idea was not just to carve random files from the disk. I had to repair enough of the VHD/NTFS metadata, pull clues out of the GPT and boot sector, reverse the executable enough to get the ZIP password, and then combine four flag fragments.

Final flag:

```text
LYKNCTF{7f87f117-ca52-4285-844a-ca0a5699a9cd}
```

## Challenge files

The downloaded archive had two files:

```text
encryptor.exe
infected.vhd
```

These were the useful facts from the challenge page and later hints:

- Category: forensics
- Points: 500
- The flag was split into four fragments.
- The admins later clarified that the original hint for fragment 2 was accidentally overwritten by the long ransom note, so they reposted the fragment-2 hint
- The repaired disk was the intended path. Random carving by itself was not really enough because some of the encrypted data depended on volume-specific key material.

## Solution

### Step 1: Identify the VHD layout

I started by checking the VHD structure. The image is a fixed-size VHD because the last 512 bytes are a `conectix` footer. That means the actual logical disk ends one sector before the physical file ends.

The protective MBR was still there at LBA 0. The primary GPT header at LBA 1 was wiped, but the backup GPT header was still alive at the final logical sector. That was really important because it let me recover the partition layout instead of just guessing.

Important recovered values:

```text
logical disk size:      104857600 bytes
sector size:            512 bytes
backup GPT header LBA:  204799
backup GPT table LBA:   204767
partition start LBA:    128
partition final LBA:    204671
```

The surviving GPT entry described a basic data partition. The weird part was that the primary entry and backup entry did not have the same partition name. That ended up mattering later.

### Step 2: Recover fragment 1 from the primary GPT entry

Even though the primary GPT header was trashed, the primary partition entry table still existed at LBA 2. The first partition entry name was not the normal Windows name. It was a Base64 string stored as UTF-16LE:

```text
TFlLTkNURns3Zjg3ZjExNy0=
```

Decoding it gives the first flag fragment:

```text
LYKNCTF{7f87f117-
```

The backup GPT entry name was just the normal string `Basic data partition`, so the primary entry was clearly changed on purpose to hold the first fragment.

### Step 3: Restore enough NTFS metadata to read parameters

The primary NTFS boot sector at the start of the partition was overwritten by the ransom note. However, the backup NTFS boot sector at the final partition sector was still intact.

From the backup NTFS boot sector, I got these values:

```text
bytes per sector:       512
sectors per cluster:    8
cluster size:           4096
MFT cluster:            8522
MFT mirror cluster:     2
volume serial/key:      504D550C97550C3C
```

That serial also matched the “personal installation key” from the reposted hint:

```text
Your personal installation key: 504D550C97550C3C
```

The primary boot sector can be restored by copying the backup NTFS boot sector from partition LBA `204671` back to partition LBA `128`. For this solve, I did not need to fully rebuild everything manually, because parsing the backup boot sector directly was already enough to get the important values.

### Step 4: Recover fragment 2 from the restored boot sector hint

A hint said that the recovery key was bound to the volume, and it included this line:

```text
Crypto wallet address: +0x80??�??�?s�m�thi�g_wr�ng
```

The `+0x80` part was the main clue. At offset `0x80` inside the intact backup NTFS boot sector, the bytes were:

```text
36 7f 2e 6f f6 60 3e 11 64 7f 6d 39 ea 1e 83 ec
```

I then XORed those bytes with the repeating installation key / NTFS volume serial:

```text
50 4d 55 0c 97 55 0c 3c
```

That produced:

```text
66 32 7b 63 61 35 32 2d 34 32 38 35 7d 4b 8f d0
```

ASCII:

```text
f2{ca52-4285}K.. 
```

So fragment 2 is:

```text
ca52-4285
```

This was where I went wrong the most. Fragment 2 was not a GPT GUID, not the NTFS serial formatted directly, and not something hidden in the ZIP media contents. The NTFS serial was the XOR key.

### Step 5: Reverse `encryptor.exe` to derive the ZIP password

Next, I looked at `encryptor.exe`. The executable imported BCrypt routines and had a few strings that were very useful:

```text
yuneko_dev_
{SERIAL}
flag.zip
SHA256
AES
ChainingModeCBC
```

From static analysis, the key derivation was:

```text
SHA256(PRNG_32_BYTES || b"yuneko_dev_" || RAW_NTFS_VOLUME_SERIAL)
```

The PRNG bytes generated by the executable were:

```text
4182fdee762eeb22ac286666a7bcd781be86d2d616956e451a9098a4e31507b4
```

Using the raw serial bytes from the backup boot sector:

```text
504d550c97550c3c
```

gives this SHA-256 digest:

```text
a558d6cf73f2aba9007595818ebd0c727db7b2c941520360ffe1b724621bb89c
```

The ZIP password was the uppercase hex version of that digest:

```text
A558D6CF73F2ABA9007595818EBD0C727DB7B2C941520360FFE1B724621BB89C
```

### Step 6: Recover the ZIP evidence and fragment 4

The deleted `flag.zip` metadata was not listed normally anymore, but the ZIP structures were still sitting inside the image. For the final flag, the important local header was the `part4.txt` member. Its local file header and encrypted payload were still intact at VHD offset `0x00b09b49`.

Using the ZIP password from the previous step, `part4.txt` decrypted and inflated to:

```text
a5699a9cd}
```

So fragment 4 is:

```text
a5699a9cd}
```

### Step 7: Recover fragment 3 from the deleted echo

After repairing enough NTFS metadata to parse the MFT, I found a lot of deleted temporary files named `fNN.tmp`. One deleted echo was the useful one:

```text
MFT record: 162
name:       f108.tmp
run:        LCN 3157, length 16 clusters
```

The raw cluster had an `f3{` marker, but the useful bytes were either encrypted or corrupted. Using the same recovered crypto material from `encryptor.exe` to decrypt the echoed record/cluster gave this marked region:

```text
82 79 47 11 66 33 7b 2d 38 34 34 61 2d 63 61 30 7d
```

Hex-bytes to text:

```text
.yG.f3{-844a-ca0}
```

The first four bytes were just noise/record slack. The actual third fragment was inside the `f3{...}` marker:

```text
-844a-ca0
```

### Step 8: Assemble the UUID

At this point, the four fragments were:

```text
f1: LYKNCTF{7f87f117-
f2: ca52-4285
f3: -844a-ca0
f4: a5699a9cd}
```

Putting them together gives:

```text
LYKNCTF{7f87f117-ca52-4285-844a-ca0a5699a9cd}
```

The inside also looks like a UUIDv4-style value:

```text
7f87f117-ca52-4285-844a-ca0a5699a9cd
              ^    ^
              v4   valid variant range
```

## Solve script

This script shows the extraction path from `ctf.zip` to the final flag. It parses the GPT and backup NTFS boot sector directly, derives the ZIP password, decrypts `part4.txt`, and assembles the final flag. The fragment-3 decrypted echo bytes are included as the output from the small AES/BCrypt reversing step described above.

```python
from pathlib import Path
import base64
import hashlib
import re
import struct
import zipfile
import zlib

CTF_ZIP = Path("ctf.zip")
SECTOR = 512

# Static reversing of encryptor.exe recovered this 32-byte PRNG output.
PRNG_BYTES = bytes.fromhex(
    "4182fdee762eeb22ac286666a7bcd781be86d2d616956e451a9098a4e31507b4"
)

# Output of decrypting the f3 echo/record with the recovered crypto material.
# Printable form: b"\\x82yG\\x11f3{-844a-ca0}"
F3_DECRYPTED_ECHO = bytes.fromhex("8279471166337b2d383434612d6361307d")


def read_member(zip_path: Path, member: str) -> bytes:
    with zipfile.ZipFile(zip_path) as zf:
        return zf.read(member)


def recover_frag1(vhd: bytes) -> tuple[str, int, int]:
    """Read the primary GPT partition entry at LBA 2."""
    entry = vhd[2 * SECTOR : 2 * SECTOR + 128]
    first_lba = struct.unpack_from("<Q", entry, 32)[0]
    last_lba = struct.unpack_from("<Q", entry, 40)[0]
    name = entry[56:128].decode("utf-16le").rstrip("\x00")
    frag1 = base64.b64decode(name).decode()
    return frag1, first_lba, last_lba


def recover_frag2(vhd: bytes, part_last_lba: int) -> tuple[str, bytes]:
    """Use the backup NTFS boot sector and the +0x80 hint."""
    boot = vhd[part_last_lba * SECTOR : (part_last_lba + 1) * SECTOR]
    if boot[3:11] != b"NTFS    ":
        raise RuntimeError("backup boot sector does not look like NTFS")

    serial = boot[72:80]
    encoded = boot[0x80 : 0x90]
    decoded = bytes(c ^ serial[i % len(serial)] for i, c in enumerate(encoded))
    match = re.search(rb"f2\{([^}]+)\}", decoded)
    if not match:
        raise RuntimeError(f"fragment 2 marker not found: {decoded!r}")
    return match.group(1).decode(), serial


def derive_zip_password(serial: bytes) -> bytes:
    digest = hashlib.sha256(PRNG_BYTES + b"yuneko_dev_" + serial).hexdigest()
    return digest.upper().encode()


def decrypt_zipcrypto_payload(password: bytes, encrypted: bytes) -> bytes:
    # Python's standard library exposes the same PKZIP stream cipher used by
    # traditional encrypted ZIP entries. The first 12 decrypted bytes are the
    # ZIP encryption header; the compressed data follows.
    return zipfile._ZipDecrypter(password)(encrypted)


def recover_zip_member_from_local_header(vhd: bytes, password: bytes, target: bytes) -> bytes:
    """Find and decrypt one ZIP local file header directly from the VHD."""
    pos = 0
    while True:
        pos = vhd.find(b"PK\x03\x04", pos)
        if pos < 0:
            raise RuntimeError(f"local ZIP member {target!r} not found")

        fields = struct.unpack_from("<IHHHHHIIIHH", vhd, pos)
        sig, ver, flags, method, mod_time, mod_date, crc, csize, usize, nlen, xlen = fields
        name_start = pos + 30
        name = vhd[name_start : name_start + nlen]
        data_start = name_start + nlen + xlen

        if name == target:
            encrypted = vhd[data_start : data_start + csize]
            decrypted = decrypt_zipcrypto_payload(password, encrypted)
            zip_header = decrypted[:12]
            compressed = decrypted[12:]

            # For entries without data descriptors, the final ZIP crypto header
            # byte should equal the high byte of the CRC.
            expected_check = (crc >> 24) & 0xFF
            if zip_header[-1] != expected_check:
                raise RuntimeError("wrong ZIP password or wrong local header")

            if method == 8:  # deflate, raw stream
                plaintext = zlib.decompress(compressed, -15)
            elif method == 0:  # stored
                plaintext = compressed
            else:
                raise RuntimeError(f"unsupported ZIP method: {method}")

            if (zlib.crc32(plaintext) & 0xFFFFFFFF) != crc:
                raise RuntimeError("ZIP CRC check failed")
            return plaintext

        pos += 4


def recover_frag3() -> str:
    match = re.search(rb"f3\{([^}]+)\}", F3_DECRYPTED_ECHO)
    if not match:
        raise RuntimeError("fragment 3 marker not found")
    return match.group(1).decode()


def main() -> None:
    vhd = read_member(CTF_ZIP, "infected.vhd")

    frag1, part_first_lba, part_last_lba = recover_frag1(vhd)
    frag2, serial = recover_frag2(vhd, part_last_lba)
    password = derive_zip_password(serial)
    frag3 = recover_frag3()
    frag4 = recover_zip_member_from_local_header(vhd, password, b"part4.txt").decode()

    flag = frag1 + frag2 + frag3 + frag4

    print(f"partition: LBA {part_first_lba}..{part_last_lba}")
    print(f"serial:    {serial.hex().upper()}")
    print(f"zip pass:  {password.decode()}")
    print(f"flag:      {flag}")


if __name__ == "__main__":
    main()
```

Expected output:

```text
partition: LBA 128..204671
serial:    504D550C97550C3C
zip pass:  A558D6CF73F2ABA9007595818EBD0C727DB7B2C941520360FFE1B724621BB89C
flag:      LYKNCTF{7f87f117-ca52-4285-844a-ca0a5699a9cd}
```

## Flag

```text
LYKNCTF{7f87f117-ca52-4285-844a-ca0a5699a9cd}
```
