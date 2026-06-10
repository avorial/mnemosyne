# Product

## Register

product

## Users

One user — Patric. Uses Mnemosyne across the day from a desktop browser at home, a phone in transit, and occasionally a second laptop. Modes alternate between *capture* (5-second drop of a thought, image, link, or task) and *glance* (peripheral check of today's calendar, open todos, recent activity). A found note can be read back and lightly edited in place (search → open → read → fix a line → save); every save commits to the vault like any capture. Obsidian is the archive: graph, backlinks, long-form browsing, restructuring.

## Product Purpose

A single calm surface that consolidates the moments where fragmented tools used to fight each other:

- thoughts → committed into a git-backed Obsidian vault
- todos → mirrored with Asana
- calendar → glanced (Google personal, Microsoft 365 work)
- activity → recent GitHub commits/PRs surfaced where the rest of the context already lives

Success looks like: opening Mnemosyne feels like opening a paper notebook, not like opening a SaaS app. Capture takes one motion. Glances take one second.

## Brand Personality

Three words: **considered, quiet, durable**.

Tone: a well-made fountain pen, not a startup demo. Confident enough to leave space empty. Doesn't over-explain itself, doesn't congratulate the user for routine actions, doesn't decorate with stock illustrations or gradients. Personal — written for one person.

## Anti-references

- **Generic SaaS dashboards** — hero metric tiles, identical card grids, "Welcome back, Patric!" empty states, gradient accent stripes, primary-blue-button-everywhere. The Linear/Stripe-clone aesthetic 90% of B2B tools collapse to.
- **Obsidian-as-is** — markdown rendering, link graph, ribbon icons. Mnemosyne is the *capture surface that feeds Obsidian*, not a re-skin of Obsidian. The two should feel meaningfully different so it's obvious which is "in the moment" and which is "the archive".
- **Cliché productivity dark mode** — pure `#000` backgrounds, saturated cyan accents, glassmorphism cards, neon-on-black. We're not selling AI.

## Design Principles

1. **Capture should feel as low-friction as paper.** Zero-chrome inputs. Don't ask for fields the user doesn't need to fill. Submitting a thought is one action, not three.
2. **Glance, don't read.** Calendar, todos, and activity are shown at a density that supports peripheral awareness. If a number requires you to lean in, the density is wrong.
3. **Different widgets, different shapes.** No identical card grids. Spacing carries separation more than borders do. Each widget is allowed to have its own internal rhythm.
4. **Restraint over color.** One accent earns its place. Neutrals carry the design. The accent is for state and consequence, never decoration.
5. **Serif for thought, grotesk for action.** Type signals mode — the things you read carry a serif voice; the things you click carry a grotesk voice. This is the design's whole personality compressed into one rule.

## Accessibility & Inclusion

- **Contrast**: WCAG AA for body text on every surface (≥ 4.5:1). Larger text and decorative elements may relax.
- **Reduced motion**: no ambient or idle animation. Motion exists only as direct feedback to a user action (button press, layout drag, swap-in). `prefers-reduced-motion` users get the same UI with all transitions zeroed.
- **Color is never the only signal** for state (completed vs open, error vs success). Always paired with text, weight, icon, or strikethrough.
- **Keyboard**: the capture path (focus input → type → Shift+Enter) works without touching the mouse. Drag-and-drop on dropzones is augmentation, not the only path.
