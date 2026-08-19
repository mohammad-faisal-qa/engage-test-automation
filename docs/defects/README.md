# Defects

Real findings from building and running this suite, in the format a QA Lead would file them:
business impact first, severity and priority set **separately**, and a "why testing missed it"
section on every one.

That last section is the point of keeping these. A defect report that stops at the fix has taught
nobody anything; the question worth answering is why the system that was supposed to catch it did
not.

| ID | Title | Severity | Priority | Status |
|---|---|---|---|---|
| [DEF-001](DEF-001-delete-contact-with-deliveries-returns-500.md) | Deleting a contact that has deliveries returns 500 | High | High | Open |
| [DEF-002](DEF-002-viewer-reaches-edit-route.md) | A viewer can open the segment editor by URL | Low | Low | Open |
| [DEF-003](DEF-003-sticky-wait-always-succeeds.md) | A wait that always succeeded, in our own framework | High | High | Fixed |
| [DEF-004](DEF-004-ci-only-connection-reset.md) | Connection reset in CI only, and a wrong first diagnosis | Medium | High | Cause found — same as DEF-001 |

**DEF-001 and DEF-004 turned out to be one defect seen from two ends.** They are kept as separate
reports because they were found separately, investigated separately, and cost differently — and
because the link between them is the most useful thing in either. Merging them would hide it.

## On severity versus priority

They are different questions and collapsing them is how triage goes wrong.

**Severity** is about consequence: what happens when it occurs. **Priority** is about scheduling:
when we act.

DEF-002 is the clearest illustration. A viewer reaching an edit form *sounds* alarming, and its
severity is **Low** — the API refuses every write and the data is verifiably unchanged. Its priority
is Low too, but for an unrelated reason: it is defence in depth, and the depth beneath it holds.

DEF-003 runs the other way. It is a defect in our own test code, invisible to any user, and it is
**High/High** — because a suite that reports green while asserting against stale state is worse than
no suite. Nothing about that is visible in a bug's user-facing description, which is exactly why the
two axes are kept apart.
