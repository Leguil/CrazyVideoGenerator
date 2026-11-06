# brand/

The CrazyLogix look and feel — **"Insanely Simple"** — as files the applications
may import. Decided 2026-09-02, out of [[crazylogix-design-system]].

## What is in here

| File | What it is |
| --- | --- |
| `tokens.css` | The shared chrome palette, type stacks, radii and spacing as `--cl-*` custom properties, light and dark. The file applications import. |
| `crazylogix_logo.svg` | The mark, vector, on its white badge disc. Prefer this one; the badge means it reads on either ground. |
| `crazylogix_logo_mono.svg` | The mark, vector, badge-less and drawn in `currentColor`. For placing the mark directly on chrome so it follows the theme. Inline it or use it as a CSS `mask` — `currentColor` does not cross an `<img>` boundary. |
| `crazylogix_logo.png` | The mark, raster with true alpha, for anywhere SVG will not go. |
| `crazylogix_logo_dark.png` | The same mark with the ink lifted to `#16a34a`, for near-black grounds. |
| `logoandname.png` | Mark plus wordmark, raster with true alpha. Light grounds only — the wordmark is navy. |
| `logoandname_dark.png` | The lockup reversed for dark grounds: ink `#16a34a`, wordmark `#e2e8f0`. There is no vector lockup, so this pair is the only answer for the wordmark. |
| `index.html` | The web look-and-feel showcase: brand assets, components, toolbars, tables, modals. Open it in a browser. |
| `android.html` | The Android showcase: Material 3 tokens and Compose components in a phone simulator, for [[android-app-skeleton]] and [[idea-manager-android]]. |

Both showcases came from the 2026-08-29 research and moved here on 2026-09-02 so the
assets and the catalog that displays them stay together — the showcases reference the
logos by bare filename, so they must not be separated.

## Rules

- **Applications import; they do not copy.** A copied token file drifts silently, which
  is the failure this folder exists to prevent.
- **This layer stops at the *chrome*.** Toolbars, panels, rails, dialogs, buttons — the
  parts that are the same in every application. It must not reach into a *document*:
  Markdown Studio's document appearance comes from the user's own theme JSON
  (`--md-*`, set by `theme/apply.ts`), and putting brand colours there would print
  CrazyLogix's palette on somebody else's page. See [[crazylogix-design-system]] for why
  that boundary is load-bearing rather than tidy.
- **The showcases load `cdn.tailwindcss.com`.** That is fine for a catalog opened by
  hand and forbidden in a product — the applications are offline-capable with no runtime
  CDN (R-9.3). So the showcases demonstrate a look, they are not a source to copy from.
  The one exception is `index.html`'s **Live Tokens** section, which imports `tokens.css`
  and paints from nothing else. It is there because the rest of the catalog is hardcoded
  Tailwind: for a while the page only *mentioned* `--cl-*` in label text, the token file
  was never rendered anywhere, and the dark block shipped having never been looked at.
- **Every ink and its ground move together.** A token named `*-text`, `*-on-*` or
  `*-chrome-text` belongs to one specific ground. Re-tone a ground in one theme and its
  ink is re-toned in the same edit — a light ink carried unchanged into the dark block
  is how white ended up on emerald at 2.54:1. The Live Tokens panel measures the pairs
  from live computed styles and shows a red pill when one drops below its floor: 4.5:1
  for text, 3:1 for a frame, ring or other non-text indicator.
- **Both showcases persist the theme under `localStorage["crazylogix_theme"]`** and apply
  it in an inline `<head>` script before first paint. Applications use the same key.
- **Green Framing across Chrome.** Every application chrome bar, header boundary, and
  primary dialog frame is framed in CrazyLogix Primary Green (`#0e6b3f`, `--cl-frame-border`,
  `--cl-chrome-border`) to establish immediate visual identity and structural framing across
  all products.
- **Two-Tier Application Bar (Top Chrome + Sub-Toolbar).** Applications with top-level workspace actions
  follow a two-tier chrome structure:
  1. **Top Application Bar (`header`):** Dark chrome (`--cl-chrome`), framed with Primary Green (`--cl-frame-border` / `--cl-chrome-border`), holding the brand lockup (`Crazy<ApplicationName>`), project title/badge, and global utilities (health indicator, theme switcher, settings).
  2. **Action Toolbar (`.action-bar`):** Sits directly below the green-framed top bar, styled on `--cl-panel` with `--cl-border` boundary and subtle elevation (`--cl-shadow-subtle`), housing primary actions (`.btn-action` with 14px icon, label, hover highlight, and disabled state).

## Guidelines

### 1. Do Not Overcrowd the Top Toolbar
The top application header (`header` / `--cl-chrome`) represents the signature identity of the application and must remain clean, uncluttered, and strictly reserved for global identity and high-level utilities.

- **Permitted in the Top Toolbar:**
  - **Brand Lockup:** Vector logo badge, `Crazy<ApplicationName>`, and `CrazyLogix • Insanely Simple` subtitle.
  - **Global System Status:** Key backend/service health indicators (e.g., LLM service connectivity, Database connection status, core engine state).
  - **Global Utilities & User Actions:** Look & Feel / Theme switch (Dark/Light), Settings dialog trigger, User account/authentication action (e.g., Login/Profile).
