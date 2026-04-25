# Shunfa Soft Luxury UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the WeChat mini-program UI into a Soft Luxury Productivity visual system with higher perceived quality, stronger consistency, and unchanged core writing flow.

**Architecture:** Keep existing page data flow and component boundaries, but replace the current editorial-paper visual language with a calmer luxury-product system driven by shared tokens in `app.wxss`. Refactor page layouts and shared components incrementally so the same token set governs spacing, card tiers, typography, buttons, and states across the main user journey.

**Tech Stack:** WeChat Mini Program (`wxml`, `wxss`, `js`), existing local component system, FastAPI backend unchanged for this task

---

### Task 1: Freeze the global design tokens

**Files:**
- Modify: `miniprogram/app.wxss`

**Step 1: Write the failing visual checklist**

Document the expected token changes directly in the implementation notes:

- Background moves from paper/newsletter to warm neutral luxury palette
- Primary accent becomes low-saturation sage
- Shared card/button styles support 3 card tiers and 3 action levels
- Existing editorial chips and highlight-yellow bias are no longer primary branding

**Step 2: Inspect current token usage**

Run: `rg --line-number "color-|radius|shadow|editorial-chip|note-card|paper-card" miniprogram`
Expected: shared tokens and repeated visual language appear across app and page styles

**Step 3: Write minimal token refactor**

Modify `miniprogram/app.wxss` to:

- replace paper/editorial palette with soft luxury palette
- define reusable surface, outline, muted text, accent, and danger tokens
- define shared classes for primary/secondary/text buttons
- define shared classes for surface tiers and subtle motion

**Step 4: Verify token coverage**

Run: `sed -n '1,240p' miniprogram/app.wxss`
Expected: no dominant editorial-yellow system remains; new neutral/sage system is visible

**Step 5: Commit**

```bash
git add miniprogram/app.wxss
git commit -m "feat: add soft luxury design tokens"
```

### Task 2: Refactor the home page into a luxury entry screen

**Files:**
- Modify: `miniprogram/pages/index/index.wxml`
- Modify: `miniprogram/pages/index/index.wxss`

**Step 1: Write the failing visual checklist**

The page currently fails if:

- it still uses newsroom/editorial branding
- it presents too many equal-weight panels at once
- the main CTA does not clearly dominate the page

**Step 2: Inspect the current page structure**

Run: `sed -n '1,240p' miniprogram/pages/index/index.wxml`
Expected: hero, stats, level card, action card, and reminder-style blocks are visible

**Step 3: Rewrite the layout**

Update `index.wxml` to:

- remove editorial terminology
- make the hero a calmer welcome/status area
- make the primary writing CTA the central visual action
- compress growth/status information into calmer summary modules

Update `index.wxss` to:

- use new token system
- reduce visual noise
- tighten hierarchy around a single main action

**Step 4: Verify visually via source inspection**

Run: `sed -n '1,260p' miniprogram/pages/index/index.wxml`
Expected: page copy and structure reflect a luxury-product tone, with one clear primary CTA

**Step 5: Commit**

```bash
git add miniprogram/pages/index/index.wxml miniprogram/pages/index/index.wxss
git commit -m "feat: redesign mini program home page"
```

### Task 3: Refactor the topics page into premium selection cards

**Files:**
- Modify: `miniprogram/pages/topics/topics.wxml`
- Modify: `miniprogram/pages/topics/topics.wxss`
- Modify: `miniprogram/components/topic-card/index.wxml`
- Modify: `miniprogram/components/topic-card/index.wxss`

**Step 1: Write the failing visual checklist**

The page currently fails if:

- topic cards still feel like newsroom items instead of premium selection cards
- selected state depends on strong blocks/colors rather than subtle hierarchy
- informational copy is louder than the actual topic content

**Step 2: Inspect current topic surfaces**

Run: `sed -n '1,260p' miniprogram/components/topic-card/index.wxml`
Expected: source, summary, and selection affordance are visible in the component

**Step 3: Refactor page and card styles**

Update the page and component to:

- remove editorial framing
- shorten and calm secondary labels
- make the topic title the focus
- move source/link/summary into secondary surfaces
- unify selected state with subtle outline, tone, and action emphasis

**Step 4: Verify selected-state semantics**

Run: `rg --line-number "selected|source|summary|url" miniprogram/components/topic-card miniprogram/pages/topics`
Expected: selected state and fact fields remain fully supported

**Step 5: Commit**

```bash
git add miniprogram/pages/topics/topics.wxml miniprogram/pages/topics/topics.wxss miniprogram/components/topic-card/index.wxml miniprogram/components/topic-card/index.wxss
git commit -m "feat: redesign topic selection surfaces"
```

### Task 4: Refactor the preview page into a private draft sheet

**Files:**
- Modify: `miniprogram/pages/preview/preview.wxml`
- Modify: `miniprogram/pages/preview/preview.wxss`

**Step 1: Write the failing visual checklist**

The page currently fails if:

- the reading surface does not dominate
- fact/reference info competes with the main draft
- quality feedback looks like an alert instead of editorial guidance

**Step 2: Inspect current preview structure**

