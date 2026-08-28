# SkillPulse — Accessibility and Release QA Specification

**Status:** Implemented locally; production verification pending

**Date:** 2026-08-22

**Priority:** Medium, required before production-ready status

**Depends on:** `docs/07_release_recovery_spec.md`

**Related:** `docs/06_ui_refactor_spec.md`, `docs/08_admin_security_spec.md`

## 1. Purpose

Correct the accessibility defects found during deployed-site testing and define a repeatable release QA matrix for public navigation, responsive layouts, keyboard operation, and truthful live-data states.

This specification does not introduce a frontend framework or redesign the product. It preserves the existing vanilla HTML, CSS, and JavaScript architecture and the product-first visual directives in `AGENTS.md`.

## 2. Evidence and current defects

Production QA on 2026-08-21 found:

- the default `Software Engineer` job drawer was present in the accessibility tree before a job was selected;
- the drawer used `display: flex`, had no initial `aria-hidden`, and was positioned offscreen rather than semantically hidden;
- its default `View Job Posting` link used `href="#"`;
- clickable sample-profile cards were plain `div` elements without button semantics or keyboard focus;
- the deployed live-data failures produced convincing synthetic output, which is also an accessibility problem because status announcements described it as market analysis;
- mobile viewport emulation in the in-app browser was inconclusive, so no mobile pass was established.

The current source has partial modal behavior but does not yet provide initial hiding, focus management, a focus return path, or a keyboard-accessible sample selector.

### 2.1 Code audit findings (2026-08-22)

Reviewing `frontend/script.js` and `frontend/index.html` against this specification found the sample-profile buttons, top-level navigation, job drawer (initial `hidden`/`aria-hidden` state, focus moved to the close button on open, Tab/Shift+Tab trap, `inert` background, focus returned to the opener on close), and Market tabs (full WAI-ARIA tablist pattern with roving `tabindex` and Left/Right arrow-key navigation) implemented as specified. Two remaining gaps were confirmed and fixed:

- Unavailable states now use `role="alert"` consistently for Match, Jobs, and Market.
- Empty Match submission now renders a dedicated field error, connects it to the profile textarea with `aria-describedby`, sets `aria-invalid`, and clears the error when input resumes.

Both corrections are covered by `tests/spec09_accessibility_and_release_qa.test.js` and `tests/browser_release_acceptance.test.js`, including job-drawer content cleanup after Escape.

## 3. Accessibility target

Target WCAG 2.2 AA for the tested public flows. Automated checks are necessary but not sufficient; keyboard and screen-reader-oriented DOM inspection are required.

The required flows are:

- switch between Match, Jobs, Market, and How it works;
- populate and clear a profile;
- invoke a live match and understand success, empty, loading, and unavailable states;
- search and filter jobs;
- open, read, follow, and close job details;
- switch Market tabs;
- expand and collapse the architecture disclosure.

## 4. Semantic control requirements

### 4.1 Sample profiles

Each sample profile is a native `<button type="button">`, not a clickable `div`.

It must expose:

- a concise accessible name containing the role and experience level;
- visible focus styling;
- selected state through `aria-pressed` when applicable;
- activation by Enter, Space, pointer, and touch without separate custom key handlers;
- no automatic live-result claim unless a valid API response is received.

### 4.2 Navigation and brand

Top-level view controls remain native buttons or links. The logo/brand is a link to `/match`, not a click-only `div`. The active view uses `aria-current="page"` in addition to visual styling.

Browser history and the displayed view must remain synchronized when navigating with Back and Forward.

### 4.3 Market tabs

Market Technologies, Seniority, and Locations use the complete WAI-ARIA tabs pattern: `role="tablist"`, `role="tab"`, `role="tabpanel"`, `aria-selected`, `aria-controls`, roving `tabindex`, and Left/Right arrow-key navigation.

## 5. Job drawer requirements

Before a job is selected:

- the drawer and backdrop use the `hidden` attribute;
- the drawer has `aria-hidden="true"`;
- no placeholder heading, company, location, description, score, or link is exposed to assistive technology;
- the external job link has no navigable placeholder destination.

When opened:

- populate all content before revealing the drawer;
- remove `hidden` and `aria-hidden`;
- set `role="dialog"`, `aria-modal="true"`, and a valid accessible title;
- store the element that opened it;
- move focus to the close button;
- keep Tab and Shift+Tab inside the dialog;
- set `inert` on the page header and main content so background content cannot receive pointer or keyboard focus;
- provide only real API fields, using explicit `Not provided` text when a nonessential field is absent;
- render the external link only when the API provides a valid `https:` job URL.

When closed by the close button, backdrop, or Escape:

- hide it semantically and visually;
- remove modal state;
- restore page scrolling;
- return focus to the element that opened it;
- clear job-specific content and link destination.

Escape must not change page state when the drawer is already closed.

## 6. Loading, empty, success, and error announcements

Every asynchronous public flow has one dedicated status region:

- loading uses `role="status"` with `aria-live="polite"`;
- unavailable and validation errors use `role="alert"`;
- successful result counts are announced once;
- status content is not duplicated by toast and inline regions;
- focus is not moved automatically on routine loading completion unless the user invoked a navigation-like action.

Unavailable copy follows `docs/07_release_recovery_spec.md` and never describes generated output as live analysis.

## 7. Forms and data presentation

