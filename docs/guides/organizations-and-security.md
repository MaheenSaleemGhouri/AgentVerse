# Organizations, roles and security

A guide to the enterprise features: organizations, the seven built-in
roles, custom roles, and the Security Center.

## Organizations

An organization groups several workspaces under one identity — for
single sign-on, a shared password policy, directory sync and branding.

**An organization does not give anyone access to its workspaces.** This
is the most important thing to understand about the model. Adding
someone to your organization does not let them open any workspace inside
it; they still need to be invited to each workspace individually. Even
the organization owner has no access to a workspace they are not a
member of.

That is deliberate. Attaching a workspace to an organization is an
administrative act, and it must not quietly hand a group of people
access to data they could not see the day before.

### Creating one

**Organizations → New organization.** You become its owner.

### Attaching a workspace

From **Organization → Settings**, attach a workspace you own. You need
to be an admin of the organization *and* the owner of the workspace —
an organization admin cannot absorb a workspace belonging to someone
else.

Detaching leaves the workspace and everything in it completely
untouched. So does deleting the organization: its workspaces are
detached, never deleted.

### The organization dashboard

**Organizations → [your organization]** shows how many workspaces and
members it has, and for each member: their role, when they last signed
in, and what device they signed in from.

A member shows as **signed in** when they hold an unexpired session.
That is not a live "online" indicator — someone who closed their laptop
an hour ago still shows as signed in until their session expires. We
show what we actually know rather than guessing.

## Roles

Seven built-in roles, each able to do everything the ones below it can:

| Role | Can |
|---|---|
| **Owner** | everything, plus transfer ownership and delete the workspace |
| **Admin** | everything below, plus manage billing |
| **Manager** | invite and remove members, assign roles, change workspace settings |
| **Developer** | delete agents/teams/knowledge, manage MCP connections and API keys |
| **Analyst** | view analytics, audit logs and billing |
| **Member** | run agents; create and edit agents, teams and knowledge bases |
| **Viewer** | read-only |

**Team → Roles** shows the exact permissions each role holds, read live
from the server. It is not a copy maintained separately from what is
enforced.

### Ownership

The last owner cannot be removed or demoted. To hand a workspace over,
transfer ownership — this is a single deliberate action, not something
that can happen as a side effect of editing roles.

## Custom roles

When one of the seven built-ins is close but not exact, define your own:
**Team → Custom roles → New role**.

Pick the closest built-in role as the base, then tick the extra
permissions to add. Permissions the base role already includes are shown
ticked and locked — you cannot grant something twice, and you cannot
take anything away.

**A custom role can only add.** There is no way to build "an admin who
cannot see billing". If someone should not have a capability, start from
a lower role and add what they need. Subtraction would make it
impossible to reason about what "at least admin" means anywhere else in
the product.

Deleting a custom role does not lock anyone out — holders fall back to
their base role.

## Security Center

**Settings → Security.**

### Security score

A score out of 100 with the breakdown that produced it. Every line that
loses points tells you specifically what to fix — the number on its own
would not be actionable.

Two-factor coverage is proportional, so a rollout shows progress rather
than scoring nothing until the last person finishes.

### Your activity

Sign-ins, device changes and failed attempts on your own account. Every
member sees their own; admins additionally see a workspace-wide feed.

Repeated failed sign-ins in a short window are flagged as **critical** —
that pattern is an attack, not forgetfulness.

### Trusted devices

Confirm a device and signing in from it stops being reported as new.
Anything not on the list produces a new-device event.

**Revoking a device does not sign it out.** It only stops the device
being recognised, so the next sign-in from it is reported. To sign a
device out, revoke its session in the Sessions panel above.

### Password policy

**Organization → Settings → Password policy.** Applies to everyone
signing in with a password in that organization.

Until you set one, the platform default applies (12 characters, upper
and lower case, a digit) — the badge says **platform default** rather
than **configured** so you can tell the difference between a decision
and an absence of one.

You cannot set a minimum below 8 characters. A policy that makes the
product less safe than it is with no policy at all is not a setting we
offer.

Forced password expiry is off by default. Periodic rotation is no longer
recommended practice; the option exists for organizations whose own
compliance regime requires it.

## API keys

**Settings → API keys.**

Choose an expiry when issuing a key — 30 days, 90 days, a year, or
never. An expired key stops authenticating immediately.

Keys that never expire count against your security score. Existing keys
are unaffected: anything issued before expiry shipped continues to work
indefinitely until you rotate it.

Each key shows when it was last used and how many calls it has served,
which is what tells you whether an old key is still load-bearing before
you revoke it.

Rotating a key issues a replacement with the **same lifetime** as the
original, not the same expiry date — rotating a 90-day key gives you
another 90 days, not whatever was left.

## Audit logs

**Audit logs** (admins and owners).

An activity graph shows daily volume over the last 30 days, and the
table below it is filterable and paginated.

**Export** downloads the log as CSV or JSON, up to 10,000 most recent
entries. Use the JSON export if you are feeding another system — it
keeps real types instead of flattening everything to text.
