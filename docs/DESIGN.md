# Hariq — Design system

**Product:** Wildfire early warning for northern Algeria (see `SPEC.md`)
**Version:** 0.1 · 2026-11-20 · owner: FS (full-stack lead), UX1/UX2 for review
**Source of truth for visuals:** Framer project → https://framer.com/projects/DTkE32V5oMTPUO4AmRPG
**Code targets:** `apps/dashboard` (React 19 + Vite + TypeScript + **shadcn/ui** + Tailwind v4 + MapLibre) and `apps/mobile` (Expo / React Native)

> "Hariq" (حريق, *fire*) is a **placeholder name** that matches the H logo. Rename it in one place (`src/config/brand.ts`) and in the Framer nav/footer.

---

## 1. Principles

These come straight from the spec. They override any visual preference.

1. **Status is always written in words, never shown by colour alone.** Every coloured thing (row, chip, map pin, phone screen) carries the word: LEAVE NOW / GET READY / SAFE / CANCELLED.
2. **Never show "safe" while a fire is active nearby.** Only an `update` or a `cancel` from Civil Protection changes an alert screen.
3. **Data age is always visible.** Header chip on the dashboard, a line on every alert screen, and a banner when the latest pass is more than 180 minutes old.
4. **Urgency sets the order of everything.** Lists sort by minutes left, ascending. The most urgent thing is the biggest number on screen.
5. **Right-to-left per text block.** Arabic and Darija flip per block (`dir="rtl"` on web, `writingDirection: 'rtl'` in React Native). Never flip the whole layout globally.
6. **Honest numbers.** Anything not read from `scoreboard.json` is labelled "Sample values". False alarms appear next to the hits.
7. **Built for bad conditions:** Slow 3G (< 1 MB JS), a noisy hall, sunlight on a laptop, phones on a desk. Prefer big type, high contrast and few colours.

---

## 2. Brand

| Item | Rule |
| --- | --- |
| Logo mark | Charcoal "H" with a flame and a map pin. Use it **only on light surfaces** (paper, white, sand). |
| Minimum size | 20 px tall on screen. Clear space = the width of the pin on every side. |
| Wordmark | "Hariq" in Archivo 800, letter-spacing −0.03em, next to the mark with an 8–10 px gap. |
| Tagline | "Wildfire early warning", IBM Plex Mono 500, 10 px, uppercase, +0.06em. |
| Dark surfaces | **Open item:** we need a reversed (white H) version of the logo. Until then, don't place the logo on ink or charcoal. |

---

## 3. Colour

### 3.1 Palette

Light theme only for v1. The dark band on the landing page and the phone screens use explicit colours, not a `.dark` theme.

| Token | Hex | OKLCH | Use |
| --- | --- | --- | --- |
| `paper` | `#F3F0EA` | `oklch(0.956 0.009 84.6)` | App and page background |
| `surface` | `#FFFFFF` | `oklch(1 0 0)` | Cards, panels, popovers, inputs |
| `sand` | `#E8E3D9` | `oklch(0.917 0.014 84.6)` | Secondary surfaces, context strip, footer |
| `ink` | `#1C1B1A` | `oklch(0.223 0.002 67.7)` | Text, primary buttons, dark band |
| `muted` | `#5F5A53` | `oklch(0.470 0.013 76.5)` | Secondary text, labels |
| `line` | ink at 12% | `oklch(0.223 0.002 67.7 / 12%)` | Borders and dividers (1 px) |
| `charcoal` | `#2B2B2B` | `oklch(0.289 0 0)` | Logo colour, CANCELLED phone screen |
| `fire` | `#E3262B` | `oklch(0.590 0.221 26.4)` | LEAVE NOW, alert actions, 1 h zone |
| `fire-text` | `#B8161B` | `oklch(0.500 0.193 27.0)` | Red text **smaller than 19 px** |
| `ember` | `#9E1016` | `oklch(0.446 0.173 26.7)` | Burning cells (core) |
| `flame` | `#F26A21` | `oklch(0.683 0.185 44.0)` | GET READY, 2 h zone, false-alarm numbers |
| `flame-text` | `#B5470F` | `oklch(0.540 0.155 42.1)` | Orange text **smaller than 19 px** |
| `safe` | `#6F6A62` | `oklch(0.526 0.014 79.7)` | SAFE status (text, outline chip) |
| `safe-line` | `#D6D0C5` | `oklch(0.859 0.016 82.8)` | SAFE status strip |
| `ok` | `#2F9E5B` | `oklch(0.621 0.141 152.6)` | System health only: "connected", model dot. **Never** used for village status. |
| `ok-text` | `#1F6E3E` | `oklch(0.478 0.108 152.6)` | Text on `ok` tints |
| `map-land` | `#ECE7DD` | `oklch(0.929 0.014 84.6)` | Map background |
| `map-sea` | `#D3DFE1` | `oklch(0.895 0.013 208.8)` | Sea fill |

