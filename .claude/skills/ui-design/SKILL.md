---
name: ui-design
description: Guidance for distinctive, intentional visual design when building or reshaping UI. Use for any frontend work - new screens, components, or redesigns.
---

# UI/UX Design Guidance

Approach this as a design lead who gives every project a visual identity that
could not be mistaken for a generic template. Make deliberate, opinionated
choices about palette, typography, and layout specific to THIS app - a
bilingual Hebrew/Spanish vocabulary trainer for two real people, not a demo.

## Ground it in the subject

This app is about the moment of revealing a word you're learning - script,
sound, meaning. That moment (the flip/reveal) is the emotional core of the
product. Design should serve and highlight it, not bury it in generic card UI.

Two real constraints shape everything:
- Hebrew must render RTL correctly and use a font that actually supports it
  well (Noto Sans Hebrew or Heebo) - never let it fall back to a default font.
- One user cannot read Hebrew script at all. Audio and phonetic transliteration
  are not secondary features, they are load-bearing UI elements, give them
  real visual weight, not a small gray subtitle.

## Design principles

Avoid the current AI-generated-design defaults: cream background with warm
terracotta accent, near-black with one acid-green accent, or broadsheet-style
hairline-rule newspaper layouts. Pick a palette and type pairing that come
from THIS subject (language, sound, script, discovery) not from a generic
template.

Typography carries personality. The studied word is the visual focus - large,
well-typed, high contrast. Pair a display face and body face deliberately.

The reveal should be a smooth, satisfying transition, not an instant DOM swap.
Motion should serve the "aha" moment of the reveal specifically - that is the
signature interaction of this whole app, worth getting right before anything
else.

Mobile-first, always. Assume a phone in portrait is the primary device for
both users.

## Process

Before writing code: describe a compact token system (4-6 named hex colors,
2 typefaces with roles, one signature element) and check it isn't the generic
default before building. State the plan briefly, then build to it.

## Quality floor

Responsive down to mobile, visible keyboard focus, reduced-motion respected,
Hebrew RTL correct at the string level (not the whole page), real contrast
ratios for accessibility.
