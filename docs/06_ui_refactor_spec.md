# SkillPulse AI — Spec: UI Refactor (Jobs, Match, Market, Admin)

**Status:** Draft — ready to implement
**Owner:** —
**Related:** `AGENTS.md`, `.agents/rules/frontend-design.md` (governing design rules — this refactor exists to make the product actually comply with them), code-review findings on `frontend/style.css`/`frontend/admin.css`, the Data & Interface Review artifact (Jobs/Match/Market mockups)

---

## 1. Problem

The current frontend (`frontend/index.html`, `admin.html`, `script.js`, `admin.js`, `style.css`, `admin.css`) already has a design-rules document — `AGENTS.md` — that explicitly bans glassmorphism, oversized radii, and generic SaaS patterns. The implementation doesn't follow its own rules:

| File:line | Violation | Rule broken |
|---|---|---|
| `frontend/style.css:106` | `backdrop-filter: blur(12px)` | AGENTS.md §1 "No `backdrop-filter: blur()`, frosted glass effects" |
| `frontend/admin.css:72` | `.auth-overlay { backdrop-filter: blur(8px) }` | same |
| `frontend/style.css:48`, `admin.css:42` | `--radius-lg: 10px` | AGENTS.md §3 "Border Radius: Restrained to 4px–8px maximum" |
| `frontend/style.css:27`, `admin.css:23` | `--accent: #2563EB` | Tailwind's default `blue-600` — the single most common "safe SaaS accent" in existence, used unmodified |
| both stylesheets | `Plus Jakarta Sans` + `JetBrains Mono` | not wrong, but generic-safe geometric-sans-plus-mono is the default every AI code generator reaches for; nothing about the pairing is specific to a labor-market data product |
| `frontend/script.js` (Match view) | score bars are `topScore × {0.50, 0.20, 0.30}` — a fixed, cosmetic split, not the real per-candidate numbers the API returns | separate correctness bug (tracked in the earlier code review), but it's also a visual-honesty problem: a chart showing fabricated proportions *is* a generic-AI-dashboard tell |

None of this is catastrophic on its own. Together it reads as a competent default Tailwind-adjacent theme rather than a product someone designed on purpose — which is the opposite of what `AGENTS.md` asks for.

## 2. Goals

