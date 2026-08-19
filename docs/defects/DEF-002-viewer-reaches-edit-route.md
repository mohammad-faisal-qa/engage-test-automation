# DEF-002 — A viewer can open the segment editor by URL

| | |
|---|---|
| **Component** | engage-app · `web/src/views/segments.js`, `web/src/router.js` |
| **Severity** | Low — no data is exposed or modified; the server refuses every write |
| **Priority** | Low — defence in depth, not a vulnerability |
| **Status** | Open — reported, deliberately not treated as urgent |
| **Found** | 2026-08-18, while writing the Phase 5 RBAC interface tests |

## Summary

The segments list hides the **Edit** link from a viewer, but the editor is a route
(`#/segments/{id}`) and the route is not role-guarded. A viewer who types or bookmarks it gets a
fully rendered editing form, including an enabled **Save** button.

Saving is refused: the API returns `403` and the form shows the error. Nothing changes.

## Impact

**No security impact.** The authorisation boundary is the API and it holds — verified, not assumed:
the test reads the segment back through the API afterwards and confirms its name is unchanged.

The impact is on the experience and on what the interface implies:

- A read-only user is shown controls that cannot work, and only discovers this after filling the
  form in and pressing Save. Being offered an action and then refused is worse than never being
  offered it.
- It makes the interface's own permission model inconsistent — the list has one rule and the editor
  has none — which is the state in which a *future* editor screen forgets its check and nobody
  notices, because inconsistency is already normal here.

## Steps to reproduce

1. Sign in as `viewer@acme.example.com`.
2. Go to `#/segments` — no Edit links appear, correctly.
3. Navigate directly to `#/segments/1`.
4. The editor renders. Change the name and press **Save**.

## Expected vs actual

| | |
|---|---|
| **Expected** | The route is refused for a viewer — redirected to the list, or shown a read-only form with no Save |
| **Actual** | The editor renders with an enabled Save; the attempt is refused by the API with `403` and the form shows the error |
| **Data** | Unchanged — confirmed via the API before and after |

## Root cause

`router.js` guards on *authentication* only:

```js
if (name !== 'login' && !auth.isLoggedIn) return navigate('/login')
```

There is no role dimension to the guard. Individual views apply `auth.can('editor')` to decide which
*controls* to render — the list uses it for the Edit link — but the segment editor renders its form
and Save button unconditionally once the route resolves.

## Why testing missed it

It did not, exactly — it was found the first time anyone drove the interface as a viewer, in the
phase that introduced role-aware browser contexts. Before that, every UI test ran as an admin,
because a single shared signed-in session is the fast default and roles are extra setup.

The lesson worth keeping: **a suite that only ever runs as its most privileged user cannot see this
class of defect at all.** It is not that the assertion was wrong; the situation was never created.

## The test we wrote, and what it deliberately does not assert

`test_a_viewer_reaching_the_edit_route_directly_cannot_save` asserts what actually holds — the form
opens, the save is refused, the segment is unchanged. It does **not** assert that the route is
blocked, because it is not, and a test asserting that would be encoding a wish rather than the
behaviour. If the route is later guarded, that test should be tightened in the same commit.

## Suggested fix

Add a role requirement to the route table, so the guard lives in one place rather than in each
view's markup — for example `route('segments/:id', segmentEditorView, { minimumRole: 'editor' })`,
with the router redirecting when the session's role is insufficient.
