<a id="part-iii"></a>
## Part III - 257-gon, circle only

<a id="257-less-technical"></a>
### Less technical explanation

The 257-gon uses the same overall idea as the 17-gon, but the exact starting value is much harder to build.

Again, we do not want to construct 257 unrelated points from scratch. We want one exact step around the unit circle. If

\[
\theta=\frac{2\pi}{257},
\]

the main target is

\[
t=2\cos\theta.
\]

Once \(t\) exists on the x-axis, a unit-radius circle centered at \((t,0)\) intersects the main unit circle at the two neighboring vertices

\[
e^{i\theta}
\quad\text{and}\quad
e^{-i\theta}.
\]

After that, the remaining vertices come from repeating the same side-length step around the circle.

So the real problem is still constructing one exact cosine.

What makes 257 manageable is the fact that

\[
257-1=256=2^8.
\]

The technical construction uses something called "Gaussian periods". The name sounds worse than the actual idea we need from them. We take a large collection of root-of-unity values, group them into sums, and repeatedly split those groups in half. At every split, the two child values have a known sum and a known product.

If the two child values are \(A\) and \(B\), and we know

\[
A+B=S
\]

and

\[
AB=P,
\]

then, with some simple algebra, \(A\) and \(B\) are the two answers to

\[
x^2-Sx+P=0.
\]

That means each split is only a quadratic problem.

Because 256 is a power of two, we can keep doing these two-way splits until we eventually reach the one value

\[
2\cos\frac{2\pi}{257}.
\]

The first version of the compiler treated the whole Gaussian-period tree as if every branch mattered. A complete tree has 127 quadratic splits. That was exact, but it was very wasteful because almost all of those values never affected the one cosine we actually needed.

The better version starts from the target and works backward. For every value, it asks which earlier values are actually needed to compute its sum and product. Anything that never reaches the final target is not constructed.

That changes the important count from

```text
127 total quadratic splits
```

to

```text
24 quadratic splits actually needed
```

This was a huge reduction. It mattered much more than saving one circle inside one local gadget.

The next problem is turning each of those 24 quadratic splits into legal circle-only geometry.

The obvious algebraic way would be to use the quadratic formula. That would mean constructing a discriminant, constructing its square root, doing separate additions and subtractions, and then dividing by two. All of those steps cost circles and intersection points.

Instead, the construction uses a geometric quadratic solver. It places two circles so that their two common points already have the two x-coordinates we want. In other words, the two answers to the quadratic are literally the two outputs of one circle-circle intersection.

That is useful because the parser always stores both intersection points anyway. We might as well make both of them meaningful.

There is still other arithmetic around the quadratic splits. The Gaussian-period products are made from integer combinations of earlier values, so the compiler needs exact addition, negation, doubling, and midpoint operations. The optimized version uses small reusable circle constructions and keeps some values scaled by 2, 4, or 8 for a while instead of constantly dividing them back down. Division by two is not free here, so delaying it saves geometry.

Eventually the 24-split chain produces

\[
t=2\cos\frac{2\pi}{257}.
\]

At that point the complicated part is over.

We draw the unit-radius circle centered at \((t,0)\). Its intersections with the main unit circle are exactly the two neighboring roots. The reason is simple: both points are distance 1 from the origin and distance 1 from \((t,0)\), which forces their x-coordinate to be \(t/2=\cos\theta\).

Now we have the first step size around the polygon.

To keep moving, suppose two consecutive vertices are already known. Draw a circle centered at the newer vertex and through the previous one. Its radius is exactly one side length of the regular 257-gon. When that circle intersects the main circumcircle, one intersection is the previous vertex and the other is the next vertex.

So the process is basically:

```text
known previous vertex + known current vertex
        ↓
draw one side-length circle
        ↓
intersect with the main circumcircle
        ↓
old vertex + next vertex
        ↓
repeat
```

The final suffix uses 255 circles and 255 circle-circle intersections. It is repetitive, but it is easy to prove exact.

The score breakdown makes the main difficulty pretty clear. The repeated vertex-generation part costs 765 score. The primitive-root construction before it costs much more. This is why most of the serious optimization work went into the algebraic seed rather than the final walk around the circle.

