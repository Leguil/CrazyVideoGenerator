# CLAUDE.md

---

## What this is

`brand/` is a **shared design system** for CrazyLogix applications:

- `tokens.css` — The source of truth. A single CSS file of `--cl-*` custom properties (palette, type, spacing, shape, shadows, status colours, scrim) with an **explicit opt-in dark theme** (`:root[data-theme="dark"]`). Never use `prefers-color-scheme` — the dark block is never applied implicitly.
- `index.html` — Web showcase catalog that renders live from `tokens.css`. Includes a "Live Tokens" panel that measures contrast ratios from computed styles and highlights failures below the floor (4.5:1 text, 3:1 non-text).
- `android.html` — Android Material 3 showcase (phone simulator + component library + Compose token contracts) with three palette variants (CrazyLogix Green, Tech Cobalt, Warm Monet Amber).
- Logo assets — `crazylogix_logo.svg` (vector on white badge), `crazylogix_logo_mono.svg` (`currentColor`, badge-less), plus `.png` variants.

---

## Adoption rules

1. **Import, never copy.** Applications import `@import tokens.css` as the first stylesheet statement. Then they alias their existing local names to `--cl-*`. This is a 10-line reversible change.
2. **This layer stops at the chrome.** Toolbars, panels, rails, dialogs, buttons — yes. Document appearance (Markdown Studio's theme JSON) — no. Brand tokens must never reach document-level rendering.
3. **Two-Tier Application Bar (No Overcrowding).** Do not overcrowd the top application bar. The top header is strictly reserved for brand lockup (`Crazy<ApplicationName>`), global status indicators (e.g. LLM health, database connection), theme switch, settings, and user login/profile. All task, workflow, or workspace actions must reside in the secondary action sub-toolbar (`.action-bar`) docked directly beneath it.

---

## Token structure

Every token lives in `:root` (light) and `:root[data-theme="dark"]` (dark). Type, radius, and spacing are **theme-invariant** and deliberately not repeated in dark.

### Key pairing rules

- **The accent flips its ink in dark.** The light block's accent is `#0e6b3f` with `--cl-accent-text = #ffffff`. The dark block lifts the base to `#10b981` so it reads on `#0b0f19` — the ink must therefore go dark (`#022c22`). Carrying `#ffffff` across gives 2.54:1 (under the 3:1 floor).
- **The frame lifts to `#16a34a` in dark.** The light frame `#0e6b3f` sits at 2.91:1 on the dark ground, so the dark frame is the lifted green. The chrome border is **the same color in both themes** — it is what separates the bar from the work.
- **Ink and ground move together.** Any token named `*-text`, `*-on-*`, or `*-chrome-text` is the ink for one specific ground. Re-tone a ground and its ink is re-toned in the same edit.

### Floors

| Floor | Applies to |
|---|---|
| 4.5:1 | All text tokens |
| 3:1 | Non-text indicators (frames, rings, borders-strong) |

The Live Tokens panel in `index.html` measures these against `--cl-panel` and shows red pills on failures.

---

## Dark theme activation

The dark block is under explicit selectors only:

```css
:root[data-theme="dark"],
body[data-theme="dark"],
.dark
```

Never attach it to `prefers-color-scheme`. Applications opt in by reading `localStorage["crazylogix_theme"]` and setting `data-theme`/adding `.dark` before first paint.

---

## Logo asset guidelines

| Asset | Format | Rules |
|---|---|---|
| `crazylogix_logo.svg` | SVG on white badge | Reads on any ground. The badge means it works. |
| `crazylogix_logo_mono.svg` | SVG, `currentColor` | Badge-less, drawn in `currentColor`. Inline it or use as a CSS `mask`. Cannot be an `<img>` — `currentColor` does not cross an `<img>` boundary. |
| `crazylogix_logo.png` | PNG, true alpha | Transparent raster. The matte is gone; the original baked-in `#f3f3f3` was stripped. |
| `crazylogix_logo_dark.png` | PNG, true alpha | Ink lifted to `#16a34a` for near-black grounds. No vector lockup exists for the wordmark. |
| `logoandname.png` | PNG, true alpha | Full lockup (mark + wordmark). Light and dark variants only. The wordmark in light is navy `#0d2446`; dark reverses to `#e2e8f0`. |

---

## What is deliberately missing

- **Faces.** Inter and JetBrains Mono are named as stacks but not bundled by every app, and the showcase pulls them from Google Fonts, which the products forbid at runtime — so both stacks degrade to the platform UI face rather than depending on a webfont. An app that bundles `@fontsource/inter` gets the real thing for free.
- **A vector lockup.** Only rasters exist for mark+name. Anything needing the wordmark at arbitrary size needs the mark + real type.
- **Component CSS.** Only tokens and marks ship here. `index.html`'s `.tk-*` rules are illustration code for the catalog, not reusable.
- **Brand CLAUDE.md copy.** This project has its own `CLAUDE.md` in the root that references this directory.