Run: `sed -n '1,300p' miniprogram/pages/preview/preview.wxml`
Expected: topic, facts, content, quality result, and actions are all on the page

**Step 3: Rewrite visual hierarchy**

Update the page to:

- make the draft reading area dominant
- move fact metadata into a calmer secondary reference area
- soften quality feedback visuals
- unify button hierarchy with the new design system

**Step 4: Verify that interaction states remain intact**

Run: `rg --line-number "quality_|step ===|onCopySourceLink|onPublish|onCheckQuality" miniprogram/pages/preview`
Expected: all existing states and actions remain wired

**Step 5: Commit**

```bash
git add miniprogram/pages/preview/preview.wxml miniprogram/pages/preview/preview.wxss
git commit -m "feat: redesign draft preview experience"
```

### Task 5: Refactor profile and settings into calmer account surfaces

**Files:**
- Modify: `miniprogram/pages/profile/profile.wxml`
- Modify: `miniprogram/pages/profile/profile.wxss`
- Modify: `miniprogram/pages/settings/settings.wxml`
- Modify: `miniprogram/pages/settings/settings.wxss`

**Step 1: Write the failing visual checklist**

The pages currently fail if:

- they still look like dashboards or generic form panels
- settings controls feel visually disconnected from the rest of the product
- account/progress modules are louder than necessary

**Step 2: Inspect current page structures**

Run: `sed -n '1,260p' miniprogram/pages/profile/profile.wxml`
Expected: profile summary and progress modules are present

Run: `sed -n '1,260p' miniprogram/pages/settings/settings.wxml`
Expected: reminder toggles and time-setting surfaces are present

**Step 3: Refactor the page visuals**

Update profile and settings to:

- align with the new shared surfaces
- reduce dashboard heaviness
- present reminders and progress as calm grouped settings
- unify copy density, spacing, and button semantics

**Step 4: Verify structural integrity**

Run: `rg --line-number "switch|picker|reminder|level|diamond|streak" miniprogram/pages/profile miniprogram/pages/settings`
Expected: controls and account data bindings remain intact

**Step 5: Commit**

```bash
git add miniprogram/pages/profile/profile.wxml miniprogram/pages/profile/profile.wxss miniprogram/pages/settings/settings.wxml miniprogram/pages/settings/settings.wxss
git commit -m "feat: redesign profile and settings pages"
```

### Task 6: Unify shared status/progress components

**Files:**
- Modify: `miniprogram/components/streak-badge/index.wxss`
- Modify: `miniprogram/components/diamond-display/index.wxss`
- Modify: `miniprogram/components/level-progress/index.wxss`

**Step 1: Write the failing visual checklist**

The shared components currently fail if:

- each component uses its own visual metaphor
- component density and shape language conflict with the new pages
- the components draw too much attention away from the main flow

**Step 2: Inspect current component styles**

Run: `sed -n '1,220p' miniprogram/components/streak-badge/index.wxss`
Expected: current visual styling is visible for comparison

**Step 3: Refactor shared component styling**

Update all three components to:

- inherit the same neutral/sage luxury vocabulary
- reduce novelty styling
- preserve data clarity while lowering visual noise

**Step 4: Verify consistency**

Run: `rg --line-number "background|border|shadow|color" miniprogram/components/streak-badge miniprogram/components/diamond-display miniprogram/components/level-progress`
Expected: token-based styling replaces isolated component-specific aesthetics

**Step 5: Commit**

```bash
git add miniprogram/components/streak-badge/index.wxss miniprogram/components/diamond-display/index.wxss miniprogram/components/level-progress/index.wxss
git commit -m "feat: unify shared progress components"
```

### Task 7: Validate the mini-program UI refactor

**Files:**
- Modify: `docs/plans/2026-04-11-shunfa-soft-luxury-ui.md`

**Step 1: Run source-level sanity checks**

Run: `rg --line-number "Editorial Desk|Morning Brief|Proof Sheet|编辑部|晨报" miniprogram`
Expected: no stale design-language labels remain on user-facing pages unless intentionally retained

**Step 2: Run visual smoke review in the codebase**

Run: `git diff -- miniprogram/app.wxss miniprogram/pages/index miniprogram/pages/topics miniprogram/pages/preview miniprogram/pages/profile miniprogram/pages/settings miniprogram/components/topic-card miniprogram/components/streak-badge miniprogram/components/diamond-display miniprogram/components/level-progress`
Expected: all primary UI files are covered and no unrelated logic changes appear

**Step 3: Manual QA checklist**

Verify in WeChat DevTools:

- Home page loads and primary CTA is clear
- Topics page shows 3 topics with stable selected state
- Preview page preserves edit / quality / publish states
- Profile and settings remain navigable
- No page has clipped text, collapsed buttons, or obvious spacing breaks

**Step 4: Record outcome**

Append a short validation note to this plan file describing:

- what was visually checked
- what still needs real-device validation

**Step 5: Commit**

```bash
git add docs/plans/2026-04-11-shunfa-soft-luxury-ui.md
git commit -m "docs: record soft luxury ui validation"
```