- **Prohibited in the Top Toolbar (Use a Sub-Toolbar):**
  - Workflow, task, or document-level actions (e.g., *New*, *Load*, *Open*, *Save*, *Manage*, *Run*, *Unload*, *Export*, *Edit Spec*).
  - Any action that operates on the active workspace or content must never be placed in the top application header.

### 2. Use a Sub-Toolbar for Actions
Applications requiring workspace, document, or execution commands must dock a dedicated **secondary action toolbar** (`.action-bar`) directly beneath the top header:
- **Visual Grounding:** Styled with `--cl-panel`, a clean bottom boundary (`--cl-border`), and subtle elevation (`--cl-shadow-subtle`).
- **Action Buttons (`.btn-action`):** Compact, readable buttons combining a 14px vector icon with a concise text label, subtle hover highlights, and explicit disabled styling for inactive states.
- **Logical Dividers (`.bar-divider`):** Use vertical hairline dividers to group related commands (e.g., Workspace actions vs. Editing tools vs. Process triggers).
- **Contextual Session Status:** The right side of the sub-toolbar is reserved for active session/document details (e.g., active workspace name, file status, idle/busy pill), keeping the top header pristine.

### 3. Maintain the "Insanely Simple" Principle
- Avoid visual noise, redundant badges, or complex nested menus in the primary chrome.
- Preserve contrast fidelity across light and dark themes (minimum 4.5:1 for body/muted text, 3:1 for frames and UI indicators).

## How to adopt it

1. `@import` this folder's `tokens.css` as the **first statement** of the app's
   stylesheet — a CSS `@import` after any rule is discarded silently.
2. Point the app's existing local names at `--cl-*` ones in its own `:root`. Do not
   find-and-replace the uses; aliasing leaves the rest of the stylesheet untouched and
   makes the revert the same ten lines.
3. Convert whatever hex literals remain, once the aliases are proven.

For a Vite app the import is build-time only: the tokens are inlined and the mark is
emitted into the bundle, so the shipped artefact contains no reference to this folder and
stays offline-capable. `npm run dev` needs `server.fs.allow` to include `brand/`, because
the path leaves the Vite root.

## Theme Specification & Dark Block

**Dark Theme Support.** `tokens.css` provides the dark theme block under explicit selectors
(`:root[data-theme="dark"]`, `body[data-theme="dark"]`, `.dark`), opted into by applications
such as `Crazy<ApplicationName>`. In accordance with design system rules, it is never applied
implicitly under `prefers-color-scheme` to prevent silently repainting light-only applications.

The dark block overrides **every** colour token and both shadows. Type, radius and spacing
are theme-invariant and are deliberately not repeated. Three things in it are not a simple
darkening, and each is a trap worth knowing before editing:

- **The accent flips its ink.** Dark lifts the accent to emerald `#10b981` so it reads on a
  near-black ground, which means the ink *on* the accent goes dark (`#022c22`). The light
  block's `#ffffff` gives 2.54:1 there — under the 3:1 floor for any text at all.
  `android.html`'s Material scheme already pairs this way (`--m3-primary` `#87d5a3` with
  `--m3-on-primary` `#00391d`); the CSS layer now matches it.
- **The accent ramp mirrors rather than repeats.** Hover lifts to `#34d399` and press sinks
  to `#0ea371`, around the lifted base, so one ink clears 4.5:1 on all three states.
- **The frame green lifts to `#16a34a`.** `#0e6b3f` sits at 2.91:1 on the dark ground, and
  in dark the frame *is* the boundary: `--cl-chrome` and `--cl-surface` are both near-black
  and cannot separate by tone. For the same reason `--cl-chrome-border` is `#16a34a` in the
  **light** block too — the bar it frames is dark in both themes.

**Elevation.** `--cl-shadow-subtle` and `--cl-shadow-elevated` are restated in dark. Black
at 5% over `#0b0f19` is not a faint shadow, it is no shadow at all.

**Scrim.** `--cl-scrim` / `--cl-scrim-strong` are the modal backdrop. Dialogs are in this
layer's scope and the backdrop is the one token an app cannot guess, because the value that
dims a white page washes out a near-black one.

**Status.** Four families: info, success, warning, danger. Success is emerald, one step off
the brand's forest green, so a success callout cannot be misread as a branded surface.
Warning is amber, which the accent cannot stand in for at all.

## What is deliberately missing

**The faces.** `tokens.css` names Inter and JetBrains Mono with a platform fallback, but
does not deliver them: the showcases pull them from Google Fonts, which the products
forbid at runtime. An app that bundles `@fontsource/inter` gets the real thing; that is a
dependency decision each app makes for itself.

**A vector lockup.** `logoandname` exists only as raster, in a light and a dark variant.
Anything that needs the wordmark at an arbitrary size needs the mark plus real type, not
an upscale.

**Component CSS.** This folder ships tokens and marks, not classes. `index.html`'s Live
Tokens section styles its own demo, and those `.tk-*` rules are illustration — an app
writes its own components against the `--cl-*` values.
