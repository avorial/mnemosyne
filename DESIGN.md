# Design

## Theme

**Avorial nocturne.** Mnemosyne is a room in the same house as avorial.com, at night. Deep violet near-black surfaces, warm cream ink, a static atmosphere of purple light from above and a low ember of gold at the foot of the page, and a film grain that keeps the dark from reading as flat pixels. The studio site is the loud front hall; the dashboard is the quiet study behind it. Same materials, lower voice.

This is not the productivity-dark-mode cliché (no pure black, no cyan, no glass cards as decoration). The palette is inherited from a real place: Patric's studio brand.

## Color

Strategy: **restrained, with two metals.** Violet-tinted neutrals carry everything. The two accent metals have fixed jobs:

- **Gold answers the hand.** Hover, focus, the active workspace underline, live markers, day labels. Gold never fills a surface; it draws lines and lights edges.
- **Purple commits.** The primary verb per widget (save, add, send) is a purple gradient fill. Selection tints use purple at low alpha. Purple appears at most once per widget as a fill.

All colors in OKLCH. Violet hue band 295–300 for neutrals; text leans warm (hue 90) so it reads as cream, not white.

| Token | OKLCH | Use |
|---|---|---|
| `--bg` | `oklch(0.13 0.025 295)` | Page (night) |
| `--surface` | `oklch(0.17 0.032 295)` | Tile base tone |
| `--surface-2` | `oklch(0.21 0.040 295)` | Menus, chips, selects |
| `--border` | `oklch(0.70 0.10 295 / 0.13)` | Hairlines |
| `--border-strong` | `oklch(0.72 0.11 295 / 0.30)` | Input hairlines, hover borders |
| `--text` | `oklch(0.93 0.018 90)` | Body (warm cream) |
| `--text-quiet` | `oklch(0.75 0.045 300)` | Secondary copy (lavender) |
| `--text-faint` | `oklch(0.55 0.040 300)` | Hints, placeholders, micro-labels |
| `--purple` | `oklch(0.66 0.18 295)` | Commit gradient end, selection tints |
| `--purple-deep` | `oklch(0.47 0.20 295)` | Commit gradient start |
| `--gold` | `oklch(0.76 0.10 80)` | Hover borders, focus hairlines, day labels |
| `--gold-bright` | `oklch(0.85 0.10 85)` | Hover text, success flashes |
| `--danger` | `oklch(0.68 0.16 25)` | Errors |

Widget tiles are translucent gradients over the page (`oklch(0.19 0.038 295 / 0.78)` to `oklch(0.16 0.030 295 / 0.55)`) so the atmosphere reads through them.

## Typography

Three voices, each with one job:

- **Fraunces** (variable: opsz, wght, SOFT) — the moments that speak: wordmark, login h1, empty-state h2, and widget titles. Wordmark is uppercase, tracked 0.18em, the same gesture as the avorial.com logotype. Widget titles run 19px at weight 380, `opsz 144, SOFT 50`.
- **Geist** — everything the user reads or types. Body, inputs, list content, menu items.
- **Geist Mono** — everything that labels or operates. Buttons, workspace toggle, tags, times, dates, ago-stamps, hints, section labels. Always small (10–11px), uppercase, tracked 0.08–0.22em.

The rule in one line: **serif speaks, sans reads, mono operates.**

| Token | Size | Family | Use |
|---|---|---|---|
| micro | 10px mono 500, tracked 0.22em | Geist Mono | ws-tags, day labels, status |
| control | 11px mono 500, tracked 0.12em, uppercase | Geist Mono | buttons, toggle, menu summary |
| meta | 12–13px | Geist | flashes, hints, secondary copy |
| body | 14–15px | Geist | list rows, inputs |
| widget title | 19px, wght 380 | Fraunces | widget h3 |
| empty h2 | 32px, wght 330, italic | Fraunces | dashboard empty state |
| login h1 | 44px, wght 330 | Fraunces | login |

## Texture & atmosphere

Two fixed pseudo-layers on `body`, both **static** (no drift animation; ambient motion is banned in this product):

- `body::before` — three radial gradients: deep purple upper-left, lighter purple upper-right, faint gold at the bottom center. Alphas 0.05–0.16.
- `body::after` — SVG feTurbulence grain at 0.45 opacity, overlay blend.

## Spacing

8px base, unchanged from the previous system.

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

Sharp, like the studio site: 2px on buttons, chips, menus; 4px on widget tiles and dropzones. Nothing rounder.

## Components

- **Widget chrome**: translucent gradient tile, 1px `--border`, 4px radius. Hover raises the border to `--border-strong` and reveals a gold hairline along the top edge (the avorial card gesture). Header hairline separates title from body. Header cursor is `grab`.
- **Buttons, quiet**: mono uppercase 11px, 1px `--border`, transparent. Hover: gold text, gold border, gold-glow tint.
- **Buttons, commit**: purple gradient fill with purple glow shadow, scoped to capture forms and login only. Hover swaps the ring to gold. Every other `type=submit` (refresh, toggle, nav) stays quiet.
- **Text buttons** (`.link`): borderless quiet text, hover to `--gold-bright`.
- **Inputs**: bottom hairline only (`--border-strong`), focus moves it to gold. Caret is gold.
- **Workspace toggle**: mono uppercase text; the active workspace carries a gold underline. No boxes, no fills.
- **Add-widget menu**: bordered mono summary control; popover on `--surface-2` with strong border and deep shadow; rows are name + faint description, purple-tint hover.
- **Flash**: single line, clamped to 3 lines (`-webkit-line-clamp`) so raw API errors cannot flood a tile. Success = `--gold-bright` medium. Error = `--danger`.
- **Dropzone**: dashed `--border-strong`; dragover turns it solid gold with a gold-glow fill.
- **Empty states**: italic Fraunces, one short sentence.

## Motion

- 180ms `ease-out-quart` on color/border/shadow; 300ms ease on the widget hover hairline.
- Never animate layout properties.
- `prefers-reduced-motion: reduce` zeroes every transition.
- No ambient or idle motion. The atmosphere and grain are static.

## Layout

- Grid: gridstack at 12 columns, 80px cell height, 8px gutter, no visible grid lines.
- Topbar is sticky with an 18px backdrop blur over the night surface (purposeful glass: it keeps workspace and capture controls reachable while scrolling).
- Page background extends edge to edge; no max-width container.
- **Phone (≤ 720px)**: gridstack collapses to a vertical stack; tile content switches to static positioning so tall content grows the tile instead of clipping. Email hides from the topbar.

## Bans (project-specific, on top of impeccable's shared bans)

- No "Welcome back, Patric."
- No hero-metric tiles.
- No icon + heading + paragraph card pattern.
- No Fraunces in buttons, labels, data, or list rows. Serif speaks; it does not operate.
- No purple fills outside the one commit button per widget.
- No gold fills, ever. Gold is lines, edges, and text only.
- No saturated category colors (productivity blue, calendar green).
- No animated atmosphere. The gradients and grain hold still.
- No em dashes in copy. Periods, commas, colons, semicolons, parentheses.
