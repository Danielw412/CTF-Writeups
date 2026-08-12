<a id="part-ii"></a>
## Part II - 17-gon, circle only

<a id="17-less-technical"></a>
### Less technical explanation

The 17-gon construction problem can be separated into two parts. First, we need to construct one exact step around the circle. After that, getting the other vertices is pretty cheap.

We start with the unit circle centered at \(O\), with \(P=(1,0)\) already sitting on it. If the angle between neighboring vertices is

\[
\theta=\frac{2\pi}{17},
\]

then the next vertex has x-coordinate

\[
\cos\theta.
\]

The value we actually construct first is

\[
t=2\cos\theta.
\]

That extra factor of two is useful because it appears naturally in the algebra.

Once \(t\) exists as a point on the x-axis, getting the actual next vertex is simple. We draw a circle centered at \((t,0)\) with radius 1 and intersect it with the unit circle. The two intersections are the vertices one step clockwise and one step counterclockwise from \(P\). In other words, they are the first neighboring vertices of the 17-gon.

So most of the hard part is really just this:

```text
start with O and P
        ↓
construct t = 2 cos(2π/17) exactly
        ↓
turn t into the first neighboring vertices
        ↓
use those vertices to fill in the rest
```

The technical section uses values called

\[
y_k=2\cos\frac{2\pi k}{17}.
\]

You do not need to keep track of all of them to understand what is happening. We only use a few carefully chosen sums and products of these values. The point is that those sums and products let us reach \(y_1=t\) through a short chain of quadratic equations.

A quadratic equation is just an equation with two possible answers. For example, if two unknown values \(A\) and \(B\) have a known sum \(S\) and a known product \(P\), then they are the two answers to

\[
x^2-Sx+P=0.
\]

This fits the parser really well because a circle-circle intersection also gives us two points. Instead of using the normal quadratic formula and separately constructing a square root, adding things, subtracting things, and dividing by two, we arrange two circles so their two intersection points directly represent the two answers we need.

That is basically what the seed construction does several times.

The first big value is \(\sqrt{17}\). We create two mirror-image circles whose intersection points land on the x-axis at

\[
\frac{-1-\sqrt{17}}4
\quad\text{and}\quad
\frac{-1+\sqrt{17}}4.
\]

The important part is not the exact formula, but rather that one circle intersection gives both related values at the same time.

Those two values are then used to construct two more values called \(T\) and \(S\). Each of those is again obtained as one answer to a quadratic. Finally, \(T\) and \(S\) give a last quadratic whose two answers are \(y_1\) and \(y_4\). One of those is exactly

\[
y_1=2\cos\frac{2\pi}{17},
\]

which is the value we wanted from the beginning.

The chain is:

```text
sqrt(17)
   ↓
two related starting values
   ↓
T and S
   ↓
y1 and y4
   ↓
first neighboring vertices
```

A lot of the score improvement came from making these quadratics happen directly as geometry. Earlier versions used more general compass constructions to copy radii or build intermediate values. Those worked, but they created a lot of circles and points that were only there to move a number from one place to another. The final construction tries to make the useful point appear directly as the second intersection of circles we already needed. The diagram below shows the difference.

![Comparison of the earlier helper-circle method with the optimized direct-intersection method](image.png)

After \(y_1\) is constructed, we get the vertices at offsets \(\pm1\). A second circle gives the vertices at offsets \(\pm2\). At that point we already have four real polygon vertices plus \(P\).

The rest uses a simple fact about circles on the same circumcircle. Suppose we know two vertices. If we draw a circle centered at one of them and through the other, that circle hits the main circumcircle in two places. One is the old vertex we already knew. The other is a new vertex reflected to the other side of the center angle.

By choosing the center and known vertex in the right order, the construction keeps producing missing 17-gon vertices until all 17 are present. The technical section lists the exact exponent sequence.

The final score also shows where the work went:

```text
algebraic seed     111
vertex tail         42
total              153
```

So even for only 17 vertices, constructing the exact first step cost much more than finishing the polygon. That was one of the main things that shaped the later 257 and 65,537 constructions.

Everything here is exact. The circles are not placed using decimal approximations to the cosine. Every point comes from exact distance and intersection identities, so the final neighboring vertex is mathematically the correct 17th root of unity. It does not depend on being close enough for the checker.

<a id="17-result"></a>
### Final accepted result

Our final verified and accepted 17-circle construction is:

```text
score                 = 153
executable lines      = 109
circle commands       = 65
CC intersections      = 43
stored points         = 88
```

The score identity is immediate:

\[
2+65+2(43)=153.
\]