**Why there is no green for "safe":** a green village next to an active fire reads as "all clear", which principle 2 forbids. SAFE is a neutral grey plus the word.

### 3.2 Contrast (WCAG 2.x, measured)

| Pair | Ratio | Allowed for |
| --- | --- | --- |
| White on `fire` | 4.59 | All text (AA) |
| `ink` on `flame` | 5.62 | All text (AA). **This is why the GET READY screen has black text.** |
| White on `flame` | 3.06 | ❌ Don't use. Fails for normal text. |
| `fire` on white | 4.59 | All text |
| `fire` on `paper` | 4.03 | Large text only (≥ 19 px bold or ≥ 24 px) → use `fire-text` below that |
| `flame` on white | 3.06 | Large text only (≥ 19 px bold) → use `flame-text` below that |
| `muted` on `paper` | 6.01 | All text |
| `safe` on white | 5.37 | All text |
| `ink` on `paper` | 15.12 | All text |

Rule of thumb: **red and orange text below 19 px always uses the `-text` variant.**

---

## 4. shadcn/ui setup (dashboard)

### 4.1 Install (Vite + React 19 + Tailwind v4, npm per D-11)

```bash
npm create vite@latest dashboard -- --template react-ts
cd dashboard
npm install tailwindcss @tailwindcss/vite
# add the tailwindcss() plugin and the "@/*" path alias, as in the shadcn Vite guide
npx shadcn@latest init            # style: new-york, base colour: stone, CSS variables: yes
npx shadcn@latest add button badge card checkbox table tabs toggle-group scroll-area \
  separator tooltip sonner alert sheet select input switch skeleton navigation-menu
npm install @fontsource/archivo @fontsource/ibm-plex-sans @fontsource/ibm-plex-mono \
  @fontsource/ibm-plex-sans-arabic @phosphor-icons/react
```

Import only the weights we use (keeps the Slow 3G budget):

```ts
// src/main.tsx
import "@fontsource/archivo/700.css";
import "@fontsource/archivo/800.css";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "@fontsource/ibm-plex-sans-arabic/500.css";
import "@fontsource/ibm-plex-sans-arabic/700.css";
```

### 4.2 `src/index.css`: theme tokens

Replace the variables that `shadcn init` generated with this block. Keep the `@import` lines it added at the top.

