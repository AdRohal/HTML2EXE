---
name: HTML to EXE Builder
description: A dark navy and violet desktop builder with the HTML2EXE logo up top and a label-tape progress strip as its one signature.
colors:
  primary: "#a78bfa"
  primary-deep: "#7c3aed"
  primary-bright: "#8b5cf6"
  primary-text: "#c4b5fd"
  success: "#34d399"
  warning: "#fbbf24"
  danger: "#f87171"
  page-navy: "#0f172a"
  rail-navy: "#0d1526"
  card: "#1e293b"
  card-deep: "#162032"
  surface: "#263248"
  log-well: "#0a1020"
  text: "#e2e8f0"
  text-2: "#cbd5e1"
  text-3: "#94a3b8"
  hairline: "rgba(255, 255, 255, 0.07)"
  hairline-strong: "rgba(255, 255, 255, 0.16)"
typography:
  display:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "28px"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.015em"
  headline:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1.3
  body:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Bahnschrift SemiCondensed, Bahnschrift, Segoe UI Semibold, Arial Narrow, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "0.1em"
  tape:
    fontFamily: "Bahnschrift SemiCondensed, Bahnschrift, Segoe UI Semibold, Arial Narrow, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "0.09em"
  mono:
    fontFamily: "Cascadia Mono, Cascadia Code, Consolas, Courier New, monospace"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.4
rounded:
  sm: "4px"
  md: "6px"
  control: "8px"
  panel: "12px"
spacing:
  xs: "6px"
  sm: "10px"
  md: "16px"
  lg: "28px"
  gutter: "40px"
components:
  button-primary:
    backgroundColor: "{colors.primary-deep}"
    textColor: "#ffffff"
    rounded: "{rounded.control}"
    height: "36px"
    padding: "0 14px"
  button-primary-hover:
    backgroundColor: "{colors.primary-bright}"
  button-secondary:
    backgroundColor: "{colors.card}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    height: "36px"
    padding: "0 14px"
  button-secondary-hover:
    backgroundColor: "{colors.surface}"
  button-quiet:
    backgroundColor: "{colors.page-navy}"
    textColor: "{colors.text-2}"
    rounded: "{rounded.control}"
  input:
    backgroundColor: "{colors.card-deep}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    height: "36px"
    padding: "0 12px"
  nav-item:
    textColor: "{colors.text-3}"
    rounded: "{rounded.control}"
    height: "38px"
    padding: "0 12px"
  nav-item-active:
    textColor: "{colors.primary-text}"
  chip:
    backgroundColor: "{colors.card-deep}"
    textColor: "{colors.text-2}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    height: "24px"
    padding: "0 8px"
  chip-ok:
    textColor: "{colors.success}"
  chip-warn:
    textColor: "{colors.warning}"
  chip-bad:
    textColor: "{colors.danger}"
  chip-ink:
    textColor: "{colors.primary-text}"
  card:
    backgroundColor: "{colors.card}"
    rounded: "{rounded.panel}"
    padding: "18px"
  tape-segment:
    backgroundColor: "{colors.card-deep}"
    textColor: "{colors.text-3}"
    typography: "{typography.tape}"
    height: "46px"
    padding: "0 14px"
  tape-segment-done:
    backgroundColor: "{colors.primary-deep}"
    textColor: "#ffffff"
  tape-segment-active:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.page-navy}"
  tape-segment-fail:
    backgroundColor: "{colors.danger}"
    textColor: "{colors.page-navy}"
  result-strip:
    backgroundColor: "{colors.success}"
    textColor: "{colors.page-navy}"
    typography: "{typography.tape}"
    height: "34px"
    padding: "0 16px"
  log-well:
    backgroundColor: "{colors.log-well}"
    textColor: "{colors.text-2}"
    typography: "{typography.mono}"
    padding: "12px 14px"
---

# Design System: HTML to EXE Builder

## Overview

**Creative North Star: "The Night Shift Label Maker"**

