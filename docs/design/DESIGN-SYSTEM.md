---
name: VOLC Design System
description: Design system for Volc's explosive, premium, and tech-forward presentations.
colors:
  background-dark: "#000000"
  background-light: "#F4F5F6"
  text-primary-light: "#FFFFFF"
  text-primary-dark: "#1A1C1E"
  text-muted-light: "#A0AAB2"
  text-muted-dark: "#6C7278"
  accent-neon-blue: "#00D4FF"
  accent-deep-blue: "#0D47A1"
  accent-neon-purple: "#8A2BE2"
  accent-neon-orange: "#FF3D00"
  accent-red: "#D32F2F"
  border-subtle-light: "rgba(255, 255, 255, 0.15)"
  border-subtle-dark: "rgba(0, 0, 0, 0.1)"
typography:
  display-hero:
    fontFamily: Space Grotesk, sans-serif
    fontSize: 4rem
    fontWeight: "800"
    letterSpacing: 0.05em
    textTransform: uppercase
  headline-main:
    fontFamily: Space Grotesk, sans-serif
    fontSize: 2.5rem
    fontWeight: "700"
    letterSpacing: 0.02em
    textTransform: uppercase
  headline-secondary:
    fontFamily: Inter, sans-serif
    fontSize: 1.5rem
    fontWeight: "600"
  body-base:
    fontFamily: Inter, sans-serif
    fontSize: 1rem
    fontWeight: "400"
    lineHeight: 1.6
  label-tech:
    fontFamily: Space Grotesk, sans-serif
    fontSize: 0.875rem
    fontWeight: "600"
    letterSpacing: 0.1em
    textTransform: uppercase
rounded:
  none: 0px
  sm: 4px
  md: 8px
  lg: 16px
spacing:
  sm: 16px
  md: 32px
  lg: 64px
  xl: 120px
  slide-padding: 48px
components:
  slide-container-dark:
    backgroundColor: "{colors.background-dark}"
    textColor: "{colors.text-primary-light}"
    padding: "{spacing.slide-padding}"
  slide-container-light:
    backgroundColor: "{colors.background-light}"
    textColor: "{colors.text-primary-dark}"
    padding: "{spacing.slide-padding}"
  text-outline-effect:
    textColor: transparent
  divider-tech:
    backgroundColor: "{colors.text-primary-light}"
    height: 1px
---

## Overview

The Volc visual identity is built on the concept of "Exploding Ideas". It is digital, highly energetic, yet strictly premium and minimalist. The aesthetic contrasts the vast, empty darkness of deep space (absolute black) with intensely vibrant, organic bursts of light (grainy aurora gradients). The UI should never feel cluttered; it relies on dramatic typography, negative space, and strategic pops of neon color to guide the eye.

## Colors & Textures

The core of the Volc aesthetic relies on extreme contrast and the specific treatment of colorful gradients.

- **Backgrounds:** The primary canvas is absolute black (`#000000`) for high-impact slides, or a very clean off-white (`#F4F5F6`) for dense, informational slides (like pricing or technical funnels).
- **The Volc Aurora (Crucial):** Accents are not flat colors. They are fluid, multi-stop gradients mixing `accent-neon-blue`, `accent-deep-blue`, `accent-neon-purple`, and `accent-neon-orange`. 
- **Texture / Noise:** Gradients MUST have a subtle static/film grain texture overlaid on them. This prevents them from looking generic and gives them a tactile, premium, and slightly gritty digital feel.
- **Text:** High contrast. Pure white on dark slides; dark slate on light slides.

## Typography

Typography acts as a structural element, often serving as the primary visual graphic on the slide.

- **Primary Display (Space Grotesk):** Used for large, impactful statements (e.g., "UNLEASH YOUR WOW", "BORN TO. EXPLODE."). It should be bold, often uppercase, and feature wide letter-spacing.
- **Outline Typography:** A signature Volc style is using outlined text (e.g., the word "WOW" in the examples). For coding agents, implement this using `-webkit-text-stroke: 1px #FFFFFF; color: transparent;`.
- **Body & Secondary (Inter):** Clean, highly legible sans-serif for explanatory text, bullet points, and data.
- **Technical Accents:** Small, heavily spaced uppercase labels (e.g., "ESTRATÉGIA DIGITAL AVANÇADA") are used as kickers or category tags.

## Layout & Spacing

Presentations must feel open and breathable. 

- **Negative Space:** Use massive amounts of negative space (`spacing.xl`). Do not fill the slide corner-to-corner with text. 
- **Alignment:** Left-alignment is heavily preferred for typography to maintain a structured, editorial feel. 
- **Structural Lines:** Use thin, 1px horizontal or vertical lines to connect ideas, divide sections, or underline key headings (e.g., the line running through "PROCESSO DE VENDAS").

## Elevation & Depth

This is a strictly flat UI design, but depth is implied through the "glow" of the background gradients. Do not use standard drop shadows on cards or text. The vibrant gradient backgrounds should feel like they are glowing *behind* the solid dark foreground elements.

## Do's and Don'ts

- **DO** use thin 1px lines and crosshairs (+) to create a technical, architectural vibe.
- **DO** apply a noise/grain filter over gradients.
- **DO NOT** use rounded corners on structural layout elements; keep edges sharp and technical, except for specific interactive UI mockups.
- **DO NOT** center-align massive blocks of text.
- **DO NOT** use flat, saturated colors for backgrounds; stick to the black/white extreme or the grainy gradients.
