# Mascot production assets

Derived from `docs/design/mascot-reference.png`, which is the approved
source of truth and is **not** modified by anything here (its checksum
is unchanged; these are separate files, as the registration task
requires).

## How they were made

Each pose was cropped from the reference sheet, then the card background
was removed by **flood-filling inward from the crop's border** rather
than by thresholding luminance. The distinction matters: the mascot's
most recognisable feature is a glossy *black* visor, and a luminance
threshold would erase it along with the background. A flood fill only
clears black that is connected to the edge, so the visor — enclosed by
the white shell — survives.

## Poses

| File | Pose | Used by |
|---|---|---|
| `waving.png` | Welcoming gesture, full body | Dashboard welcome banner |
| `happy.png` | Happy, waving, upper body | Success states |
| `thinking.png` | Neutral, wide-eyed | Loading states |
| `excited.png` | Both hands raised | Completion / celebration |

Only poses with a real consumer are committed. The reference also
contains front, side, back and laptop views; they are extracted the same
way when a surface needs them.

## Limits worth knowing

These are **derived from a reference sheet, not authored assets**. Each
is roughly 180–360px on its longest edge, which is enough for the sizes
they are used at and not enough for a hero treatment or print. The
edges carry some compression softness from the source.

If AgentVerse commissions real mascot artwork, replace these files
rather than scaling them up — and keep the filenames, so no component
has to change.

Do not recolour or restyle them. `docs/design/design-system.md` §6 fixes
the mascot's identity: same proportions, same white body, same visor,
same warm accents.