A dark navy desktop tool that prints a label. The page is deep navy (#0f172a), the sidebar and title bar drop one step darker (#0d1526), and everything the user works in sits on slate cards one to two steps lighter. Violet is the single brand voice: it fills the primary action, tints the active nav item, and drives the progress strip. The HTML2EXE logo (38px, 10px radius) opens the sidebar and carries the brand; nothing else in the window is decorative.

The signature is the label-tape strip. A build is a row of printed segments (queued, active, done, failed) that ends in a cut label carrying the exe name. Tape lettering is Bahnschrift SemiCondensed in uppercase, which is also the voice of every label, chip and table header. Control chrome stays ordinary: buttons, inputs, details, tables. Density is calm and tool-like; a build takes minutes, so progress, log and Cancel carry the screen.

Note on provenance: the earlier light-paper and yellow-tape look is retired. The owner asked for the original brand palette back; layout, tape strip, result label, tables and forms were kept and recolored.

**Key Characteristics:**
- Tonal layering on navy: page, then card, then surface, with hairline white borders. No light surfaces.
- One accent family: violet gradient button, violet-tint nav, violet tape.
- Three type voices: Segoe UI for text, Bahnschrift caps for labels and tape, Cascadia Mono for paths and log.
- Status color is saturated pastel on dark (green, amber, red) and always paired with an icon or word.
- Fixed px type scale, no fluid type; one 880px content column.

## Colors

A restrained dark palette: navy ground, slate cards, one violet accent family, three status colors.

### Primary
- **Lilac Signal** (#a78bfa): the active tape segment, focus ring and input focus border, and caret. Used sparingly on its own; it is the "something is happening" color.
- **Deep Violet** (#7c3aed): done tape segments, the primary button gradient start, step numbers in the first-run list, text selection, checkbox accent.
- **Bright Violet** (#8b5cf6): the primary button gradient end and its hover start.
- **Pale Violet Text** (#c4b5fd): violet used as text on dark (active nav label, links, ink chips, BETA tag); chosen to stay above 4.5:1 on the cards.

### Neutral
- **Page Navy** (#0f172a): the work surface, sticky action bar, and the dark ink on lilac and green tape.
- **Rail Navy** (#0d1526): sidebar and custom title bar.
- **Slate Card** (#1e293b): cards, tables, secondary buttons, result label body.
- **Deep Slate** (#162032): inputs, chips, table heads, the idle tape, path wells.
- **Raised Slate** (#263248): hover fills, counts, stopped tape, toasts.
- **Log Well** (#0a1020): the build log background, darker than the page so output reads as a terminal.
- **Mist** (#e2e8f0): primary text. **Fog** (#cbd5e1): secondary text. **Slate Gray** (#94a3b8): helper text, labels, idle nav.
- **Hairline** (white at 7%) and **Hairline Strong** (white at 16%): all borders and the dashed tape perforations.

### Status
- **Mint** (#34d399): ready, supported, verified, the finished-OK label strip.
- **Amber** (#fbbf24): warnings and notes, optional-tool chips, log command lines.
- **Coral** (#f87171): errors, failed tape, destructive hover, invalid input border.

### Named Rules
**The One Voice Rule.** Violet is the only accent. Mint, amber and coral appear only as status, never as decoration.

**The Tint Not Fill Rule.** Chips and the active nav item are a translucent tint of their color (14-16% alpha with a 40% border), never a solid fill. Solid fills are reserved for tape segments, the result strip and primary buttons.

## Typography

**Display / Body Font:** Segoe UI Variable Text (with Segoe UI, system-ui, sans-serif)
**Label / Tape Font:** Bahnschrift SemiCondensed (with Bahnschrift, Segoe UI Semibold, Arial Narrow)
**Mono Font:** Cascadia Mono (with Cascadia Code, Consolas)

**Character:** Plain Windows-native text with a condensed, stamped caps voice for anything that reads like a printed label. The mono face is kept for things the user may copy.

### Hierarchy
- **Display** (700, 28px, 1.15, -0.015em): one h1 per view.
- **Headline** (700, 20px, 1.2): the job title above the tape.
- **Title** (700, 16px, 1.3): empty-state headings.
- **Body** (400, 14px, 1.5): all text; ledes cap at 62ch, empty-state copy at 56ch. Strong labels use 600.
- **Label** (600, 12px, 0.1em, uppercase, Bahnschrift): section headings, sidebar group label, table heads, fieldset legends, chips (0.07em).
- **Tape** (600, 13px, 0.09em, uppercase, Bahnschrift): tape segments and the result strip (0.12em). The result file name is the one large tape-face moment (600, 28px).
- **Mono** (13px, Cascadia Mono): folder paths and result paths; the log runs 12.5px / 1.55.
- Helper and meta text is 13px.

### Named Rules
**The Three Voices Rule.** Sentences are Segoe, stamps are Bahnschrift caps, copyable paths and logs are Cascadia. Do not mix a voice into another's job.

**The Fixed Scale Rule.** Sizes come from 12, 13, 14, 16, 20, 28 px. Intentional exceptions in the build: 15px for the logo wordmark and large buttons, 11px for the logo subtitle, 12.5px for the log.

## Layout

A frameless window: a 36px title bar over a two-column shell. The sidebar is 244px and the main area is one column, capped at 880px, with 40px side padding, 28px top padding and a stable scrollbar gutter. A view is a head (h1, lede) followed by stages; sections are separated by 18-28px, form fields by 18px, inline gaps by 6-16px. Grids are simple: a two-column field row (16px gap), a 140px+140px window-size grid, and a four-column system row (100px, flexible, flexible, 92px).

The project table is fixed-layout and drops its third column under 1260px. Under 1000px the sidebar folds to a 56px icon rail (labels, meta and the wordmark hide, the logo shrinks to 32px, status dot moves to the corner), main padding falls to 24px and the choose slot wraps. The primary action bar sticks to the bottom of long forms on the page background with a hairline top rule.

## Elevation & Depth

Depth is tonal first: page, card, raised surface, with hairline borders doing the separating. Shadows are soft and neutral black, used for exactly three things: the primary button's resting lift, the tape strip and result label panels, and toasts. Focus is a violet border plus a 3px translucent violet halo on inputs, a 2px violet outline elsewhere.

### Shadow Vocabulary
- **Panel** (`box-shadow: 0 2px 12px rgba(0, 0, 0, 0.35)`): tape strip, result label, toasts.
- **Lift** (`box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4)`): primary button at rest; hover deepens to `0 4px 10px rgba(0, 0, 0, 0.45)`, pressed removes it.
- **Input halo** (`box-shadow: 0 0 0 3px rgba(167, 139, 250, 0.25)`): focused text and number inputs.

### Named Rules
**The Neutral Shadow Rule.** Shadows are black, never violet, never offset-hard. Violet glow is not part of this system.

## Shapes

Four radii: 4px for tiny tags (nav count, BETA), 6px for chips, small buttons, path wells and step numbers, 8px for controls (buttons, inputs, nav items, the tape container, the toast), 12px for panels (cards, tables' wrappers, slot, result label, log box, system rows). The logo uses 10px. Borders are 1px hairlines; the one dashed element is the choose slot (1.5px, violet at 40%) and the dashed perforation between tape segments. Tape segments are square-edged inside a rounded, clipped container, so the strip reads as a single piece of tape.

## Components

### Buttons
- **Shape:** 8px radius, 36px high, 14px side padding; large is 42px (15px text), small is 28px with a 6px radius; icon buttons are 32px square.
- **Primary:** a diagonal violet gradient (#7c3aed to #8b5cf6) with white text and the neutral Lift shadow. Hover lightens the gradient and deepens the shadow; active drops the shadow and presses down 1px.
- **Secondary:** Slate Card fill with a strong hairline border; hover goes to Raised Slate.
- **Quiet and danger:** quiet is borderless with Fog text and a Raised Slate hover; danger keeps neutral fill, coral text, and a coral-tinted hover with a coral border.
- **Disabled:** 45% opacity, no pointer events. Links are Pale Violet, underlined at 3px offset, thickening on hover.

### Chips
- **Style:** 24px high, 6px radius, Bahnschrift caps at 12px, Deep Slate fill with a strong hairline border; icons are 14px.
- **State:** ok, warn, bad and ink variants use the Tint Not Fill Rule in mint, amber, coral and violet. Chip buttons (recent-project shortcuts) are 26px, Segoe sentence case, and hover to Raised Slate.

### Cards / Containers
- **Corner Style:** 12px.
- **Background:** Slate Card, with a hairline border; lists are 1px-gap stacks on a hairline background inside one clipped 12px frame.
- **Shadow Strategy:** none at rest; only the tape strip and result label take the Panel shadow.
- **Internal Padding:** 10-14px rows, 18-26px for first-run and empty states.

### Inputs / Fields
- **Style:** Deep Slate fill, strong hairline border, 8px radius, 36px high, Mist text, placeholders in Slate Gray, labels 600.
- **Focus:** border turns Lilac with the translucent halo. Hover brightens the border to white at 28%.
- **Error:** invalid border is Coral, with 13px Coral help text. Checkboxes are 18px with Deep Violet accent.

### Navigation
- The sidebar leads with the logo block (logo, "HTML2EXE" 15px bold, "App Builder" 11px, a hairline rule below). Items are 38px, 8px radius, Slate Gray text; hover adds a white 5% fill; the current page gets a violet tint (15%), Pale Violet text and weight 600. Counts are small Raised Slate tags; BETA is an outlined violet tag. The status dot is slate, mint or coral. Below 1000px items collapse to centered icons.

### Tape Strip (signature)
- A flat row of equal segments in a clipped 8px container with Deep Slate fill. Each segment is 46px high, Bahnschrift caps, with a 16px check icon visible only when done. Segments are divided by 1px dashed perforations (brighter after a done segment). States: idle is Slate Gray on Deep Slate; **done** is Deep Violet with white text; **active** is Lilac with navy text and a 4px navy bar that slides across the bottom edge (1.1s loop, becomes a static full-width 3px bar under reduced motion); **fail** is Coral with navy text; **stop** is Raised Slate.
- Under it: a one-line "now doing" note in 13px Slate Gray, then the log.

### Finished Label (signature)
- A 12px-radius card with Panel shadow. A 34px strip in tape caps carries the outcome: Deep Violet while neutral, Mint with navy text for Done, Coral for Failed, Raised Slate for Cancelled. The body shows the exe name in 28px tape face, meta (13px, values in Mist), the path in a mono well, and actions. The Build log sits below as a collapsible card with a Log Well pre; log lines tint amber for commands, soft red for errors, soft green for success.

### Tables and System Rows
- Fixed-layout table on Slate Card with a hairline frame; head cells are Deep Slate with Label type. Rows have 11px vertical padding and hairline tops; numbers are tabular in Slate Gray; names are 600 with a 13px sub line; row actions right-align. System rows use the four-column grid inside a clipped 12px frame.

## Do's and Don'ts

### Do:
- **Do** build every new surface from the tonal ladder: Page Navy, Slate Card (#1e293b), Deep Slate (#162032), Raised Slate (#263248), separated by hairline borders.
- **Do** keep violet as the only accent; primary buttons use the violet gradient with white text and the neutral Lift shadow.
- **Do** put 12px radius on panels, 8px on controls, 6px on chips and small buttons, 4px on tiny tags.
- **Do** set stamps (section labels, chips, table heads, tape) in Bahnschrift SemiCondensed uppercase with 0.07-0.12em tracking; set paths and logs in Cascadia Mono.
- **Do** show state with the tape vocabulary: done is Deep Violet, active is Lilac with the sliding bar, fail is Coral.
- **Do** pair every status color with an icon or word, and honor reduced motion.

### Don't:
- **Don't** reintroduce the light paper surfaces, yellow tape or black-tape button of the retired look.
- **Don't** add a second accent hue, or use mint, amber and coral for anything other than status.
- **Don't** use violet glows, hard offset shadows, or shadows other than the three in the vocabulary.
- **Don't** replace the drawn stroke icons (1.75 stroke on a 24px grid) with glyphs or emoji.
- **Don't** pad the layout with stat-card dashboards or multi-page wizards; one column, one primary action.
- **Don't** use solid fills for chips or the active nav item; tint them.