<a id="257-result"></a>
### Final accepted result and exact lower bound

Our final verified and accepted `opt39` construction has:

```text
score                 = 2149
executable lines      = 1529
circles               = 909
CC intersections      = 619
stored points         = 1240
stored lines          = 0
primitive step        = 1
```

Because every CC contributes two points,

\[
2+2(619)=1240
\]

and

\[
1240+909=2149.
\]

Before getting into the construction, it helps to know the exact incidence lower bound.

Let \(\Gamma\) be the true circumcircle of the final 257-gon.

There are 256 missing polygon vertices beyond \(P\). If \(\Gamma\) itself is stored, each of those vertices must also lie on some other circle. A circle different from \(\Gamma\) meets it in at most two points, so at least 128 auxiliary circles are necessary:

\[
c\ge129.
\]

At least 128 CC commands are also needed to create 256 points two at a time:

\[
i\ge128.
\]

Hence

\[
\boxed{
\text{score}\ge
2+129+2(128)
=
387
}.
\]

This is only an incidence bound. It ignores the harder causal question of how to construct those 129 circles from \(O,P\).

That gap (between 387 and 2,149) became the focus of the later research.

---

<a id="257-construction"></a>
### Construction steps

> **Roadmap:** set up Gaussian periods → prune the dependency tree → compile exact scalar arithmetic → solve each quadratic directly → extract \(\zeta^{\pm1}\) → walk around the circumcircle.

#### Step 1 - Gaussian periods for 257

Let

\[
\zeta=e^{2\pi i/257}.
\]

Because

\[
257=2^8+1
\]

is a Fermat prime, the multiplicative group modulo 257 has order 256, a power of two.

We used \(g=3\), which has order 256 modulo 257, to organize a Gaussian-period tower. Basically, each stage splits a parent period into two children

\[
A+B=S
\]

whose product

\[
AB=P
\]

is expressible in the previous field. Therefore the children are roots of

\[
x^2-Sx+P=0.
\]

A full binary hierarchy would contain

\[
1+2+4+8+16+32+64=127
\]

quadratic splits.

Our first exact compiler more or less built all of them.

That was the wrong architecture.

---

#### Step 2 - Backward dependency pruning: 127 splits became 24

The only value we ultimately need is the real primitive trace

\[
\eta_{7,0}
=
\zeta+\zeta^{-1}
=
2\cos\frac{2\pi}{257}.
\]

So instead of generating every period, the optimized planner starts at that leaf and walks backward:

> Which earlier period values are actually required to express the product of the two children needed at this node?

Repeating that question to closure leaves only 40 period values and 24 quadratic splits:

| level | required period values | required splits |
|---:|---:|---:|
| 0 | 1 | 1 |
| 1 | 2 | 2 |
| 2 | 4 | 4 |
| 3 | 8 | 8 |
| 4 | 16 | 6 |
| 5 | 6 | 2 |
| 6 | 2 | 1 |
| 7 | 1 | - |
| **total** | **40** | **24** |

The first split is already simple:

\[
S=-1,\qquad P=-64,
\]

so the children are roots of

\[
x^2+x-64=0.
\]

This dependency reduction saved way more than any one local compass trick. It is the cleanest example of why `n-force` became a compiler problem rather than a textbook construction problem.

---

#### Step 3 - Exact compass arithmetic

The `.geo` still uses only circles and CC intersections. The generator merely gives names to recurring exact geometric macros.

##### Reflection: \(2B-A\)

Given scalar points \(A,B\) on the axis, a small equilateral-circle configuration reflects \(A\) across \(B\), producing

\[
2B-A.
\]

The optimized generic cost is three circles and two CC intersections before cache reuse.

##### Addition

Let

\[
X=(x,0),\qquad Y=(y,0).
\]

Draw equal circles centered at \(X\) and \(Y\) through each other. Their equilateral intersections \(Q,R\) have x-coordinate

\[
\frac{x+y}{2}.
\]

Now draw equal circles centered at \(Q,R\) through \(O\). One axis intersection is \(O\); the other is

\[
(x+y,0).
\]

