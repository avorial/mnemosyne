# Design

## Theme

**Warm-paper dark.** Not a category-reflex dark mode — not navy-blue dashboard dark, not pure-black AI-tool dark. Background is a low-chroma warm brown-black (think a book of stained pages held under a desk lamp at night). The user is glancing on a laptop or phone in mixed lighting — a warm tint reads as habitable across both daylight and evening rather than punishing under either.

Light mode is deferred. If it ever ships, it will be a cream-paper light, not white.

## Color

Strategy: **restrained**. One accent (ochre/amber), used to mark consequence — submit buttons, success state, an active workspace tag. Everything else is neutrals.

All colors in OKLCH. No `#000`, no `#fff`. Every neutral carries a small warm chroma so the palette feels of one piece.

| Token | OKLCH | Use |
|---|---|---|
| `--bg` | `oklch(0.15 0.012 60)` | Page background |
| `--surface` | `oklch(0.19 0.013 65)` | Widget body |
| `--surface-2` | `oklch(0.24 0.012 65)` | Inputs, chips |
| `--border` | `oklch(0.32 0.010 65)` | Hairline dividers |
| `--text` | `oklch(0.95 0.008 80)` | Body |
| `--text-quiet` | `oklch(0.70 0.012 75)` | Secondary copy, meta |
| `--text-faint` | `oklch(0.50 0.010 75)` | Hints, placeholders |
| `--accent` | `oklch(0.74 0.14 70)` | Ochre — primary actions, success |
| `--accent-soft` | `oklch(0.74 0.14 70 / 0.15)` | Accent backgrounds |
| `--danger` | `oklch(0.66 0.18 25)` | Errors — used sparingly |

Hue band stays in the 60-80 range across the neutral stack so the warm tone is consistent. The accent sits at 70 — same warm-ochre family, just chroma-promoted.

## Typography

Two families, both via Google Fonts, both already widely cached:

- **Newsreader** (serif) — headings, widget titles, empty-state copy, "thoughts" surfaces. A modern editorial serif by Production Type. Light optical-size optimization built in via Newsreader's variable axes.
- **Inter** (grotesk) — body, UI controls, inputs, buttons. System fallback to `-apple-system, "Segoe UI", Roboto`.

Scale, 1.250 ratio (major third) between steps. Weight contrast carries the hierarchy, not just size:

| Token | Size | Weight | Family |
|---|---|---|---|
| `--text-xs` | 12px / 1.4 | 400 | Inter |
| `--text-sm` | 14px / 1.5 | 400 | Inter |
| `--text-md` | 16px / 1.6 | 400 | Inter (body default) |
| `--text-lg` | 18px / 1.4 | 500 | Inter |
| `--heading-sm` | 20px / 1.3 | 500 | Newsreader (italic optional) |
| `--heading-md` | 28px / 1.2 | 500 | Newsreader |
| `--heading-lg` | 40px / 1.1 | 400 | Newsreader |

Body line length stays under 70ch.

## Spacing

8px base. Vary across element types — don't apply the same padding everywhere. Widget header sits tighter than widget body; lists breathe differently from forms.

| Token | px |
|---|---|
| `--space-1` | 4 |
| `--space-2` | 8 |
| `--space-3` | 12 |
| `--space-4` | 16 |
| `--space-5` | 24 |
| `--space-6` | 32 |
| `--space-7` | 48 |

## Radius

| Token | px |
|---|---|
| `--radius-sm` | 4 |
| `--radius-md` | 6 |
| `--radius-lg` | 10 |

Larger radii are reserved for surfaces; controls stay tight (≤6px) so they don't look like pill-shaped consumer toys.

## Components

- **Widget chrome**: surface background, no card-border by default — use one hairline `border-bottom` under the header instead of a four-sided card. Reduces the "card-grid" feel even though gridstack is involved.
- **Widget header**: title in Newsreader 18-20px, workspace tag in Inter 11px uppercase letterspaced, muted color. No icon-and-text-and-stats hero pattern.
- **Inputs**: borderless on the body side, a single bottom hairline. Focus is the accent color on the bottom hairline only — no full outline.
- **Buttons**: two styles total. *Primary* is the accent fill, used for submit/save. *Quiet* is text-only, accent on hover. No "secondary" button style — if it's not the primary action, it's a quiet button.
- **Flash**: not a card with an icon. A single line of italic Newsreader at top of the widget, colored by kind, fading after 3s. No border, no background fill.
- **Empty states**: italic Newsreader, one short sentence, no illustration. "Nothing pending." beats "You have no tasks!". Speak to one person.

## Motion

- Transitions: 160ms ease-out-quart (`cubic-bezier(0.5, 1, 0.89, 1)`). No bounce, no elastic, no overshoot.
- Only on direct user action. No hover-pulses on idle elements, no skeleton shimmer, no looped icons.
- `prefers-reduced-motion: reduce` → all transitions become 0ms.

## Layout

- Grid is real (gridstack) but visually quiet. 8px gutter, no visible grid lines.
- Widget tiles do not need to be visually identical sizes — vary intentionally with `default_size`.
- The page background extends to the edges; no max-width container around the whole dashboard. Let the workspace breathe.

## Bans (project-specific, on top of the impeccable shared bans)

- No "Welcome back, Patric" — the dashboard does not greet.
- No hero-metric tile pattern (big-number-with-label-and-sparkline) anywhere.
- No icon + heading + paragraph card pattern.
- No tooltips that explain what a label already explains.
- No saturated category colors (productivity blue, calendar green, github purple). Tags use the same warm neutral family as everything else.