1. Bring the implementation into actual compliance with `AGENTS.md` / `.agents/rules/frontend-design.md` — treat those as the acceptance bar, not aspirational copy.
2. Replace the generic token set (blue-600 accent, 10px radius, Plus Jakarta Sans) with a considered one, specific to this product.
3. Ship the three redesigned surfaces already speced conceptually in the Data & Interface Review artifact: **Jobs** (grouped by region, coverage stated honestly), **Match** (real score breakdown), **Market** (region-segmented skill bars, data-completeness footer).
4. Do this without introducing a new framework, build step, or component library — stay in vanilla HTML/CSS/JS, matching the existing stack (`README.md`'s stated stack: "Modern Vanilla JS/HTML5/CSS3, 0 heavy frameworks").
5. Apply the same pass to `admin.html`/`admin.js`/`admin.css` — it's the same product's operator surface, not a separate visual identity.

## 3. Non-goals

- The API routing fix (`docs/05_api_routing_fix_spec.md`) — do that first or in parallel; this spec assumes real data is flowing.
- Backend/extraction changes.
- A full component framework migration.

---

## 4. Anti-AI-generated checklist (apply to every screen touched)

Lift straight from `AGENTS.md` §1, made concrete for this specific pass:

- [ ] No pill badge anywhere ("✨ Powered by AI", "🚀 Now live") — the current hero doesn't have one; keep it that way when touching the hero.
- [ ] No decorative gradient meshes, no purple/blue/cyan blends behind text or cards.
- [ ] Remove `backdrop-filter: blur()` at `style.css:106` and `admin.css:72` — replace the auth overlay and the modal backdrop with a flat scrim (`rgba(15,23,42,.5)`, no blur) or a solid surface panel.
- [ ] Cap every radius at 8px. Retire `--radius-lg: 10px` → `8px`, and audit every `var(--radius-lg)` usage to confirm 8px still reads correctly at that size (buttons, drawer corners, stat tiles).
- [ ] No card-inside-a-card. The Jobs list redesign (§5.1) replaces bordered `.job-card` divs with divider rows — apply the same test to Market's stat tiles and Match's result panel: if removing the box doesn't hurt legibility, remove it.
- [ ] No 3×2 icon-in-a-circle feature grid anywhere (none currently exist — don't introduce one on "How it works").
- [ ] No fake data. Every mockup and every empty/loading state in this refactor uses real rows pulled from `jobs.db` (see §5 for actual examples) — never "John Doe" / "Acme Corp" / "Lorem ipsum".
- [ ] No marketing-voice copy ("Unlock the power of your career", "Seamlessly explore opportunities"). Labels say what the control does; copy states what the data shows.

---

## 5. Design changes

### 5.1 Design tokens (`frontend/style.css` `:root`, mirrored in `admin.css`)

Replace the generic set with one considered for this subject — a labor-market data tool, engineering audience, cross-border dataset. Pick **one** of the two directions below (both satisfy the AGENTS.md constraints; pick by taste, not by default):

**Option A — "signal" (cooler, data-forward)**
```css
--accent: #0E7C86;        /* deep teal — reads as "signal", not generic SaaS indigo */
--accent-hover: #0A5F67;
--accent-subtle: #E3F1F1;
--warn: #B45309;          /* amber — reserved for data-quality/coverage callouts, not the accent */
--danger: #B91C1C;
--good: #15803D;
```

**Option B — "ledger" (warmer, editorial)**
```css
--accent: #A6521C;        /* burnt sienna — distinct from every default blue/indigo/violet */
--accent-hover: #834015;
--accent-subtle: #F6ECE3;
--warn: #7A6A16;
--danger: #B33A3A;
--good: #2F6B4F;
```

Either way: **one** accent, used sparingly (primary buttons, active nav state, link color, the one emphasized bar/segment in a chart) — not repeated across every badge and icon. Semantic colors (warn/danger/good) stay visually distinct from the accent so a status chip is never confused with a call to action.

Typography — replace `Plus Jakarta Sans` + `JetBrains Mono` with a pairing that isn't every other generator's default. Two options, both real upgrades over the current pair and both already vetted as non-cliché:

- `IBM Plex Sans` (headings/body, weight does the hierarchy work) + `IBM Plex Mono` (data, tags, code) — technical/engineering character, used in the Data & Interface Review artifact already.
- `Source Serif 4` (headings only, at page-title size — 24–28px per AGENTS.md's own type scale) + `IBM Plex Sans` (body/UI) + `IBM Plex Mono` (data) — a serif display face adds a point of view without touching UI-density areas (tables, forms) where a serif would hurt legibility.

Radius scale: `--radius-sm: 4px; --radius-md: 6px; --radius-lg: 8px;` (was `6/8/10`).

### 5.2 Jobs — group by region, state coverage honestly

Current: a flat list of bordered `.job-card` divs, no indication that the dataset is 88% one country.

Change to: section-per-region (mirrors the Ashby/Linear job-board pattern of grouping under a plain heading, divider rows instead of cards — see the reference notes in the Data & Interface Review artifact), region header shows its real share, e.g.:

```
Latin America                              1,305 roles · 88% of dataset
──────────────────────────────────────────────────────────
Senior Data Science | Python & MLOps
Dasa Tecnologia · São Paulo, Brasil · Hybrid          [Python] [MLOps] [Airflow]

Europe                                        76 roles · 5% of dataset
──────────────────────────────────────────────────────────
Senior Data Scientist / ML Engineer — Financial Crime
SumUp · Berlin, Germany · On-site                     [Python] [ML] [SQL]
```

Each row also carries a small tier indicator (`regex-extracted` vs `LLM-verified`, once `docs/05`'s pipeline exposes it) so the skill tags don't read as more authoritative than they are.

### 5.3 Match — render the real breakdown

Replace the `topScore * {0.5, 0.2, 0.3}` computation with the API's actual `hard_points` / `soft_points` / `vector_points` (already present in the `/api/v1/match` response, `schemas/matcher.py`). Each bar gets its own fill %, not a fixed proportion of the total — see the mockup in the Data & Interface Review artifact for the target layout (dial + three independent bars, weakest component visibly called out, not hidden).

### 5.4 Market — segment by region, disclose completeness

Each skill-demand bar becomes a stacked segment (Latin America / Europe / North America / Global, using the `--accent` for the dominant segment and neutral tints for the rest — not four saturated colors competing for attention). Footer line states embedding/extraction coverage plainly: *"based on 1,095 of 1,490 jobs with a computed embedding (73.5%) · 0% of extractions used the LLM tier."* This is copy pulled directly from real query results, not rounded up or softened.

### 5.5 Admin console

Same token set, same radius cap, same "remove blur" rule. No separate visual identity from the public site — currently `admin.css` duplicates `style.css`'s entire `:root` block independently (flagged in code review as a maintenance risk); while touching this, extract the shared tokens into one file both stylesheets `@import` or link, so a future accent/radius change can't drift between the two again.

---

## 6. Acceptance criteria

- [ ] `grep -rn "backdrop-filter" frontend/*.css` returns nothing.
- [ ] `grep -rn "radius-lg" frontend/*.css` resolves to `8px`, and every element using it still looks correct at that radius.
- [ ] `--accent` is no longer `#2563EB` in either stylesheet.
- [ ] Jobs page groups results by region with real, live percentages (once `docs/05` is done) instead of a flat list.
- [ ] Match result view's three score bars sum to a total that matches the displayed fit score *and* are visibly non-uniform across different candidates (proof the fixed-ratio bug is gone — check two different sample profiles and confirm the proportions differ).
- [ ] Market page shows region-segmented bars and the literal coverage-percentage footer line.
- [ ] `frontend/style.css` and `frontend/admin.css` no longer duplicate the full token block — one shared source.
- [ ] A colleague unfamiliar with the anti-AI checklist, shown the before/after side by side, identifies the after as "designed for this specifically" rather than "a nice default template" — this is a subjective bar, but it's the actual bar; if the honest answer is "still looks templated," the token/type choices in §5.1 haven't been applied with enough conviction.