So generic exact scalar addition costs four circles and two CCs.

##### Negation

A reusable reflector scaffold at

\[
(0,\pm\sqrt3)
\]

allows a scalar \(x\) to be reflected to \(-x\) with two circles and one CC after setup.

##### Midpoint

The compiler can first create

\[
E=2B-A
\]

and then use compass inversion relative to the circle centered at \(A\) through \(B\) to recover the midpoint.

##### Sparse integer forms

Gaussian products become integer linear combinations of earlier periods. Instead of materializing every coefficient independently, the compiler uses signed binary Horner form. A step

\[
A\mapsto2A+q
\]

can be implemented as the reflection

\[
2A-(-q).
\]

This substantially compressed the linear arithmetic.

---

#### Step 4 - Solve the quadratic directly from sum and product

The original mental model was

\[
a,b
=
\frac{s\pm\sqrt{s^2-4p}}2.
\]

That suggests a long construction:

1. square \(s\);
2. form \(s^2-4p\);
3. construct a square root;
4. add/subtract;
5. divide by two.

Under `n-force`, that is a really expensive way to do it.

The optimized solver treats the quadratic as a geometry object.

Suppose

\[
a+b=s,\qquad ab=p.
\]

Use the fixed scaffold

\[
R_\pm=
\left(
0,\pm\frac{2\sqrt3}{3}
\right)
\]

and define

\[
t=p+\frac13.
\]

Construct

\[
A=s-t,\qquad B=s+t.
\]

Equal circles centered at \(A,B\) yield the equilateral pair

\[
Q_\pm=(s,\pm\sqrt3\,t).
\]

Now draw:

- a circle centered at \(Q_+\) through \(R_+\);
- a circle centered at \(Q_-\) through \(R_-\).

Their common points lie on the scalar axis. If one has x-coordinate \(x\),

\[
(x-s)^2+3t^2
=
s^2+3\left(t-\frac23\right)^2.
\]

After cancellation,

\[
x^2-2sx+4p=0.
\]

The roots are exactly

\[
\boxed{2a,\ 2b}.
\]

So one reflected pair of circles produces both algebraic conjugates directly.

The actual compiler uses scaled variants and deliberately carries values at scales \(2,4,8\) through several levels. Division by two is not free in a compass-only language, so postponing normalization is cheaper than repeatedly constructing midpoints.

---

#### Step 5 - Getting the first unit roots

After the 24 period splits and final scale reductions, the compiler has

\[
\eta
=
2\cos\theta,
\qquad
\theta=\frac{2\pi}{257}.
\]

An earlier version explicitly constructed the chord

\[
2\sin\frac{\pi}{257}.
\]

That square-root route was unnecessary.

Instead, construct a unit-radius circle centered at \((\eta,0)\). Since the parser needs a radius witness, first construct \(\eta+1\), then emit a circle centered at \(\eta\) through \(\eta+1\).

Intersect it with the unit circumcircle:

\[
x^2+y^2=1,
\]

\[
(x-\eta)^2+y^2=1.
\]

Subtracting gives

\[
x=\frac{\eta}{2}
=
\cos\theta.
\]

Therefore the two intersections are exactly

\[
\boxed{\zeta,\zeta^{-1}}.
\]

So we could remove the final chord square root completely.

---

#### Step 6 - The equal-chord walk

Once \(\zeta^{-1}\) and \(\zeta\) are known, the rest is simple.

Suppose consecutive vertices

\[
\zeta^{j-1},\qquad\zeta^j
\]

already exist.

Draw the circle centered at \(\zeta^j\) through \(\zeta^{j-1}\). Its radius is the polygon side length. Its intersections with \(\Gamma\) are exactly

\[
\zeta^{j-1}
\quad\text{and}\quad
\zeta^{j+1}.
\]

The first output is geometrically old but receives a fresh parser name. The second is the next vertex.

The 257 suffix uses:

```text
255 circles
255 CC intersections
510 geometry commands
score contribution = 765
```

The final ordered list is

\[
1,\zeta,\zeta^2,\ldots,\zeta^{256}.
\]

