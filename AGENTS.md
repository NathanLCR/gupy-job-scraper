# AGENTS.md — Frontend Design & Product UI Directives

> **Core Directive**: Eliminate generic AI tropes. Build utilitarian, product-first interfaces with high information density, intentional typography, asymmetric layout decisions, and restrained styling.

---

## 1. ANTI-AI PATTERNS (Prohibited Frontend Tropes)

Never generate or converge to these default AI patterns unless explicitly instructed:

* ❌ **Generic SaaS Hero Section**:
  * No pill badge (`"✨ Now in Beta"` / `"🚀 Powered by AI"`)
  * No oversized headline + vague subtitle + 2 side-by-side CTAs (`"Get Started"` / `"Learn More"`) + floating card mockup
* ❌ **Purple / Blue Gradients**: No decorative violet/cyan/magenta mesh or glowing gradients.
* ❌ **Nested Card Overload**: Do not wrap cards inside cards inside cards. If removing a container box does not hurt legibility, **remove the box**.
* ❌ **Homogeneous 16px Radius**: Do not put `border-radius: 16px` on every single element.
* ❌ **Repetitive 3×2 Icon Grids**: No generic feature grids with an icon in a circle, bold title, and 2-line placeholder text.
* ❌ **Glassmorphism & Heavy Shadows**: No `backdrop-filter: blur()`, frosted glass effects, or diffuse multi-layer drop shadows.
* ❌ **Excessive Centering & Padding**: Avoid centering everything with huge arbitrary whitespace.
* ❌ **Vague Marketing Copy**:
  * Never use: *"Unlock the power of..."*, *"Seamlessly manage..."*, *"Elevate your workflow..."*, *"The next-generation platform for..."*
* ❌ **Fake Dummy Data**: No `John Doe`, `john@example.com`, `$12,345`, `+24%`, or `Lorem Ipsum`. Use contextual, realistic domain data.

---

## 2. DESIGN PRINCIPLES (Product-First Philosophy)

1. **Utilitarian & Product-First**:
   * Prioritize tools, workflows, data readability, and actions over promotional splash pages.
   * Model UI behavior on mature developer and productivity tools (*Linear, GitHub, Stripe, Raycast, Vercel, Notion*).
2. **Typography > Decoration**:
   * Establish visual hierarchy via font sizes, weights, line heights, and subtle muted colors—not background boxes.
   * Standard type scale:
     * `Page Title`: `24px` – `28px` / `semibold`
     * `Section Header`: `14px` – `16px` / `semibold`
     * `Body`: `13px` – `14px` / `regular` (`line-height: 1.5`)
     * `Metadata / Captions`: `11px` – `12px` / `regular` or `medium` (muted text color)
3. **Structured Spacing Scale**:
   * Stick to a rigid 4/8-point spacing system: `4px | 8px | 12px | 16px | 24px | 32px | 48px`.
4. **Editorial Decisions & Intentional Asymmetry**:
   * Not all columns need equal widths (e.g., Main view `680px`, Sidebar `280px`, Context drawer `320px`).
   * Not all elements deserve equal visual weight. Demote secondary metadata.
   * Use dividers (`1px solid var(--border)`), subtle surface changes, or whitespace instead of heavy borders and cards.

---

## 3. PRODUCT UI RULES & DESIGN SYSTEM

* **Border Radius**: Restrained to `4px` to `8px` maximum (e.g., `4px` for inputs/badges, `6px` for buttons, `8px` for panels).
* **Color Palette**:
  * Neutral grayscale foundation (`background`, `surface`, `border`, `text-primary`, `text-muted`).
  * **One single accent color** for primary interactions and active states (e.g., brand indigo, slate, or emerald).
  * Semantic colors (success, error, warning) used sparingly for status indicators only.
* **Containers & Surfaces**:
  * Default to flat surfaces with clean borders: `1px solid var(--border)`.
  * Shadows: Minimal or none (e.g., `box-shadow: 0 1px 2px rgba(0,0,0,0.05)` for floating dropdowns/popovers only).
* **Alignment**:
  * Left-align content and form elements by default.
  * Right-align numerical values, timestamps, and currency in tables/lists.
* **Information Density**:
  * Show data in structured tables, lists with horizontal dividers, or split-pane views.
  * Reveal contextual actions on hover or keyboard shortcuts to keep default views clean.

---

## 4. FRONTEND WORKFLOW (Phased Execution)

When implementing or redesigning any UI:

1. **Information Hierarchy**: Define the data model, primary user goal, and secondary actions.
2. **Structural Layout**: Define viewport regions (header/nav, main stage, sidebars, inspector).
3. **Interaction Flow**: Implement primary action paths, keyboard interactions, filters, and states (empty, loading, error).
4. **Visual Polish**: Apply type scale, tokens, subtle borders, and alignment.
5. **Anti-AI Review / Visual Lint**:
   * [ ] Are there redundant nested cards?
   * [ ] Is there unnecessary gradient or blur decoration?
   * [ ] Is typography carrying the hierarchy without needing colored boxes?
   * [ ] Is the data realistic and aligned with the domain?