```css
:root {
  --radius: 0.75rem; /* lg 12px · md 10px (buttons) · sm 8px (chips) · xl 16px (cards) */

  /* shadcn semantic tokens */
  --background: oklch(0.956 0.009 84.6);          /* paper */
  --foreground: oklch(0.223 0.002 67.7);          /* ink */
  --card: oklch(1 0 0);
  --card-foreground: oklch(0.223 0.002 67.7);
  --popover: oklch(1 0 0);
  --popover-foreground: oklch(0.223 0.002 67.7);
  --primary: oklch(0.223 0.002 67.7);             /* ink buttons */
  --primary-foreground: oklch(1 0 0);
  --secondary: oklch(0.917 0.014 84.6);           /* sand */
  --secondary-foreground: oklch(0.223 0.002 67.7);
  --muted: oklch(0.917 0.014 84.6);
  --muted-foreground: oklch(0.470 0.013 76.5);
  --accent: oklch(0.917 0.014 84.6);
  --accent-foreground: oklch(0.223 0.002 67.7);
  --destructive: oklch(0.590 0.221 26.4);         /* fire */
  --border: oklch(0.223 0.002 67.7 / 12%);
  --input: oklch(0.223 0.002 67.7 / 20%);
  --ring: oklch(0.223 0.002 67.7 / 45%);

  --chart-1: oklch(0.590 0.221 26.4);             /* fire */
  --chart-2: oklch(0.683 0.185 44.0);             /* flame */
  --chart-3: oklch(0.526 0.014 79.7);             /* safe grey */
  --chart-4: oklch(0.223 0.002 67.7);             /* ink */
  --chart-5: oklch(0.859 0.016 82.8);             /* baseline bars */

  --sidebar: oklch(1 0 0);
  --sidebar-foreground: oklch(0.223 0.002 67.7);
  --sidebar-primary: oklch(0.223 0.002 67.7);
  --sidebar-primary-foreground: oklch(1 0 0);
  --sidebar-accent: oklch(0.917 0.014 84.6);
  --sidebar-accent-foreground: oklch(0.223 0.002 67.7);
  --sidebar-border: oklch(0.223 0.002 67.7 / 12%);
  --sidebar-ring: oklch(0.223 0.002 67.7 / 45%);

  /* Hariq tokens */
  --fire: oklch(0.590 0.221 26.4);
  --fire-foreground: oklch(1 0 0);
  --fire-text: oklch(0.500 0.193 27.0);
  --flame: oklch(0.683 0.185 44.0);
  --flame-foreground: oklch(0.223 0.002 67.7);    /* black on orange, never white */
  --flame-text: oklch(0.540 0.155 42.1);
  --ember: oklch(0.446 0.173 26.7);
  --safe: oklch(0.526 0.014 79.7);
  --safe-line: oklch(0.859 0.016 82.8);
  --charcoal: oklch(0.289 0 0);
  --sand: oklch(0.917 0.014 84.6);
  --ok: oklch(0.621 0.141 152.6);
  --ok-text: oklch(0.478 0.108 152.6);
  --map-land: oklch(0.929 0.014 84.6);
  --map-sea: oklch(0.895 0.013 208.8);
}

@theme inline {
  --font-sans: "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif;
  --font-display: "Archivo", "IBM Plex Sans", sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, monospace;
  --font-arabic: "IBM Plex Sans Arabic", "IBM Plex Sans", sans-serif;

  --color-fire: var(--fire);
  --color-fire-foreground: var(--fire-foreground);
  --color-fire-text: var(--fire-text);
  --color-flame: var(--flame);
  --color-flame-foreground: var(--flame-foreground);
  --color-flame-text: var(--flame-text);
  --color-ember: var(--ember);
  --color-safe: var(--safe);
  --color-safe-line: var(--safe-line);
  --color-charcoal: var(--charcoal);
  --color-sand: var(--sand);
  --color-ok: var(--ok);
  --color-ok-text: var(--ok-text);
  --color-map-land: var(--map-land);
  --color-map-sea: var(--map-sea);
}
```

The shadcn `@theme inline` block that `init` generates already maps `--color-background`, `--color-primary` and the rest, so keep it. The block above only **adds** our tokens, which gives you utilities like `bg-fire`, `text-flame-text` and `font-display`.

`components.json`: keep `"cssVariables": true`. shadcn's own components use Lucide icons internally; we use **Phosphor** (`@phosphor-icons/react`) for our own UI, so it matches the Framer file. That's fine to mix.

---

## 5. Typography

