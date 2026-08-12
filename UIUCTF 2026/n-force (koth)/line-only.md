<a id="part-v"></a>
## Part V - The line-only bug

The `17-line` and `257-line` challenges had a pretty fundamental issue

Under the published semantics, no legitimate construction could get started.

<a id="line-bootstrap"></a>
### Step 1 - Bootstrap deadlock

The initial state contains only

\[
O=(0,0),
\qquad
P=(1,0),
\]

and no lines or circles.

Line mode requires the first non-comment command to be a `circle`.

The natural command is

```text
circle O P C0
```

but this creates only a circle object.

It creates **no point**.

After that first command, line mode rejects:

```text
circle
meets_circle_circle
meets_line_circle
```

so the only remaining geometric commands are

```text
line
meets_line_line
```

The only points are still \(O,P\).

Therefore every constructible line is geometrically the same line \(OP\):

```text
line O P L1
line P O L2
```

Intersecting them cannot produce a new point because they are coincident; the determinant is zero and the intersection routine rejects the operation.

So we have an invariant:

\[
\boxed{\text{the constructible point set remains }\{O,P\}.}
\]

A valid polygon needs at least three distinct points.

Therefore, under the deployed line-language semantics,

\[
\boxed{
\text{no legitimate regular }n\text{-gon exists for any }n\ge3.
}
\]

In particular,

```text
17-line:  legitimate exact feasible set is empty
257-line: legitimate exact feasible set is empty
```

This is even stronger than the normal straightedge-only impossibility issue. The DSL cannot create a third point.

---

<a id="line-live-tests"></a>
### Step 2 - Live tests confirmed the parser was actually bugged

We did not want to conclude that a helper function was authoritative if the server injected hidden initial geometry.

So we tested the live submission.

A submission containing the required initial circle, two copies of \(OP\), and their attempted LL intersection reached the worker and returned:

```text
Error in meets_line_line: lines L1 and L2 are parallel!
```

We then tested the operations that would have made the initial circle useful. `meets_line_circle` and a second circle were rejected synchronously; one live response was:

```text
This challenge only allows lines (after the initial circle) - no circle commands permitted
```

The frontend did not insert hidden bootstrap geometry before upload.

So the live ordinary path matched the deadlocked semantics.

---

<a id="line-organizer"></a>
### Step 3 - We asked the organizers

The leaderboard still contained line-only entries, so we asked whether the intended challenge had additional starting geometry.

The organizer's early responses made clear that a starting circle had been intended. After further review, the conclusion recorded in our contest chat was:

> “this is a known bug, but we have decided to keep the parser as is - if you decide to submit valid submissions, we may award such in writeups”

For our legitimate-solve record, we therefore do **not** claim a 17-line or 257-line solve. The legitimate result is the impossibility proof for the language that was actually deployed.

---