The score breaks down pretty cleanly:

| part | circles | CC intersections | score contribution |
|---|---:|---:|---:|
| initial points \(O,P\) | 0 | 0 | 2 |
| algebraic seed through `q0095` | 51 | 29 | 109 |
| vertex tail | 14 | 14 | 42 |
| **total** | **65** | **43** | **153** |

The seed was already the bigger bottleneck. Even a theoretically perfect pair-harvesting tail could not push this construction below 100 without a cheaper algebraic core.

---

<a id="17-construction"></a>
### Construction steps

> **Roadmap:** algebraic target → bootstrap geometry → construct \(\sqrt{17}\) → construct \(T,S\) → solve the final quadratic → harvest the first roots → generate all 17 vertices.

#### Step 1 - The algebraic spine

Let

\[
\zeta=e^{2\pi i/17}
\]

and define the real traces

\[
y_k=\zeta^k+\zeta^{-k}
=
2\cos\frac{2\pi k}{17}.
\]

Instead of starting from the famous nested-radical formula for a 17-gon, we used Gaussian-period identities that are naturally quadratic.

Define

\[
B=y_1+y_2+y_4+y_8
\]

and

\[
B'=y_3+y_5+y_6+y_7.
\]

The exact cyclotomic certificate verifies

\[
B^2+B-4=0,
\qquad
{B'}^2+B'-4=0,
\qquad
B+B'+1=0.
\]

Thus, in the intended real embedding,

\[
B=\frac{-1+\sqrt{17}}2,
\qquad
B'=\frac{-1-\sqrt{17}}2.
\]

The geometry uses the halved values

\[
a=\frac{-1-\sqrt{17}}4,
\qquad
b=\frac{-1+\sqrt{17}}4.
\]

Now set

\[
S=y_1+y_4,
\qquad
T=y_3+y_5.
\]

The exact identities include

\[
(y_1+y_4)(y_2+y_8)=-1,
\]

\[
(y_3+y_5)(y_6+y_7)=-1,
\]

and, crucially,

\[
y_1y_4=y_3+y_5=T.
\]

Therefore \(S\) is the positive root of

\[
x^2-2bx-1=0
\]

and \(T\) is the positive root of

\[
x^2-2ax-1=0.
\]

The final target pair \(y_1,y_4\) is then exactly the root pair of

\[
\boxed{x^2-Sx+T=0}.
\]

That is the entire algebraic chain:

\[
\sqrt{17}
\longrightarrow
(a,b)
\longrightarrow
(T,S)
\longrightarrow
(y_4,y_1)
\longrightarrow
\zeta^{\pm1},\zeta^{\pm2}
\longrightarrow
\text{all 17 vertices}.
\]

The hard part was realizing that chain with as few legal circles as possible.

---

#### Step 2 - Bootstrap geometry and why radius transport hurt

We start with

```text
circle O P c0001
```

which is the true unit circumcircle

\[
\Gamma:x^2+y^2=1.
\]

The next unit circle, centered at \(P\) through \(O\), gives the equilateral pair

\[
\left(\frac12,\pm\frac{\sqrt3}{2}\right).
\]

A short compass scaffold produces points including

\[
(-1,0),\qquad
\left(-\frac12,0\right),\qquad
(0,\pm1),\qquad
(0,\pm\sqrt2).
\]

The original construction spent a surprising amount of score merely moving already-known radii between centers. That is normal in a classical compass-only construction, but expensive in this parser because every transfer gadget leaves behind scored circles and points.

This became the first major optimization lesson of the 17-gon:

> [!IMPORTANT]
> **If a desired point is already the second intersection of two circles whose centers and witnesses exist, construct it directly. Do not compile a generic radius-copy theorem around it.**

Three concrete substitutions mattered.

##### Direct `q0015`

Instead of a longer radius-copy chain, two circles already available in the scaffold yield

\[
q0015=(-1,\sqrt2)
\]

as their second intersection.

##### Direct `q0021`

An equal-radius reflection using centers at \((-1,0)\) and \((-1,\sqrt2)\) gives

\[
q0021=\left(-\frac32,0\right).
\]

##### Direct `q0053`

A second-intersection identity produces

\[
q0053=(0,1-\sqrt2)
\]

without separately transporting the required radius.

These look like small local tricks, but each replacement kills not just its own commands; it can also make an entire upstream helper branch dead. A backward dependency prune after the substitutions was responsible for the last large drop.

---

#### Step 3 - Constructing \(\sqrt{17}\) directly from a mirror-circle pair

One useful block starts with the intersection of two unit circles arranged so that we obtain the conjugate pair

\[
\left(-\frac14,\pm\frac{\sqrt{15}}4\right).
\]

We then construct radius-\(\sqrt2\) witnesses for both conjugate centers. The two mirror circles have equations

\[
\left(x+\frac14\right)^2+
\left(y-\frac{\sqrt{15}}4\right)^2
=2
\]

and

\[
\left(x+\frac14\right)^2+
\left(y+\frac{\sqrt{15}}4\right)^2
=2.
\]

Their common points lie on the x-axis. Setting \(y=0\),

\[
\left(x+\frac14\right)^2+\frac{15}{16}=2
\]

so

\[
\left(x+\frac14\right)^2=\frac{17}{16}.
\]

Therefore the two outputs are exactly

\[
\boxed{
\frac{-1-\sqrt{17}}4,
\frac{-1+\sqrt{17}}4
}.
\]

In the file these are `q0033` and `q0034`.

This pattern shows up a lot in the final construction: **the two algebraic conjugates are deliberately made to be the two geometric intersection outputs**.

---

#### Step 4 - Constructing \(T\) and \(S\) without materializing discriminants

Given

\[
a=\frac{-1-\sqrt{17}}4
\]

we need the positive root of

\[
x^2-2ax-1=0.
\]

The optimized geometry constructs the two centers

\[
(a,0),\qquad(a,1)
\]

and chooses radii so that a common x-axis point \(x\) satisfies

\[
(x-a)^2=a^2+1.
\]

Expanding gives

\[
x^2-2ax-1=0.
\]

The positive output is

\[
q0060=T.
\]

The conjugate construction with \(b\) gives

\[
q0074=S.
\]

What matters here is what we **did not** have to build:

- no explicit discriminant;
- no generic square root;
- no separate subtraction;
- no generic division by two.

The quadratic root itself is an intersection.

---

#### Step 5 - Final quadratic and the primitive trace

Now

\[
u=q0060=y_1y_4,
\qquad
v=q0074=y_1+y_4.
\]

So \(y_1,y_4\) are the roots of

\[
x^2-vx+u=0.
\]

The late construction creates a mirror-symmetric pair of centers with x-coordinate \(v/2\), then an exact radius witness that makes the two x-axis intersections satisfy precisely that quadratic.

The final CC gives

\[
q0091=y_4
=
2\cos\frac{8\pi}{17}
\]

and

\[
\boxed{
q0092=y_1
=
2\cos\frac{2\pi}{17}
}.
\]

A related reflection then produces

\[
q0095=y_1-1
\]

without a generic subtraction routine.

At that point, the hard algebra is basically done.

---

#### Step 6 - Harvesting four roots immediately

Let

\[
t=y_1=2\cos\frac{2\pi}{17}.
\]

The circle centered at \((t,0)\) through \((t-1,0)\) has radius 1. Intersect it with \(\Gamma\):

\[
x^2+y^2=1
\]

and

\[
(x-t)^2+y^2=1.
\]

Subtracting gives

\[
x=\frac t2=\cos\frac{2\pi}{17},
\]

so the two outputs are exactly

\[
\zeta^{\pm1}.
\]

A second circle, centered at \((-1,0)\) through \((t-1,0)\), has radius \(t\). Its intersection with \(\Gamma\) satisfies

\[
x=\frac{t^2-2}{2}
=
\cos\frac{4\pi}{17},
\]

so it gives

\[
\zeta^{\pm2}.
\]

Two circles have now produced four final polygon vertices.

---

#### Step 7 - Finishing all 17 vertices by exponent reflection

Suppose an auxiliary circle is centered at \(\zeta^a\) and passes through \(\zeta^b\). Reflection across the radius through \(\zeta^a\) sends exponent \(b\) to

\[
2a-b\pmod{17}.
\]

Therefore the intersections of that circle with \(\Gamma\) are

\[
\boxed{\zeta^b,\ \zeta^{2a-b}}.
\]

Starting with \(\{\pm1,\pm2\}\), the final tail uses the recurrence:

| center \(a\) | known witness \(b\) | new exponent \(2a-b\pmod{17}\) |
|---:|---:|---:|
| 1 | 15 | 4 |
| 0 | 4 | 13 |
| 1 | 13 | 6 |
| 0 | 6 | 11 |
| 1 | 11 | 8 |
| 0 | 8 | 9 |
| 1 | 9 | 10 |
| 0 | 10 | 7 |
| 1 | 7 | 12 |
| 0 | 12 | 5 |
| 1 | 5 | 14 |
| 0 | 14 | 3 |

Together with \(P=\zeta^0\), every exponent \(0,\ldots,16\) is present.

The final `n_gon` therefore lists

\[
1,\zeta,\zeta^2,\ldots,\zeta^{16}
\]

in actual cyclic order, not merely a numerically accepted permutation.

---

<a id="17-optimization"></a>
### Optimization history: 202 → 153

The recorded exact progression was:

| stage | score | main change |
|---|---:|---|
| uploaded legitimate construction | 202 | Gérard-style baseline |
| pair-harvested initial roots | 199 | two useful roots from a \(\Gamma\) intersection |
| direct scalar/reflection substitutions | 191 | remove generic transfer work |
| direct `q0060`, `q0074` quadratics | 183 | roots appear directly as CC outputs |
| more conjugate/reflection reuse | 175 | eliminate mirrored branches |
| direct `q0053` | 171 | two-circle incidence |
| direct `q0015`, `q0021` | 167 | remove midpoint/radius-copy gadgets |
| exact circumcircle reuse | 161 | reuse a geometrically identical \(\Gamma\) |
| backward dependency pruning | **153** | delete now-dead branches |

The biggest lesson was that the algebra itself was not the main waste. **Radius transport and helper dependencies were.**

---

<a id="17-lower-bound"></a>
### Exact lower-bound addendum: why scores 27 and 28 are impossible

The lowest raw leaderboard scores made it worth asking how low an exact construction could possibly go.

For the 17-circle mode, let \(c\) be the number of circles and \(i\) the number of CC intersections.

At least 15 polygon vertices must be generated beyond the initial point names, so

\[
i\ge8.
\]

Let \(\Gamma\) be the true circumcircle. If \(\Gamma\) is stored, every missing selected vertex needs one additional construction-circle incidence. Any other circle meets \(\Gamma\) in at most two points, so at least eight additional circles are required:

\[
c\ge9.
\]

Thus the naive incidence lower bound is

\[
\text{score}
=
2+c+2i
\ge
2+9+16
=
27.
\]

The interesting part is that neither 27 nor 28 is attainable.

#### Step 1 - The first productive intersection is forced

Before any intersection, only \(O\) and \(P\) exist.

The only geometrically distinct nondegenerate circles available are:

- centered at \(O\) through \(P\);
- centered at \(P\) through \(O\).

So the first productive CC is forced and yields

\[
Q_\pm
=
\left(
\frac12,
\pm\frac{\sqrt3}{2}
\right).
\]

#### Step 2 - Scores 27 and 28 leave only one helper point

At score 27, the lower-bound counts force

\[
c=9,\qquad i=8.
\]

At score 28, they force

\[
c=10,\qquad i=8.
\]

Either way, the stored-point count is

\[
2+2i=18.
\]

Seventeen distinct points must appear in the polygon. Therefore the entire construction has room for only **one helper point**.

After the first CC, the four relevant points are

\[
P,\ O,\ Q_+,\ Q_-.
\]

Since \(P\) is mandatory, at least two of \(O,Q_+,Q_-\) must also be final polygon vertices.

There are two cases up to reflection.

##### Case 1: \(O\) and \(Q_+\) are vertices

Then

\[
P,O,Q_+
\]

form an equilateral triangle.

Three vertices of a regular 17-gon cannot be separated by \(120^\circ\), because that would require \(17/3\) polygon steps.

Contradiction.

##### Case 2: \(Q_+\) and \(Q_-\) are vertices

We have

\[
|P-Q_+|=|P-Q_-|=1
\]

and

\[
|Q_+-Q_-|=\sqrt3.
\]

If two vertices of a regular 17-gon are equally far from \(P\), they lie at offsets \(\pm k\). The ratio of their mutual chord to either chord from \(P\) is

\[
\frac{2R\sin(2k\pi/17)}
     {2R\sin(k\pi/17)}
=
2\cos\frac{k\pi}{17}.
\]

Our forced geometry would require

\[
2\cos\frac{k\pi}{17}=\sqrt3.
\]

Since \(1\le k\le8\),

\[
\frac{k\pi}{17}=\frac{\pi}{6}
\]

would be required, so

\[
k=\frac{17}{6},
\]

not an integer.

Contradiction again.

Therefore

\[
\boxed{\text{no genuine exact score-27 or score-28 17-circle construction exists}.}
\]

We also searched the near-minimal 29–32 incidence space computationally and found no compatible construction, but that work never became the same kind of symbolic theorem. We treat it as **negative computational evidence**, not a global proof.

That distinction between proof and search evidence became important throughout the project.

---
