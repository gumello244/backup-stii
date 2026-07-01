---
version: alpha
name: Remos
description: A premium visual identity and theme specification for the Remos application.
colors:
  primary: "#3B6EA5"           # Dark Pastel Blue Accent (RM_ACCENT)
  primary-hover: "#2C5282"     # Accent Hover (RM_ACCENT_HOVER)
  primary-pressed: "#1E3A5F"   # Accent Pressed (RM_ACCENT_PRESSED)
  primary-container: "#EBF3FC" # Light Blue Bento Hero BG (RM_HERO_BG)
  secondary: "#27AE60"         # Green Success (RM_GREEN)
  secondary-container: "#EAF7ED" # Soft Green Bento Success BG (RM_SUCCESS_BG)
  tertiary: "#B7950B"          # Yellow Warning (RM_YELLOW)
  tertiary-container: "#FCF3CF" # Soft Yellow Container (RM_YELLOW_SOFT)
  neutral-dark: "#1A202C"      # Deep Charcoal Text (RM_TEXT)
  neutral-muted: "#718096"     # Slate Gray Muted Text (RM_TEXT_MUTED)
  neutral-light: "#F9F9F9"     # Premium Surface Gray (RM_SURFACE)
  surface: "#FFFFFF"           # Solid Background White (RM_BG)
  border: "#EEEEEE"            # Light Border (RM_BORDER)
  error: "#C0392B"             # Deep Red Error (RM_RED)
  error-container: "#FDF2F2"   # Soft Red Bento Danger BG (RM_DANGER_BG)
typography:
  fontFamily: Segoe UI, Arial, sans-serif
  h1:
    fontFamily: Segoe UI
    fontSize: 22px
    fontWeight: 700
    lineHeight: 1.25
  body:
    fontFamily: Segoe UI
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
rounded:
  xs: 4px
  sm: 6px
  md: 8px
  lg: 12px
  full: 9999px
spacing:
  xs: 2px
  sm: 4px
  md: 8px
  lg: 12px
  xl: 14px
---

# Overview

Remos is a desktop backup restoration and management application built using Python and PyQt5. The design system focuses on a clean, light-only layout utilizing a native Windows font family (`Segoe UI`) and a structured Bento Grid layout for high information density and premium visual hierarchy.

# Colors

We enforce a light-only color theme with high-contrast pastel accents:
- **Accent / Primary (`#3B6EA5`)**: Denotes primary focus, branding, and major action paths.
- **Success (`#27AE60`)**: Indicates successful operations and complete backups.
- **Warning (`#B7950B`)**: Highlights conflicts, skipped files, and warnings.
- **Danger / Error (`#C0392B`)**: Shows errors, cancellation actions, and risky states.
- **Neutral Dark (`#1A202C`)**: Used for highly legible main text.
- **Neutral Muted (`#718096`)**: Secondary subtitle and caption text color.
- **Surfaces (`#F9F9F9`)**: Background for cards, selectors, and secondary states.
- **Window Background (`#FFFFFF`)**: Base backdrop for the main application container.

# Typography

System fonts ensure native performance and premium readability across Windows installations:
- **Font Stack**: `Segoe UI`, `Arial`, sans-serif.
- **View Titles**: `22px` Bold (`font-weight: bold`), dark charcoal (`#1A202C`).
- **View Subtitles**: `14px` Regular, slate gray (`#718096`).
- **Accent Labels**: `14px` Semi-bold (`font-weight: 600`), accent color (`#3B6EA5`).
- **Bento Card Hierarchy**:
  - **Bento Title (Header)**: `9px` Extra-bold (`font-weight: 800`), uppercase, `1px` letter-spacing, muted gray (`#718096`).
  - **Bento Value (Default)**: `20px` Bold (`font-weight: 700`), dark charcoal (`#1A202C`).
  - **Bento Value (Hero)**: `32px` Extra-bold (`font-weight: 800`), negative letter-spacing (`-1px`), accent color (`#3B6EA5`).
  - **Bento Subtitle**: `11px` Regular, muted gray (`#718096`).

# Layout

The guided user experience fits in a compact, fixed viewport:
- **Window Size**: Fixed `660x440px` (QMainWindow).
- **Margins**: `40px` left/right, `20px` or `30px` top/bottom margins on views.
- **Vertical spacing**: `14px` standard between layout rows; `12px` for buttons.
- **Bento Grid Spacing**: `8px` gaps between cards in grid structures.

# Shapes

Rounded shapes establish a friendly, state-of-the-art interactive experience:
- **Bento Cards**: Corner radius of `12px` (`lg`).
- **Surface Cards**: Corner radius of `10px` (`md`).
- **Action Buttons**: Corner radius of `8px` (`md`).
- **Progress Bars & Checkboxes**: Corner radius of `6px` (`sm`).
