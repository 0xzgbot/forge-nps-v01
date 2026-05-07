---
version: alpha
name: Forge OS
description: A high-precision, cinematic command center designed for the Forge NPS Cognitive Operating System. The aesthetic is "Obsidian Studio"—dark, professional, and focused on deep concentration.
colors:
  primary: "#3D5AFE"      # Action Blue (High emphasis)
  secondary: "#A0A0A0"    # Lightened Slate for sidebar text to meet WCAG
  background: "#0A0A0A"   # Deep Obsidian (Main panels)
  surface: "#1A1A1A"      # Lighter Obsidian (Sidebar/Input areas)
  text: "#E0E0E0"         # Soft White (High readability)
  text-dim: "#999999"     # Lightened Grey for better contrast on surface
typography:
  interface:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "14px"
  data:
    fontFamily: "JetBrains Mono, monospace"
    fontSize: "13px"
  heading:
    fontFamily: "Inter, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 700
rounded:
  sm: "4px"
  md: "8px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
components:
  sidebar:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.secondary}"
    padding: "{spacing.md}"
    width: "280px"
  panel-main:
    backgroundColor: "{colors.background}"
    textColor: "{colors.text}"
    padding: "{spacing.md}"
  event-entry:
    textColor: "{colors.text-dim}"
    typography: "{typography.data}"
  input-field:
    backgroundColor: "#222222"
    textColor: "{colors.text}"
    rounded: "{rounded.sm}"
    padding: "10px"
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#FFFFFF"
    rounded: "{rounded.sm}"
    padding: "10px 20px"
  prompt-input:
    backgroundColor: "#13243a"
    textColor: "#eef6ff"
    minHeight: "132px"
    rounded: "{rounded.sm}"
  model-combo:
    description: "Flux2.Dev and Turbo share one pill. Turbo is disabled unless Flux2.Dev is checked."
---

## Overview

Forge OS follows an **Obsidian Studio** design language. It is built to minimize cognitive load for directors and engineers, providing a high-contrast, low-glare environment that feels like professional post-production software (e.g., DaVinci Resolve or Avid). 

The interface prioritizes the "Flow State" by using deep blacks to recede the UI into the background, allowing cinematic assets and real-time agent logs to take center stage.

## Colors

- **Obsidian (#0A0A0A):** The primary void. Used for main content areas to maximize perceived contrast with video/images.
- **Action Blue (#3D5AFE):** Reserved strictly for user agency—buttons, active states, and critical triggers.
- **Slate Grey (#6C7278):** Used for non-essential metadata, keeping the visual hierarchy clean.

## Typography

We utilize a dual-font system to separate "Intent" from "Data":
- **Interface (Inter):** Clean, highly legible sans-serif for navigation and labels.
- **Data (JetBrains Mono):** A technical monospace font used exclusively for agent logs, timestamps, and code payloads, ensuring alignment in vertical data streams.

## Components

`sidebar` acts as the structural anchor, utilizing a slightly elevated surface color to distinguish it from the main content void. 

All interactive elements follow the `{rounded.sm}` standard to maintain a sharp, professional edge, avoiding the "bubbly" consumer-app aesthetic.

## Current Dashboard Refresh

The active dashboard language is production-oriented rather than agency-brief-oriented:

- The main textarea is labeled **Prompt**, not Creative Brief.
- The primary generation command is **Generate Images**.
- The prompt field is intentionally larger than default inputs and uses a lighter dark-blue surface for emphasis.
- **Flux2.Dev** and **Turbo** share one pill. Turbo remains a dependent option and is disabled unless Flux2.Dev is active.
- **Flux2 Klein** remains a separate peer model toggle.
- Visible **Anchor/Anchors** terminology has been replaced with **Character/Characters**. Internal `anchor` field names stay unchanged where needed for API compatibility.

Navigation now favors operational workspaces:

- Home
- Ideas
- Characters
- Script
- Products
- Renders
- Memory
- Settings

The standalone Models tab was removed. Provider and model configuration lives in Settings.

The Ideas workspace uses a kanban layout grouped by pipeline stage. It should degrade gracefully: if the Hermes idea-board endpoint is unavailable, the frontend builds the board from `/api/shots`.
