---
name: Aprova
description: Design system for Aprova, positioned as a modern, systematic tech product rather than a traditional preparatory course.
colors:
  brand-primary: "#5FC48C"        # Mint/Emerald green for main actions and highlights
  bg-dark-base: "#141F20"         # Deep teal/slate for dark sections
  bg-dark-elevated: "#1D2D2E"     # Slightly lighter for inner dark cards
  bg-light-base: "#FFFFFF"        # Pure white for content sections
  bg-light-alt: "#F8F9FA"         # Subtle off-white for contrast areas
  text-on-dark-primary: "#FFFFFF"
  text-on-dark-muted: "#8FA7A3"   # Soft teal-grey for subtitles
  text-on-light-primary: "#1A2522"
  text-on-light-muted: "#6B7A77"
  border-dark: "rgba(255, 255, 255, 0.15)"
  border-light: "rgba(0, 0, 0, 0.05)"
typography:
  display-hero:
    fontFamily: Plus Jakarta Sans, sans-serif
    fontSize: 4rem
    fontWeight: "700"
    lineHeight: 1.05
    letterSpacing: "-0.03em"
  heading-section:
    fontFamily: Plus Jakarta Sans, sans-serif
    fontSize: 2.5rem
    fontWeight: "700"
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  body-large:
    fontFamily: Inter, sans-serif
    fontSize: 1.25rem
    fontWeight: "400"
    lineHeight: 1.5
  body-base:
    fontFamily: Inter, sans-serif
    fontSize: 1rem
    fontWeight: "400"
    lineHeight: 1.6
  label-caps:
    fontFamily: Inter, sans-serif
    fontSize: 0.875rem
    fontWeight: "600"
    letterSpacing: 0.1em
    textTransform: uppercase
rounded:
  sm: 8px
  md: 16px
  lg: 24px
  xl: 40px          # Used for large section containers
  full: 9999px      # Used for buttons and pills
spacing:
  sm: 16px
  md: 24px
  lg: 40px
  xl: 80px
  section-padding: 120px
components:
  button-primary-glow:
    backgroundColor: "{colors.brand-primary}"
    textColor: "{colors.bg-light-base}"
    rounded: "{rounded.full}"
    padding: "16px 32px"
    shadow: "0 0 32px rgba(95, 196, 140, 0.3)"
  button-outline-dark:
    backgroundColor: transparent
    textColor: "{colors.text-on-dark-primary}"
    border: "1px solid {colors.border-dark}"
    rounded: "{rounded.full}"
    padding: "16px 32px"
  pill-badge:
    backgroundColor: transparent
    textColor: "{colors.text-on-dark-primary}"
    border: "1px solid {colors.border-dark}"
    rounded: "{rounded.full}"
    padding: "8px 16px"
  large-section-dark:
    backgroundColor: "{colors.bg-dark-base}"
    rounded: "{rounded.xl}"
    padding: "{spacing.xl}"
---

## Overview

The Aprova design system is built to communicate "System" and "Execution" over "Study Materials". It uses a highly modern, SaaS-like aesthetic. The interface is divided into starkly contrasting blocks: pure white spaces for functional steps and deep, sophisticated teal/dark spaces for emotional, high-value value propositions. 

## Colors & Lighting

- **The Dark Theme:** The core brand identity relies heavily on `bg-dark-base` (#141F20). This is not pure black; it has a rich teal undertone that pairs perfectly with the green accents.
- **The Glow Effect:** The primary call-to-action buttons (`button-primary-glow`) on dark backgrounds must have a soft, diffuse box-shadow using the primary green color. This creates a "neon glow" effect that draws the eye immediately.
- **Text:** Headings often mix white text with the primary green (`brand-primary`) to highlight specific keywords (e.g., "Menos cursinho. Mais **sistema de aprovação**.").

## Typography

- **Headings:** Bold, highly geometric, and tightly spaced. Headlines should feel punchy and confident. Use negative letter-spacing (`-0.03em`) on large displays to make them feel cohesive as a single visual block.
- **Body Text:** Extremely clean and readable. Muted colors (`text-on-dark-muted` or `text-on-light-muted`) are used extensively for paragraphs to ensure the headings and green accents remain the focal points.

## Layout & Components

- **Rounded Corners:** The UI is incredibly soft. Buttons, badges, and input fields are exclusively pill-shaped (`rounded-full`). Large content blocks and image wrappers use very generous rounding (`rounded-xl` or 40px). Sharp corners are strictly avoided.
- **Step-by-Step UI:** Process explanations use vertical or horizontal thin, subtle lines connecting circular badges to visually reinforce the idea of a "systematic journey".
- **Wireframe Elements:** Subtle background grids (light dots or thin lines) can be used on white backgrounds to reinforce the "tech/engineering" feel of the platform.

## Do's and Don'ts

- **DO** use a soft green glow on the main CTA when it sits on a dark background.
- **DO** highlight one or two key words in a headline using the primary green color.
- **DO** use pill-shaped (`9999px`) buttons and badges everywhere.
- **DO NOT** use sharp, 0px corners on any cards or buttons.
- **DO NOT** clutter the interface; use massive amounts of padding (`section-padding`) between structural blocks.
