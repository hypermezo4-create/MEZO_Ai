# MEZO AI — Design Tokens & Aesthetics

This document is the single source of truth for MEZO AI's cross-platform design aesthetics. All implementations (Web CSS, Flutter ThemeData, and Tauri native styling) must adhere to these tokens to guarantee a premium, consistent user experience.

## Design Philosophy

The USER requested:
> "Use Rich Aesthetics: The USER should be wowed at first glance by the design. Use best practices in modern web design (e.g. vibrant colors, dark modes, glassmorphism, and dynamic animations) to create a stunning first impression."

This means:
1. **Never use default colors.** No "plain red" or "plain blue". Use tailored HSL tokens.
2. **Dynamic UI:** Hover effects, micro-animations, and smooth state transitions are required.
3. **Glassmorphism:** Slight translucency on floating panels over a deeply saturated dark background.

## Color Palette (Dark Theme First)

| Token Name | HSL Value | Hex Equivalent | Usage |
|---|---|---|---|
| `--mezo-bg-primary` | `hsl(220, 20%, 8%)` | `#11141A` | Main application background |
| `--mezo-bg-panel` | `hsla(220, 25%, 15%, 0.7)`| `#1C222E (70%)`| Floating panels, glassmorphism layer |
| `--mezo-accent-primary` | `hsl(250, 85%, 65%)`| `#7B5EEB` | Primary buttons, active state indicators |
| `--mezo-accent-secondary`| `hsl(320, 80%, 60%)`| `#E53995` | Secondary actions, gradients |
| `--mezo-text-primary` | `hsl(220, 10%, 95%)`| `#F0F1F5` | Main text, headings |
| `--mezo-text-secondary`| `hsl(220, 10%, 70%)`| `#B1B4BD` | Subtitles, timestamps, muted text |
| `--mezo-status-armed` | `hsl(150, 70%, 45%)`| `#22C55E` | Kill switch active/armed (green) |
| `--mezo-status-disarmed`| `hsl(0, 80%, 60%)`| `#EF4444` | Kill switch disarmed/pulsing (red) |

## Typography

Primary Font: **Inter** or **Outfit**
Monospace Font: **Fira Code** or **JetBrains Mono**

| Token Name | Size | Weight | Usage |
|---|---|---|---|
| `--text-h1` | `2.5rem` | 700 | Main titles |
| `--text-h2` | `1.75rem`| 600 | Panel headers |
| `--text-body` | `1rem` | 400 | Chat messages, normal text |
| `--text-small` | `0.875rem`| 400 | Helper text, captions |

## Spacing Scale

| Token Name | Value | Flutter Equivalent |
|---|---|---|
| `--space-xs` | `4px` | `EdgeInsets.all(4.0)` |
| `--space-sm` | `8px` | `EdgeInsets.all(8.0)` |
| `--space-md` | `16px`| `EdgeInsets.all(16.0)`|
| `--space-lg` | `24px`| `EdgeInsets.all(24.0)`|
| `--space-xl` | `32px`| `EdgeInsets.all(32.0)`|

## Interaction & Animation

- **Hover States**: Lighten accent background by 10%.
- **Transitions**: Use `cubic-bezier(0.4, 0.0, 0.2, 1)` with `200ms` duration.
- **Backdrop Blur** (Glassmorphism): Panels use `backdrop-filter: blur(12px)`. In Flutter, wrap with `BackdropFilter(filter: ImageFilter.blur(sigmaX: 12, sigmaY: 12))`.

*Note: All platform engineers must refer to these tokens before merging UI changes.*