The independent verifier confirms primitive step \(k=1\), not merely a star polygon accepted through reordering.

---

<a id="257-optimization"></a>
### Optimization history: 37,004 → 2,149

The 257 progression records how our optimization strategy changed:

| stage | score | lines | main change |
|---|---:|---:|---|
| initial exact compiler | 37,004 | 27,196 | all 127 splits; generic arithmetic |
| pruned dependency DAG | 8,255 | 5,943 | build only periods needed for the target |
| signed-binary linear forms | 5,134 | 3,642 | Horner compilation |
| six-line scalar addition | 3,743 | 2,661 | equilateral addition identity |
| product-form quadratics | 2,729 | 1,963 | roots directly from sum/product |
| specialized early stages | 2,368 | 1,690 | take advantage of constant products |
| multilevel period basis | 2,269 | 1,615 | reuse parent-period identities |
| shared exact partial sums | 2,199 | 1,565 | exact CSE |
| opt38 | 2,151 | 1,531 | scaling + geometry reuse |
| **opt39** | **2,149** | **1,529** | remove two exact duplicate circles |

The final two-point reduction is small, but it is a good example of the exactness standard we were using.

The opt39 wrapper observes two origin-centered circles whose through-points are exact mirror pairs across an axis through \(O\). Therefore their radii are not numerically similar; they are **provably equal**.

Concretely, the generator removes two redundant circle commands:

- one through `cr34`, whose mirror is `cr35`;
- one through `e482`, whose mirror is `e478`;

and redirects later intersections to the already-existing geometrically identical origin circles.

That is the kind of reuse we accepted: prove equality in exact geometry first, then deduplicate.

---

<a id="257-verification"></a>
### Exact verification

The accepted opt39 file reproduces the same final counts under the final patched parser:

```text
is_ok_circle=True
status=valid
score=2149
executable_lines=1529
stored_points=1240
stored_circles=909
stored_lines=0
```

An independent root-of-unity replay gives, at higher precision:

```text
primitive_step_k=1
max_vertex_error_vs_zeta^j       = 8.8029932169e-1226
max_unit_radius_squared_error    = 1.2916192025e-1229
max_edge_squared_relative_error  = 7.2807996224e-1224
chord_abs_error                  = 4.8781010261e-1228
```

The same file was replayed at 3072, 3584, 4096, 4608, 5120, 6144, and 8192 bits with the same topology and intended root ordering. The minimum normalized geometric margins remained stable.

Contest acceptance and the numerical replay both support the implementation. The mathematical proof is the exact Gaussian-period algebra and Euclidean identities used to generate the file.

---

<a id="257-postsolve"></a>
### Post-solve research: why 387 did not become 550

Once opt39 existed, we asked a different question:

> Could a genuinely exact construction get anywhere near the incidence lower bound?

A first cost audit showed the immediate problem. Before the first final root-producing circle, opt39 already spends roughly

\[
2+654+2(364)=1384
\]

score.

So no amount of suffix optimization could reach 550. A radically smaller construction had to **merge primitive-root generation with vertex generation**.

That is what led to the more experimental geometry research later in the thread.

#### Research direction 1 - Conjugate-pair harvesting

For

\[
t_k
=
\zeta^k+\zeta^{-k}
=
2\cos(k\theta),
\]

a unit circle centered at \((t_k,0)\) intersects \(\Gamma\) at exactly

\[
\zeta^k,\zeta^{-k}.
\]

In principle, 128 such circles could generate all 256 nonzero roots two at a time.

The problem was no longer final-root incidence. It was constructing 128 useful centers \(t_k\) cheaply.

#### Research direction 2 - Reciprocal helper rings

A related version uses circles through the origin and two symmetric roots. The circle through

\[
O,\ \zeta^{m-d},\ \zeta^{m+d}
\]

has center

\[
\boxed{
C_{d,m}
=
\frac{\zeta^m}{2\cos(d\theta)}
}.
\]

For fixed \(d\), the centers lie on a reciprocal concentric ring.

This turned the search into a more structured problem involving ring radii, angular offsets, and transversals.

#### Research direction 3 - A productive helper-circle family

One exact identity was especially promising.

Let