| Style | Font | Weight | Size (desktop / tablet / phone) | Line height | Tracking | Tailwind |
| --- | --- | --- | --- | --- | --- | --- |
| Display (page H1) | Archivo | 800 | 68 / 54 / 40 | 1.0 | −0.035em | `font-display font-extrabold text-[68px] leading-none tracking-[-0.035em]` |
| H2 (section) | Archivo | 800 | 44 / 36 / 30 | 1.05 | −0.03em | `font-display font-extrabold text-[44px] leading-[1.05] tracking-[-0.03em]` |
| H3 (card title) | Archivo | 700 | 21 | 1.25 | −0.01em | `font-display font-bold text-[21px]` |
| Big number (minutes) | Archivo | 800 | 26 (row) · 64 (scoreboard) · 96 (phone) | 0.9–1.0 | −0.04em | `font-display font-extrabold tabular-nums` |
| Lead | IBM Plex Sans | 400 | 19 / 18 / 17 | 1.5 | 0 | `text-[19px] text-muted-foreground` |
| Body | IBM Plex Sans | 400 | 16 | 1.55 | 0 | `text-base leading-[1.55] text-muted-foreground` |
| UI (buttons, nav, row names) | IBM Plex Sans | 500–600 | 13–16 | 1.2 | 0 | `text-sm font-semibold` |
| Label | IBM Plex Mono | 500 | 12 (10–11 inside dense UI) | 1.3 | +0.08em, UPPERCASE | `font-mono text-xs uppercase tracking-[0.08em] text-muted-foreground` |
| Status word | IBM Plex Mono | 600 | 10.5–12 | 1.2 | +0.06em, UPPERCASE | `font-mono text-[10.5px] font-semibold uppercase tracking-[0.06em]` |
| Arabic / Darija | IBM Plex Sans Arabic | 500 / 700 | same size as the Latin equivalent, +2 px for body text | 1.6 | 0 | `font-arabic` + `dir="rtl"` on the block |

Rules:
- **All numbers that change** (minutes, times, km, percentages) use `tabular-nums` so the list doesn't jitter between updates.
- Use typographic quotes and apostrophes (’ “ ”) in UI copy.
- Kabyle (Latin) uses ɣ, ẓ, ḥ, ṛ, ḍ, ε. **Check that IBM Plex Sans renders each of them**; if any falls back, add `Noto Sans` after Plex in `--font-sans`. If Q-6 picks Tifinagh, add Noto Sans Tifinagh.

---

## 6. Space, layout, shape

| Thing | Value |
| --- | --- |
| Base unit | 4 px. Scale: 4 · 8 · 12 · 16 · 24 · 32 · 48 · 56 · 64 · 88 · 104 |
| Content width | 1120 px max, centred |
| Page gutters | 40 px desktop · 32 px tablet · 20 px phone |
| Section padding (marketing pages) | 104 px desktop · 80 px tablet · 64 px phone |
| Breakpoints | Framer frames: 1200 / 810 / 390. In Tailwind, use `md:` (≥ 768) for tablet and `lg:` (≥ 1024) for desktop. |
| Radius | chips 6–8 px · buttons and inputs 10 px · cards 16–18 px · CTA band 24 px · phone screen 38 px. Nested radii are concentric. |
| Borders | 1 px `border-border` everywhere. Status strips are 3–4 px solid status colour. |
| Elevation | Level 1 (cards on the map): `0 1px 2px rgb(0 0 0/.08), 0 6px 16px rgb(0 0 0/.06)`. Level 2 (preview cards, phones): `0 1px 2px rgb(0 0 0/.06), 0 16px 40px rgb(0 0 0/.08)`. Toast: `0 8px 24px rgb(0 0 0/.2)`. |
| Tap targets | ≥ 44 × 44 px on touch. Dashboard buttons are ≥ 36 px tall with full-row click areas. |

---

## 7. Status system (the core of the product)

| Level (`status` / alert `level`) | Rule | Fill | Text on fill | Small text colour | Word (EN) | Icon | Map |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `leave_now` | minutes left < 60 | `fire` | white | `fire-text` | LEAVE NOW | `Siren` | pin with red strip |
| `get_ready` | 60 ≤ minutes ≤ 120 | `flame` | **ink** | `flame-text` | GET READY | `Bell Ringing` | pin with orange strip |
| `safe` | > 120 min, or no zone within 15 km | none (outline) | — | `safe` | SAFE | — | grey pin |
| `outside_model_window` | inside 15 km but outside the tile | none (outline) | — | `safe` | SAFE · OUTSIDE WINDOW | `Info` | grey pin, flagged |
| `update` | minutes left rose on 2 runs in a row | `ink` | white | `ink` | UPDATE | `Arrows Clockwise` | — |
| `cancel` | operator pressed Cancel | `charcoal` | white | `ink` | CANCELLED | `Shield Check` | — |

