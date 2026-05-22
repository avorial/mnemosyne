# Design

## Theme

**Pinewood light.** A tan, wood-toned page; widget tiles sit as slightly darker wood inset into it. Not a category-reflex theme — not white-and-teal SaaS light, not cream-paper editorial. The metaphor is a writing desk made from a single piece of pine: the surface, the inset tiles, and the wordmark all share one warm hue band; nothing reads as decoration.

Dark mode is deferred. If it ever ships, it should feel like the same desk at night, not a separate palette.

## Color

Strategy: **restrained**. One accent (deep burnt-sienna) used at most once per screen on the submit button. Active states do not use the accent — they use a surface-tint shift (selected workspace shows as a darker tile, not a colored one).

All colors in OKLCH. Tints kept in the warm hue band 60–80 so the whole palette reads as one piece of wood.

| Token | OKLCH | Use |
|---|---|---|
| `--bg` | `oklch(0.84 0.045 75)` | Page (pinewood) |
| `--surface` | `oklch(0.78 0.050 75)` | Widget tile (darker wood) |
| `--surface-2` | `oklch(0.73 0.052 75)` | Inputs, chips, active-state tints |
| `--border` | `oklch(0.62 0.055 70)` | Hairlines |
| `--text` | `oklch(0.22 0.020 60)` | Body |
| `--text-quiet` | `oklch(0.42 0.020 65)` | Secondary copy |
| `--text-faint` | `oklch(0.55 0.022 70)` | Hints, placeholders, micro-labels |
| `--accent` | `oklch(0.45 0.12 35)` | Burnt sienna — submit fills only |
| `--accent-soft` | `oklch(0.45 0.12 35 / 0.10)` | Reserved (not currently used) |
| `--on-accent` | `oklch(0.96 0.012 80)` | Text on the accent fill |
| `--danger` | `oklch(0.45 0.18 25)` | Errors |

The accent's job is **exactly one** per screen: the primary verb. Active-workspace marker is a `--surface-2` background tint, not a color. Bookmark hover is an underline shift, not an accent. Drag highlight is a solid `--text` outline, not an accent. Success flash is `--text` at medium weight, not green. The accent stays scarce so when it appears, it means *go*.

## Typography

One sans family carries the entire UI. One serif moment carries the brand.

- **Inter** — everything else. Body, UI controls, inputs, buttons, widget headers, lists, flashes. System fallback to `-apple-system, "Segoe UI", Roboto`.
- **Georgia** (system-stack serif, with Iowan Old Style and Times New Roman as fallbacks) — used in exactly three places: the `.brand` wordmark, the `.login h1`, and the empty-dashboard `.empty h2`. All set in italic. These are the moments where the design speaks; everywhere else, Inter does the work. **The serif is reserved**. Adding a fourth serif use anywhere else breaks the system.

Why Georgia? It ships on every device. No extra font request. It carries a quietly classical voice without trying to be editorial-precious. A pinewood desk wouldn't have a Display-Pro Variable Type Family bolted to it.

Scale, weight-led hierarchy:

| Token | Size | Weight | Family | Use |
|---|---|---|---|---|
| `--text-xs` | 11px | 500 | Inter | uppercase tags, micro-labels |
| `--text-sm` | 13px | 400 | Inter | meta, flashes, hints |
| `--text-md` | 15px | 400 | Inter | body default |
| `--widget-title` | 16px | 600 | Inter | widget header h3 |
| `--brand` | 22px | 400 italic | Georgia | topbar wordmark |
| `--display-md` | 28px | 400 italic | Georgia | dashboard empty h2 |
| `--display-lg` | 36px | 400 italic | Georgia | login h1 |

Tracking is tight on Inter (-0.005em to -0.015em depending on size). Georgia ships with its own metrics; we don't override.

## Spacing

8px base. Vary by element role — widget headers sit tighter than widget bodies; lists breathe differently from forms.

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

| Token | px | Where |
|---|---|---|
| `--radius-sm` | 4 | Inline chips, small affordances |
| `--radius-md` | 6 | Buttons, selects, popovers |
| `--radius-lg` | 10 | Widget tiles |

## Components

- **Widget chrome**: `--surface` background, 1px `--border` outline, `--radius-lg`. Hairline under the header separates title from body. Tiles look inset into the page, not floated above it.
- **Widget header**: 16px Inter 600, the workspace tag at 11px Inter 500 uppercase tracked.
- **Inputs**: borderless on the body side, bottom hairline only. Focus moves the hairline to `--text` (not accent — focus is acknowledgment, not consequence).
- **Buttons**: two styles. *Primary* is `--accent` fill with `--on-accent` text, used for submit actions exclusively. *Quiet* is text-only at `--text-quiet`, hover to `--text`. No outlined-secondary surface button.
- **Workspace toggle**: active button gets a `--surface-2` background tint. No accent.
- **Flash**: single inline line, no card, no icon. Success = `--text` medium weight. Error = `--danger` text. Fades after 3s.
- **Dropzone**: 1px dashed `--border`. Dragover = solid `--text` outline. No background fill, no accent tint.
- **Bookmark hover**: text stays the same color; an underline appears in `--text`. No accent.
- **Empty states**: italic Georgia, one short sentence. Same voice as the brand.

## Motion

- 160ms `ease-out-quart` (`cubic-bezier(0.5, 1, 0.89, 1)`) on color/border transitions.
- Never animate layout properties.
- `prefers-reduced-motion: reduce` zeroes every transition.
- No ambient or idle motion. No hover-pulse on quiet elements.

## Layout

- Grid: gridstack at 12 columns, 80px cell height, 8px gutter, no visible grid lines.
- Widget tiles vary in size intentionally via their `default_size`. No identical-card grid.
- Page background extends edge to edge; no max-width container.
- **Phone (≤ 720px)**: gridstack collapses to a vertical stack. Each widget gets full width and a minimum height of 240px. The drag-and-resize grid is desktop-only behavior; on phone we surrender the grid and let widgets read like a column.

## Bans (project-specific, on top of impeccable's shared bans)

- No "Welcome back, Patric."
- No hero-metric tiles.
- No icon + heading + paragraph card pattern.
- No serif outside the three reserved moments (brand, login h1, dashboard empty h2).
- No accent outside primary submit buttons.
- No saturated category colors (productivity blue, calendar green). Everything stays in the warm hue band.
- No em dashes in copy. Periods, commas, colons, semicolons, parentheses.