\[
q_h=2\cos(h\theta)-1,
\qquad
A_j=q_h^{-1}\zeta^j.
\]

Let \(F_j\) be the circle centered at \(A_j\) through \(A_{j+h}\). Then

\[
F_j\cap\Gamma
=
\{\zeta^{j-h},\zeta^{j+h}\}
\]

while

\[
F_{j-h}\cap F_{j+h}
=
\{A_j,\zeta^j\}.
\]

A single circle family was now doing two jobs:

- generating final polygon vertices;
- generating future helper centers.

This was the first architecture we found that actually mixed the seed and suffix problems together.

But it did not branch efficiently enough. Its causal dependency graph behaved more like a one-dimensional bootstrap. A sparse seed did not explode into all 257 roots cheaply.

#### Research direction 4 - Mutual-witness networks

We then tried to make helper intersections maximally productive.

If one CC outputs centers \(C,D\), and both

```text
circle C D
circle D C
```

produce two final roots on \(\Gamma\), then one helper intersection supports four final vertices.

For symmetric same-ring centers

\[
C=a\zeta^{m-h},
\qquad
D=a\zeta^{m+h},
\]

requiring a desired final half-offset \(d\) reduces exactly to

\[
\boxed{
(2\cos(2h\theta)-1)a^2
-
2\cos(d\theta)a
+
1
=
0
}.
\]

That gave us a finite parameterized search.

One abstract network looked especially good:

- 12 support circles;
- 64 helper intersections;
- 128 final circles;

for a core score around 527.

But no sufficiently high-incidence nonunit support circles survived the exact/high-precision search. Apparent near-concurrences vanished when recomputed more carefully.

That rejected the parameterized family, not all possible 527 constructions.

#### Research direction 5 - Reciprocal transversals and the 531/549 mirage

For a transversal with center-radius parameter \(b\), define its power parameter

\[
X=b^2-R^2.
\]

To intersect a helper ring of radius \(a\) at half-separation \(h\), the geometry satisfies

\[
\boxed{
X
=
2ab\cos(h\theta)-a^2
}.
\]

For fixed ring type, that is a line in \((b,X)\)-space. Several ring types can share one congruent transversal family only when those lines concur.

The exponent combinatorics looked almost perfect because every nonzero residue mod 257 has a balanced-binary representation

\[
\pm1\pm2\pm4\pm8\pm16\pm32\pm64\pm128.
\]

Splitting the bits suggested an 8-ring by 8-transversal architecture with ideal incidence score around **531** before seeding.

We exhaustively tested all 56 relevant bit splits in the distinct-ring reciprocal model.

None produced the required common transversal geometry.

A simpler two-ring tiling did work combinatorially:

\[
\{\pm1,\pm3,\pm5,\pm7\}
=
\{\pm4\pm3\}
\cup
\{\pm4\pm1\}.
\]

That gave a perfect abstract cover of all 256 roots with ideal incidence accounting around **549**.

But “ideal incidence accounting” hid the real cost:

> the transversal centers and their radius witnesses still had to be constructed legally.

#### Research direction 6 - Productive transversals and the ~517 idea

We also found an exact family in which a transversal itself produces roots. One circle could support a six-root block

\[
\boxed{
\phi+\{\pm k,\pm3k,\pm7k\}
}.
\]

The same transversal also creates two reciprocal-ring centers that define additional root-pair circles.

On paper, this pushed some abstract incidence cores toward **~517**.

Again the blocker was causality: we could not cheaply manufacture the transversal centers from previously existing legal centers and witnesses. Cross-family transition searches returned no useful propagation graph.

#### What the post-solve search showed

The elementary lower bound counts an abstract incidence graph.

A `.geo` file needs a **straight-line causal program**.

Every circle requires:

1. an already-existing center;
2. an already-existing through-point establishing the radius.

Every helper center must itself come from earlier intersections.

That is why an elegant 517-, 531-, or 549-score incidence architecture can still be nowhere close to an executable construction.

This was the most important conceptual result of the 257 post-solve research:

> [!IMPORTANT]
> **Incidence optimality and constructibility-DAG optimality are different problems.**

---
