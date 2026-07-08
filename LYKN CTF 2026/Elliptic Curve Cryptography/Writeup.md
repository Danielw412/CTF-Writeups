# Elliptic Curve Cryptography

## Challenge: 

the flag is hidden some where in this curve (100-bit?) look at the p,a and x params
```
[
{
    "field": {
        "p": "0x0fffffffffffffffffffffff67"
    },
    "a": "0x0fffffffffffffffffffffff64",
    "b": "0x00000000000000000000000abb",
    "order": "0x0ffffffffffff918654d8534a1",
    "subgroups": [
        {
            "x": "0x00000000000000000000000001",
            "y": "0x05a0248e58b8beaa670036b766",
            "order": "0xffffffffffff918654d8534a1",
            "cofactor": "0x1",
            "points": [
                {
                    "x": "0x00000000000000000000000001",
                    "y": "0x05a0248e58b8beaa670036b766",
                    "order": "0xffffffffffff918654d8534a1"
                }
            ]
        }
    ],
    "meta": {
        "j": "112789750583074789140677749659",
        "discriminant": "1267650600228229401493443331063",
        "embedding_degree": "1267650600228227457995237569696",
        "frobenius": "1943501465635527",
        "cm_discriminant": "-1293404453985476069488808253163",
        "conductor": "1"
    }
}]
```
## Summary

This challenge gave a small elliptic curve over a prime field. At first, it looked like it might involve some actual elliptic curve cryptography attack, but it ended up not really being that.

The important part was not solving a discrete log or breaking ECC. The challenge text specifically hinted to look at `p`, `a`, and `x`, so I focused on those values. Those parameters ended up matching the way NUMS curves are generated. After that, the admin hints helped give the paper that described the algorithm.

The final answer was:

```text
LYKNCTF{draft-black-numscurves-02}
```

## Challenge Data

The challenge gave these curve parameters:

```text
p = 0x0fffffffffffffffffffffff67
a = 0x0fffffffffffffffffffffff64
b = 0x00000000000000000000000abb
X(P) = 0x00000000000000000000000001
Y(P) = 0x05a0248e58b8beaa670036b766
h = 0x01
```

The challenge also directly said to look at `p`, `a`, and `x`, so those were probably not random values.

## Solution

### Step 1: Looking at the curve parameters

I first converted the important hex values into a cleaner form.

```text
p = 0xfffffffffffffffffffffff67
  = 2^100 - 0x99

a = 0xfffffffffffffffffffffff64
  = p - 3
  = -3 mod p

X(P) = 1
```

These values are actually pretty specific.

- `p` is a 100-bit pseudo-Mersenne prime of the form `2^s - c`.
- `a = p - 3`, so the curve is basically using the form `y^2 = x^3 - 3x + b`.
- The generator point starts at `x = 1`.

That combination stood out because it matches the NUMS curve generation style. NUMS curves use a pseudo-Mersenne prime, use the Weierstrass form with `a = -3`, and then pick a generator point by starting from the smallest valid `x` value.

So instead of trying to attack the curve, the better idea was to fingerprint where the curve came from.

### Step 2: Checking that the point is actually on the curve

Before fully trusting the fingerprint, I wanted to check that the provided point was actually valid.

The curve equation is:

```text
y^2 = x^3 + ax + b mod p
```

Since `x = 1`, the right side becomes:

```text
1^3 + (p - 3) * 1 + 0xabb
= 1 - 3 + 0xabb mod p
= 0xab9
```

The given `y` value satisfies this:

```text
y^2 mod p = 0xab9
```

So the point is actually on the curve. That made it more likely that these parameters were intentionally generated instead of just being random fake data.

### Step 3: Connecting it to NUMS curves

The next part was figuring out what exact algorithm or document this came from.

NUMS stands for “Nothing Up My Sleeve.” The idea is that the curve parameters are generated in a deterministic way so they do not look secretly chosen.

The IETF draft for NUMS curves describes this kind of generation:

- choose a prime like `p = 2^s - c`
- use a short Weierstrass curve like `y^2 = x^3 - 3x + b`
- choose the generator by starting from `x = 1`

The challenge curve matched those same patterns, except it used a small toy 100-bit curve instead of the normal larger curves like 256-bit, 384-bit, or 512-bit curves.

So at this point, the answer was probably related to NUMS, but `NUMS` by itself was too broad.

### Step 4: Using the admin hints

The first admin hint was:

```text
What the name of the algorithm that generate that curve?
```

That pointed toward the NUMS deterministic curve generation algorithm.

Later, the admins gave a more specific hint:

```text
Whats the name of the paper include algorithm that generate that curve?
```

That changed the direction. The flag was probably not just the name of the algorithm anymore. It was asking for the paper or draft that contained the algorithm.

There was also a pasted parameter block from the same NUMS draft. It looked like it came from the `numsp512t1` curve parameters, with values like:

```text
p = ... FFFDC7
a = ... FFFDC6
d = 0x9BAA8
X(P) = 0x20
h = 0x04
Curve-Id: numsp512t1
```

That confirmed that the source was an IETF NUMS curve document.

The final hint was:

```text
Oops I slipped my keyboard and type IETF and Draft with #000000
```

This was the important hint.

```text
IETF + Draft + #000000
```

`#000000` is black. So this pointed to an IETF draft by Black.

The matching draft name is:

```text
draft-black-numscurves-02
```

### Step 5: Getting the flag

The recovered flag body was the exact IETF Internet-Draft identifier:

```text
draft-black-numscurves-02
```

Putting it into the flag format gives:

```text
LYKNCTF{draft-black-numscurves-02}
```

## Flag

```text
LYKNCTF{draft-black-numscurves-02}
```

## Notes

The main issue was thinking too broadly. I tried `NUMS`, `nothing_up_my_sleeve`, or `GenerateCurveWeierstrass` which were not specific enough once the admins asked for the paper containing the algorithm.

The clue that finally narrowed it down was:

```text
IETF + Draft + #000000
```

That leads to an IETF draft by Black, which gives:

```text
draft-black-numscurves-02
```