Boundary checks (from the spec's unit tests): 60 → `get_ready`, 59 → `leave_now`.

**Level words (draft, needs native check before use; owned by CO in `contracts/alert_texts.json`):**

| | LEAVE NOW | GET READY | CANCELLED |
| --- | --- | --- | --- |
| Français | Partez maintenant | Préparez-vous | Alerte annulée |
| العربية | غادروا الآن | استعدّوا | أُلغي التنبيه |
| Darija (Arabic script, Q-6 default) | خرجو دركا | وجدو رواحكم | CO to supply |
| Taqbaylit (Latin, Q-6 default) | Ffeɣ tura | CO to supply | CO to supply |

**Direction to leave**, 8-point compass. EN: N, NE, E, SE, S, SW, W, NW. FR: nord, nord-est, est, sud-est, sud, sud-ouest, ouest, nord-ouest. AR: الشمال، الشمال الشرقي، الشرق، الجنوب الشرقي، الجنوب، الجنوب الغربي، الغرب، الشمال الغربي. Darija and Taqbaylit: CO to supply. The arrow always shows next to the word.

### 7.1 `StatusBadge` (shadcn Badge + variants)

```tsx
// src/components/status-badge.tsx
import { cva } from "class-variance-authority";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const statusBadge = cva(
  "rounded-md px-2 py-1 font-mono text-[10.5px] font-semibold uppercase tracking-[0.06em] border-transparent",
  {
    variants: {
      status: {
        leave_now: "bg-fire text-fire-foreground",
        get_ready: "bg-flame text-flame-foreground",
        safe: "bg-transparent border-border text-safe",
        update: "bg-primary text-primary-foreground",
        cancel: "bg-charcoal text-white",
      },
    },
  }
);

const LABEL = { leave_now: "Leave now", get_ready: "Get ready", safe: "Safe", update: "Update", cancel: "Cancelled" } as const;

export function StatusBadge({ status, className }: { status: keyof typeof LABEL; className?: string }) {
  return <Badge className={cn(statusBadge({ status }), className)}>{LABEL[status]}</Badge>;
}
```

### 7.2 Button variants

Add one variant to the generated `button.tsx` `cva`:

```ts
alert: "bg-fire text-fire-foreground hover:bg-fire/90 focus-visible:ring-fire/40",
```

| Use | Variant |
| --- | --- |
| Send alert, Start a demo fire, landing hero CTA | `alert` |
| Open dashboard, secondary actions on light surfaces | `default` (ink) |
| Cancel alert, Reset demo, "See the phone alert" | `outline` |
| Sort, layer toggles, nav links | `ghost` |

Never put two `alert` buttons side by side. Cancel is always `outline`, never red, so the two actions can't be confused.

---

## 8. Component inventory (Framer → code)

| Framer component / frame | Code (dashboard: shadcn) | Notes |
| --- | --- | --- |
| **Site Nav** | `NavigationMenu`; `Sheet` for the phone drawer | Sticky, 72 px, paper fill, 1 px bottom line. Current-page link in `fire-text`. |
| **App header** (dashboard) | custom `header` + `ToggleGroup` (Replay / Live / Demo) + status chips | 60 px, white. The active mode is the only filled item (Demo = `fire`). |
| Status chips (Model C · auto, Pass 22 min ago, wind, receivers) | `Badge variant="outline"` + Phosphor icon + optional 8 px dot | Data-age chip turns into a `fire` banner at > 180 min. |
| Fire context strip | `div` on `sand` + `Badge` (DEMO FIRE D-07) + `Button variant="outline" size="sm"` | One line; text truncates before the button. |
| **Village row** | custom: `Checkbox` + status strip + minutes + names + `StatusBadge` | Props: name_fr, name_ar, minutes_left, distance_km, leave_direction, alert_state, status, selected. 64 px min height. Arabic name in `font-arabic` with `dir="rtl"` on its span. |
| Village list | `ScrollArea` | Header with filter `ToggleGroup` (All / Leave now / Get ready / Safe + counts) and a sort button. |
| Action bar | `div` + `Select` (level) + `Button outline` Cancel + `Button alert` Send alert | Shows "N selected". Disabled state when 0 are selected. |
| Alert log | list or `Table` (compact) | time (mono) · `StatusBadge` · place · source (auto/operator). Show "0 receivers connected" in `fire-text` when that happens. |
| Map overlays: Layers, Weather, Demo hint, Zoom, Scale | `Card` (white, 96% opacity, level-1 shadow) + `Switch` or `Checkbox` | Top-left layers, top-right weather, bottom-left hint, bottom-right zoom. 16 px from the map edges. |
| Toast ("LEAVE NOW sent to Irdjen · 3 phones") | `Sonner` (`toast.success`) | Ink background, green check. Top-centre of the map. |
| Stale data / disconnected banner | `Alert` with `fire` fill | Words + icon. Never dismissible while the condition holds. |
| **Fire map** | MapLibre (see §9) + HTML markers for village pins | The pin card is a 150 px white card with a 3 px status strip, name, and status line. |
| **Phone alert** (Leave now / Get ready / Cancelled) | Expo app, not shadcn (see §10) | |
| Scoreboard table | `Table` | Keep it horizontally scrollable below 1024 px (`min-w-[980px]` inside `overflow-x-auto`). The shipping row has a 3 px `fire` left border and a 5% `fire` tint. |
| Lead-time bars | plain `div`s (right-aligned to "Fire arrives") | `fire` for Hariq, `chart-5` for the buffer baseline. |
| Goal cards G-1…G-6 | `Card` + `Badge` (PASS = ink fill + check · REPORTED = `flame` outline · PENDING = dashed outline) | |

---

## 9. Map (MapLibre GL JS)

MapLibre paint properties need real colour strings, not CSS variables, so keep these in `src/map/colors.ts`:

```ts
export const mapColors = {
  burningCore: "#9E1016",
  burning: "#E3262B",
  burningEdge: "#F26A21",
  zone1hFill: "rgba(227, 38, 43, 0.22)",
  zone1hLine: "#E3262B",
  zone2hFill: "rgba(242, 106, 33, 0.13)",
  zone2hLine: "#F26A21",
  nextPassLine: "#1C1B1A",
  alertArea: "#1C1B1A",
  land: "#ECE7DD",
  sea: "#D3DFE1",
} as const;
```

| Layer | Type | Paint |
| --- | --- | --- |
| 2 h zone | `fill` + `line` | fill `zone2hFill`; line `zone2hLine`, width 2, `line-dasharray: [4, 3]` |
| 1 h zone | `fill` + `line` | fill `zone1hFill`; line `zone1hLine`, width 2.5, solid |
| Burning cells | `fill` (375 m squares) | `burning`; the core cells `burningCore`; edge cells `burningEdge` |
| Next pass (replay) | `line` | `nextPassLine` at 70% opacity, width 1.5, `line-dasharray: [1, 2]` |
| Alert areas (3 km) | `line` | `alertArea` at 60%, width 1.5, `line-dasharray: [2, 2]` |
| Village pins | HTML markers | white card + status strip + words; dot 14 px with a 3 px white ring |

Draw order: basemap → 2 h → 1 h → burning cells → alert areas → pins. Basemap: OpenFreeMap with a light, low-saturation style, so red and orange zones stay the loudest things on screen. Every map has a legend that shows the **dash pattern and the fill**, not only colour.

---

## 10. Alert receiver (Expo / React Native)

shadcn/ui is web-only. For the phone you have two options:
- **The alert screen itself:** a custom full-screen view built with `StyleSheet` and the same tokens. It's one screen and has to be pixel-exact.
- **Settings and other ordinary screens:** optionally use **React Native Reusables** (a shadcn/ui port for React Native built on NativeWind). It keeps the same component names and theming as the dashboard.

Put the tokens in `apps/mobile/src/theme.ts`:

```ts
export const colors = {
  fire: "#E3262B", flame: "#F26A21", charcoal: "#2B2B2B", ink: "#1C1B1A",
  paper: "#F3F0EA", white: "#FFFFFF", bezel: "#141414",
};
export const screens = {
  leave_now: { bg: colors.fire, fg: colors.white },
  get_ready: { bg: colors.flame, fg: colors.ink },   // black text on orange (contrast 5.6:1)
  cancel:    { bg: colors.charcoal, fg: colors.white },
};
```

Screen anatomy, top to bottom (Framer component "Phone alert"):
1. "EMERGENCY ALERT · CIVIL PROTECTION" + `Siren` icon (mono 10–11 px, uppercase)
2. Language switch, 4 segments: Darija · Taqbaylit · العربية · Français. The active segment is white.
3. Level word: 36–42 px (Arabic 42 px Plex Sans Arabic 700; Latin 30–36 px Archivo 800) + the English code below it in mono
4. Minutes left: 96 px Archivo 800, `tabular-nums`, + unit + village name
5. Direction card: 52 px arrow tile + "Go towards …" + fire distance and direction
6. Message body: 14–15 px, two lines maximum
7. (spacer)
8. "SATELLITE PASS 22 MIN AGO · 14:24 UTC"
9. Dismiss button, full width: stops the sound only. The screen stays.

Behaviour: loud on silent (`expo-audio`, looped) + vibration + `expo-keep-awake`; RTL per block with `writingDirection: 'rtl'` and `textAlign: 'right'`; mirror the order of rows like minutes and direction for RTL; red "Not connected to alert server" banner with backoff 1 → 2 → 5 → 10 s; never render "safe".

---

## 11. Content style

- **Voice:** short, imperative, numbers first. "34 min · leave SW" beats "You have approximately 34 minutes".
- **Formats:** minutes `34 min`; hours `1 h 40 min`; distance `2.1 km` (French UI: `2,1 km`); clock 24 h `14:41`; data age always ends in `UTC` on alert screens; percentages one decimal `96.4%`.
- **Phone numbers:** `1021` is a placeholder (Q-5). Don't ship it without confirmation.
- **Sample data:** any number not read from the API or `scoreboard.json` carries the label "Sample values".
- **Names:** villages show the French name, then the Arabic name (`name_ar`). Kabyle names come in when CO has checked them.

---

## 12. Accessibility checklist

- [ ] Every status shows a word, not just a colour, including map pins and legend swatches (dash pattern differs too).
- [ ] Red and orange text under 19 px uses `fire-text` / `flame-text`.
- [ ] Visible focus ring (`ring-ring`, 3 px) on every interactive element; keyboard order: mode → list → actions → map.
- [ ] `prefers-reduced-motion`: no pulsing pins and no animated zone transitions.
- [ ] Arabic blocks carry `dir="rtl"` and `lang="ar"`; Kabyle blocks carry `lang="kab"`; French blocks carry `lang="fr"`.
- [ ] Toasts are announced (`role="status"`); banners use `role="alert"`.
- [ ] Usable under Chrome DevTools Slow 3G with < 1 MB of compressed JS.

---

## 13. Open items

| # | Item | Owner |
| --- | --- | --- |
| D-1 | Confirm the product name ("Hariq" is a placeholder). | Team |
| D-2 | Reversed logo (white H) for dark surfaces. | UX1 |
| D-3 | Native check of all Darija, Taqbaylit and Arabic strings, plus the missing cells in §7. | CO |
| D-4 | Replace sample scoreboard numbers with `scoreboard.json`. | AI |
| D-5 | Framer: tablet (810) and phone (390) layouts for all four pages are not built yet. | FS |
| D-6 | Check that Plex Sans covers the Kabyle glyphs (ɣ ẓ ḥ ṛ ḍ ε). | FS |
