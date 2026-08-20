---
description: Rules for frontend UI design, enforcing product-first, utilitarian patterns and eliminating generic AI UI tropes.
alwaysApply: true
---

# Frontend Design & Product UI Directives

Always enforce these frontend UI rules:

## 1. Anti-AI Patterns (Strictly Prohibited)
- **No generic SaaS hero sections**: No pill badges ("✨ AI Powered"), giant marketing headlines, dual generic CTAs, or floating card mockups.
- **No decorative gradients**: No purple/blue/cyan gradient backgrounds or text meshes.
- **No card nesting abuse**: Never nest cards inside cards. If removing a container box does not harm comprehension, remove the box.
- **No excessive border-radius**: Cap radii at 4px–8px. Never use uniform 16px radius across all elements.
- **No 3x2 generic icon grids**: Do not place repetitive circle icons + title + 2-line descriptions in grid cards.
- **No glassmorphism or heavy shadows**: Avoid `backdrop-filter: blur()` and diffuse multi-layer drop shadows.
- **No excessive centering**: Left-align content by default; right-align numbers/dates.
- **No generic marketing copy**: Avoid clichés ("Unlock the power of...", "Seamlessly manage...", "Elevate your workflow...").
- **No fake dummy data**: Always use domain-specific, realistic data (real job titles, timestamps, matching scores, tech stacks).

## 2. Design Principles
- **Utilitarian & Product-First**: Design like mature tools (Linear, GitHub, Stripe, Raycast, Vercel). Focus on data density, keyboard flow, and direct manipulation.
- **Typography > Decoration**: Establish visual hierarchy using a structured type scale (Page title: 24-28px semibold, Section: 14-16px semibold, Body: 13-14px regular, Metadata: 11-12px muted).
- **Spacing Scale**: Strict 4/8-point spacing (`4px`, `8px`, `12px`, `16px`, `24px`, `32px`, `48px`).
- **Asymmetry & Editorial Restraint**: Deliberately size panels (e.g., 680px main / 280px sidebar), mute secondary info, and use subtle 1px dividers rather than boxes.
- **Single Accent Color**: Neutral monochrome base with a single accent color for primary actions.

## 3. Workflow & Visual Lint
When writing or refactoring UI:
1. Determine information hierarchy and data states first.
2. Build semantic structure and viewport regions (nav, main, sidebar).
3. Implement core interaction flow and keyboard accessibility.
4. Apply restrained visual tokens and typography.
5. Run a visual lint pass: remove unnecessary cards, strip decorative gradients/shadows, and verify data authenticity.