- Every input and select has a persistent programmatic label.
- Validation errors identify the field and are connected with `aria-describedby`.
- Color is not the sole indicator of fit tier, availability, workplace type, or verification state.
- Percent bars expose their label, current value, minimum, and maximum to assistive technology.
- Numerical tables and lists preserve a logical reading order at narrow widths.
- External links disclose that they open a new tab in visible or accessible text.

## 8. Responsive requirements

Test these CSS viewport sizes at 100% zoom:

- 390 × 844;
- 768 × 1024;
- 1280 × 800;
- 1440 × 900.

At each size:

- no page-level horizontal scrolling occurs;
- the top navigation remains operable without clipping controls;
- touch targets are at least 24 × 24 CSS pixels, with 44 × 44 preferred for primary touch controls;
- text remains readable without overlapping or truncating essential meaning;
- forms stack in a logical order;
- the drawer fits the viewport, has an independently scrollable body, and keeps its close control visible;
- job rows and metric distributions preserve labels and values;
- no content relies on hover to expose the only available action.

Also test 200% browser zoom at 1280 × 800. The layout must reflow without loss of content or functionality.

## 9. Visual and interaction constraints

All corrections must retain the repository's product UI rules:

- no gradients, glassmorphism, excessive card nesting, or heavy shadows;
- one restrained accent color;
- 4/8-point spacing and 4–8px radii;
- typography and dividers carry hierarchy;
- realistic data only;
- status styling uses semantic color sparingly and always includes text or icon meaning.

Accessibility fixes must not introduce a generic marketing layout or reduce the information density of Jobs and Market.

## 10. Automated testing requirements

Add static and behavior tests for:

- sample profiles are buttons with usable names;
- active navigation exposes programmatic state;
- the drawer is hidden and non-navigable on initial load;
- opening the drawer sets modal state and focuses inside it;
- Tab wraps within the open drawer;
- Escape closes it and returns focus;
- a missing or invalid job URL renders no apply link;
- closing clears content and destination;
- status regions announce loading, unavailable, empty, and result-count states;
- the unavailable/error status component uses `role="alert"`, not `role="status"`, for Match, Jobs, and Market failures alike;
- empty or invalid Match submission renders a field-connected error via `aria-describedby` on the profile textarea, not only a global toast;
- no duplicate IDs, unlabeled form controls, unnamed buttons, or visible images without `alt` remain;
- viewport-specific layout assertions detect page-level overflow.

If an accessibility scanner is added, pin its version and run it against rendered Match, Jobs, Market, How it works, and the open drawer. Scanner output does not replace manual keyboard acceptance.

## 11. Manual release QA matrix

Run the following against a local production-like build and, after deployment approval, against production:

| Area | Scenario | Expected result |
|---|---|---|
| Navigation | Mouse, keyboard, Back/Forward | One active view; URL and content agree |
| Match | Empty submit | Labeled validation; focus returns to profile field |
| Match | API unavailable | No score or jobs; unavailable state announced |
| Match | Valid API response | Only server values render; result count announced |
| Jobs | Empty dataset | Zero-result state, not unavailable state |
| Jobs | API unavailable | No fixture vacancies; unavailable state announced |
| Jobs | Filters | Request and rendered results reflect each filter |
| Drawer | Open/Tab/Escape | Focus trapped, close works, trigger regains focus |
| Market | Tabs and API failure | Controls work; no stale metrics remain |
| Architecture | Disclosure | Summary toggles with keyboard and exposes state |
| Responsive | Four required sizes and 200% zoom | No essential clipping or horizontal page scroll |
| Console | All core flows | No uncaught errors or unexpected warnings |

## 12. Production evidence package

For each approved production release, retain:

- tested deployment URL and timestamp;
- deployed asset hashes from `docs/07_release_recovery_spec.md`;
- browser and OS used;
- viewport matrix results;
- console error/warning export;
- DOM accessibility snapshot for initial Match, unavailable Jobs, unavailable Market, and the open drawer;
- screenshots only where they demonstrate layout or focus-state evidence;
- a severity-ranked defect list with reproduction steps.

Do not include profile text, credentials, cookies, or sensitive raw data in evidence.

## 13. Cost and safety guardrails

- Use local contract fixtures for success-state testing.
- Do not call paid AI or embedding services.
- Do not run scraping, ingestion, extraction, digest, or database maintenance.
- Do not invoke admin mutations during public QA.
- Do not deploy without explicit user approval.
- Responsive and accessibility testing is read-only against production.

## 14. Acceptance checklist

- [x] All sample profile controls are keyboard-accessible native buttons.
- [x] Initial job drawer is absent from the accessibility tree and tab order.
- [x] Open drawer has correct modal state, focus trap, Escape handling, and focus return.
- [x] Placeholder `href="#"` is removed.
- [x] Navigation and Market controls expose programmatic active state.
- [x] Async loading, empty, success, and unavailable states are announced accurately.
- [x] Automated accessibility checks pass for all public views.
- [ ] Manual keyboard checks pass.
- [x] Four viewport sizes and 200% zoom pass without essential clipping or horizontal page scroll.
- [ ] Production evidence package is complete after an approved deployment.
- [x] Unavailable and validation error states use `role="alert"`, verified by an automated test, not `role="status"`.
- [x] Empty-profile submission shows a field-connected validation message via `aria-describedby`, not only a toast.

## 15. Out of scope

- a visual redesign beyond accessibility-required adjustments;
- admin authentication and authorization, governed by `docs/08_admin_security_spec.md`;
- API hosting, D1 migration, or vector search;
- native mobile applications;
- localization beyond preserving correct language and seniority labels already returned by the API.
