# D5 — In-app refresh: from bland to "the majlis"

Research only. Status: proposal for the lead engineer. Builds on DESIGN.md and D1–D4; changes token *values* and screen composition, not the token *names* (so web `app.css` can mirror it).

## 1. What I looked at
- Read: DESIGN.md, D1, D4, `DesignSystem.swift`, `Theme.swift`, ChatView, MainView, SettingsView, OnboardingView, ConnectView (VoiceView, AmbientView, MajlisOrb only skimmed; the orb is the one screen the owner did not call bland).
- Built the iOS app (scheme Amin, iPhone 17 Pro, iOS 26.5, builds clean) and screenshotted the first screen (ConnectView). Chat, Settings, Documents sit behind sign-in or a model folder, which the simulator has no server/model for, so those were diagnosed from code, not pixels. Screenshots of those are the first thing to capture once a server runs.

## 2. Diagnosis

**Root cause: the design system exists but the app does not use it.** Token usage counts in `apple/Sources/App`: ChatView 0, MainView 0, SettingsView 0, ConnectView 0, MajlisOrb 0; only Onboarding (10), Ambient (8), QuickAsk (7), Voice (3). Chat, sidebar, settings and sign-in are stock SwiftUI (`.largeTitle.bold()`, `.secondary`, `.background.secondary`, `Form`, `List`) with a teal tint on top. The result is "default iOS, in green". D4's `aminBg`, `aminSurface`, `aminAccentWash`, `AminRadius` never reach the screen the owner sees most.

| Area | Observation (file) | Why it reads bland |
|---|---|---|
| Colour | Backgrounds are system white/grouped grey; teal appears only on the send arrow, labels and a 12% bubble tint (ChatView). Sand `#F3EFE4` is defined but only used in the orb. Saffron is a 1-pixel superscript number. | Palette is 90% neutral. The two brand colours that make Amin distinctive carry no area. |
| Hierarchy | Welcome: door mark 44 pt, `largeTitle.bold` greeting, grey paragraph, three identical grey cards. Answer: grey caption label, body, chips. Everything is one weight and one grey. | No focal point; the trust signal ("From your documents · 2 sources") is a 12 pt caption, the product's whole promise shown smaller than the timestamp. |
| Typography | SF everywhere via `.font(.body)`; `Font.amin` and Malayalam face unused in Chat. One voice for UI and answers. Bold-only emphasis. | No personality, no distinction between "Amin speaking" and chrome. Malayalam uses system fallback in chat, so the extra-leading rule is not applied. |
| Empty state | Greeting + generic paragraph + 3 grey cards + lock footnote (ChatView `Welcome`). Left-aligned in a 760 pt column; on iPhone it is a text list. | No brand moment, no sense of place; the door mark is tiny and static. Starters have no icon, colour or document-awareness (always the same 3 questions). |
| Answer card | No card: plain text beside a 30 pt dark-teal door tile. Assistant avatar repeats every turn. | Repeated avatar is noise; no surface means the cited-answer, general-answer and refusal states look alike apart from a tiny icon. |
| Citations | Chip = saffron 30% square with number + grey `.background.secondary` pill, `lineCap` 1 line. | Chips look like system tags; no document-type icon, no snippet; the saffron number on pale saffron has weak contrast (gold is "never text on light", D4). |
| Composer | `.regularMaterial` capsule-ish box, mic grey, send is a 32 pt SF circle. | Reasonable, but grey-on-grey; nothing signals "private/on-device" or current source/space; mic (Amin's differentiator) is the weakest control. |
| Sidebar/tabs | Stock `List` with 4 SF symbols; iPhone `TabView` with generic chat-bubble icon; "Recent" is plain rows. | Zero brand; no grouping by day, no pinned spaces, no active-space colour. |
| Settings | One long `Form`, ~10 sections, flat. | Admin invite, memory, model, packs, device all same weight. Density without structure; no status summary at top. |
| Onboarding | Centred SF symbol (`cpu`, `mic.fill`) at 56 pt light, body copy, dots. Door mark only on page 1. | Generic "permissions wizard". The Majlis Orb (best asset) is absent. |
| Sign-in | Door mark 72 pt, bold title, grey blurb, white fields on `aminTealDeep` at 4% (looks grey), disabled grey pill button. Screenshot confirms: logo is small, whole screen is white/grey, first view of the brand is a form. | No welcome, no teal, nothing says "trust". |
| Motion | `.snappy` scroll, spring on onboarding pages. No streaming-text animation, no state change on citations, no haptics. Orb motion is rich but isolated to Voice/Ambient. | App is static between orb sessions; answers pop in as text blocks. |
| Materials | `.regularMaterial` on composer only. iOS 26 Liquid Glass comes free from system bars but no custom surface uses it deliberately. | Flat; no depth hierarchy between content and controls. |
| Iconography | SF Symbols at default weight, mixed `.fill`/outline (`lock`, `doc.text`, `shield`, `brain`). | Pleasant but anonymous. One custom icon family (door, keyhole, lantern, arch) is missing beyond the logo. |

## 3. What leading apps do (patterns to borrow, not copy)

| Source | Pattern | Take for Amin |
|---|---|---|
| Claude app (warm cream canvas, coral accent, serif display; third-party spec summaries [shadcn](https://www.shadcn.io/design/claude/raw), [kombai](https://kombai.com/examples/design-systems/claude-kombai); unofficial, unverified) | Warm paper background and a *serif* for the assistant's voice makes answers feel authored, not "system output". | Sand paper canvas; a serif for answers and greeting. |
| Perplexity ([teardown](https://www.925studios.co/blog/perplexity-design-breakdown), [AI design patterns](https://ai-design-patterns.pages.dev/teardowns/perplexity/how-output-and-refinement-work)) | Numbered markers inline; three layers: inline marker, source row, detail preview; source cards with title and snippet. | Citations as a visible "sources strip" with doc icon + snippet, the product's hero element. |
| ChatGPT / Gemini | Large friendly greeting, suggestion chips with icons, generous empty space, voice as a first-class composer button; Gemini uses colour gradients as identity. | Greeting with brand art; voice button prominent. |
| Apple Liquid Glass (HIG Materials updated Jun 2025: [Materials](https://developer.apple.com/design/human-interface-guidelines/materials), [overview](https://developer.apple.com/documentation/technologyoverviews/liquid-glass); secondary summary [Firefox/Acorn](https://acorn.firefox.com/latest/mobile/patterns/i-os-26-and-liquid-glass-w2oH48nk)) | Glass is for the *functional layer* (bars, floating controls); content stays opaque and legible; avoid glass on glass. I could not read the HIG text directly, so confirm in the HIG before shipping. | Composer, tab bar, floating buttons = glass; answers, sources = opaque sand/ink. Already DESIGN.md principle 2. |
| Things / Linear / Arc | One strong accent, refined neutrals, tiny delight (completion animation, hover, spring), consistent iconography, tinted sidebar, space colour-coding. | Spaces get colours; saffron micro-delights; tinted sidebar. |
| Cultural: Emirati door/majlis (project brief), mashrabiya and geometric arches, Naskh/Kufic type pairing ([Ubuntu Arabic UI font note: Kufic-based for UI, Naskh for text](https://canonical.com/blog/hebrew-and-arabic-on-track)) | Warm lamplight, carved lattice, arch and keyhole silhouettes, deep teal doors with brass studs, sand walls. Search for Malayalam/mashrabiya references returned nothing usable; direction below is design judgement, not sourced. | Arch + stud lattice as a quiet pattern; lantern glow as the single "alive" light. |

## 4. Options

| | A. Warm Paper | B. Lantern Majlis (recommended) | C. Glass Night |
|---|---|---|---|
| Mood | Calm, editorial, a trusted document you read. Cream paper, serif answers, near-no ornament. | Evening majlis: sand walls, deep teal door panels, a saffron lantern glow that appears when Amin is thinking or has found a source. Warm, dignified, distinctive. | Dark teal glass, glow, JARVIS-like everywhere; consistent with the orb. |
| Strengths | Lowest cost, great reading, accessible. | Uses both brand colours, makes the door/arch the identity, fits Arabic/Malayalam, still legible. | Dramatic, matches HUD. |
| Risks | Can read as "Claude clone" (cream + serif). | More work (patterns, new components); must keep ornament quiet. | Contrast/readability on long text, battery, fights "no glass behind long text" and Liquid Glass guidance; weak for daytime and Malayalam. |
| Effort | S | M | L |

Recommendation: **B**, built on A's reading surface (sand paper, serif answers) with C's drama reserved for the orb and thinking moments.

## 5. Recommended token changes (names unchanged unless "new")

**Colour** (light / dark; all text pairs ≥4.5:1, non-text ≥3:1; check with Increase Contrast variants, keep existing `lHC/dHC`)

| Token | Old → New light | Old → New dark | Note |
|---|---|---|---|
| aminBg | `F7F8F6` → `F6F1E7` (warm sand paper) | `0D1615` → `0B1716` | main canvas |
| aminSurface | `FFFFFF` → `FFFCF5` | `131E1D` → `122120` | answer card, sheets |
| aminRaised | `FFFFFF` → `FFFFFF` | `182524` → `1A2B2A` | composer, popovers |
| aminSidebar | `EFF2F0` → `EAE3D2` | `0F1A19` → `082B29` | tinted sidebar, ink on it ≥ 7:1 |
| aminInk | `142826` → `1B2B29` | `E5EDEB` → `F1EBDD` (warm) | |
| aminMuted | `5F706D` → `5E6B66` | `8FA19E` → `9FB0AB` | |
| aminLine | `E0E6E3` → `DDD4BF` | `22312F` → `243634` | warm hairlines |
| aminAccent (fill) | `0E5E5A` (keep) | `1F7A72` → `2A8C84` | brighter dark fill |
| **aminLantern** (new) | `E3A72F` fill, `8A5A00` as text on light (6.0:1 on aminBg) | `F2B94B` | glow, source highlight, active citation; text only via the dark variant |
| **aminDoor** (new) | `0A3F3C` panels with sand text | `0E5E5A` | hero panels, welcome, onboarding, user bubble |
| **aminWashGold** (new) | `F7E7BF` | `3A2D12` | cited passage background |
| aminAccentWash | `E3EFEC` → `DCEBE6` | keep | |

Rule: surfaces never pure white or neutral grey; at least one *area* of aminDoor or lantern per screen.

**Type** (add `Font.aminDisplay`, `Font.aminAnswer` replaced)

| Role | Latin | Arabic | Malayalam | Size/leading |
|---|---|---|---|---|
| Display (greeting, titles) | New York serif (`.system(design: .serif)`), semibold | SF Arabic, bold (system) | Noto Serif Malayalam (bundle; else Noto Sans, bold) | 34 / 1.15; Arabic 1.35; Malayalam 1.5 |
| Answer | New York serif, regular | SF Arabic regular (Naskh-like, readable) | Noto Sans Malayalam regular | 18 / 1.5; Arabic 1.65; Malayalam 1.75 (keeps D4 `extraLeading` .12/.22 at least) |
| UI (chrome) | SF Pro, `.rounded` for chips and labels | system | Noto Sans Malayalam | existing scale |
| Trust label | SF Pro semibold small-caps feel, 13 pt, tracking +0.2 | system | Noto Sans | 13 (up from 12 caption) |

Answer measure ≤ 46 em; all text uses Dynamic Type; nothing `.lineLimit(1)` on answers/chips without `fixedSize` or wrap-on-expand.

**Radius / space:** sm 8 → 10, md 12 → 14, lg 16 → 20 (cards), xl 22 → 28 (composer, sheets); add `AminRadius.arch = 999 top corners` (door-arch shape for hero panels and avatars). Spacing grid unchanged; answer card padding 20, between turns 28.

**Materials:** opaque sand/ink for content. Glass (`glassEffect`, iOS 26; `.ultraThinMaterial` fallback) only on composer, floating "scroll to bottom", tab bar/toolbars (system), voice button. One shadow style: `y:6 blur:18 aminDoor 10%`. Door-panel hero: `aminDoor` fill + 4% sand stud-lattice pattern (Canvas, ≤ 60 dots, static) + inner top highlight 1 pt sand 12%.

**Motion** (all with `AminMotion.adaptive`; Reduce Motion → 150 ms fades, no glow pulse)

| Moment | Spec |
|---|---|
| Streaming answer | words fade in 120 ms, 12 ms stagger per word, no layout jump; one soft haptic at first token and "rigid" at completion |
| Thinking | lantern dot (12 pt, saffron) breathes 1.6 s; replaces ProgressView "Reading…" |
| Citation found | chip slides in 250 ms, number badge fills saffron then settles; source row staggered 60 ms |
| Source open | matched-geometry from chip to sheet (`.spring(0.35, 0.85)`) |
| Welcome | lantern glow fades in 600 ms, door mark draws on (stroke 700 ms), once per launch |
| Send | arrow → lantern flick 150 ms |
| Orb | unchanged (60 fps budget; no new full-screen blur layers elsewhere) |

**Iconography:** keep SF Symbols for system actions; custom set (door, arch, lantern, keyhole, stud lattice, source-doc) 24 pt, 1.75 pt stroke, rounded caps, drawn from DoorMark geometry, for: tabs, citation, trust label, empty states. SF symbols use `.hierarchical` rendering with aminAccentInk.

## 6. Per-screen spec (option B)

| Screen | Change |
|---|---|
| **Chat empty state** | Replace text list with hero: `aminDoor` arch panel (≈ 220×140) behind a 72 pt DoorMark with lantern glow; greeting in serif display ("Good evening, Abdul." / Arabic / Malayalam by app language); one-line promise in muted. Below: 3 starter cards in 2×N grid, 20 radius, each with a custom icon, colour-coded by kind (document = teal wash, general = sand, memory = gold wash), questions generated from the user's actual documents when any (fallback: current trilingual three). Lock line becomes a pill "On this device · nothing leaves it" with lock icon. |
| **Answer card** | Surface `aminSurface`, radius 20, padding 20, 1 pt aminLine, no avatar per turn (door badge only on first answer of a session). Header = **trust bar** (full-width row, 13 pt semibold, 36 pt tall): teal wash + doc icon "From your documents · 2 sources"; lantern-wash + lantern icon for conflicts "Your documents disagree"; sand + globe for general; danger wash for errors. Answer text serif 18/1.5. Inline citation = superscript pill 16 pt, `aminWashGold` fill, `8A5A00` number (≥4.5:1). Footer: share, copy, latency 12 pt muted, aligned trailing in the user's language direction. Cited sentences gain a 2 pt lantern leading rule while their chip is pressed. |
| **Citations / sources** | Replace chips with a **sources strip** under the answer: horizontal cards 200×64, doc-type icon, file name (wraps to 2 lines, never 1-line truncation), heading, 1-line passage preview; number badge top-leading. Tap → source sheet; passage on `aminWashGold` with a leading lantern bar and the matched sentence bolded. 44 pt min target. |
| **User bubble** | Fill `aminDoor`, text sand (≥ 7:1), radius 22 with 6 pt tail corner on the trailing side (mirrors in RTL). |
| **Composer** | Glass capsule radius 28, min height 52, "Message Amin" placeholder plus current space as small leading chip (tap to change; replaces toolbar menu on iPhone). Mic becomes a 44 pt circle in `aminAccentWash` with teal icon (primary Amin action); Send is lantern-filled circle (`aminOnGold` arrow) when enabled, muted when empty. Focus ring `aminFocus` 2 pt. Offline/on-device indicator: small dot at the trailing edge of the chip. |
| **Sidebar (iPad/Mac)** | `aminSidebar` fill; wordmark + DoorMark header; "New chat" as filled teal button; spaces (projects) listed with colour dot + icon, active one has lantern leading bar; recents grouped Today / Yesterday / Earlier with 2-line titles (no truncation of meaning, expand on hover); footer: user avatar + connection state ("This device" / "Amin computer"). iPhone tab bar: custom icons, selected = aminAccentInk with lantern dot. |
| **Settings** | Top status card in `aminDoor`: avatar, name, role, and three live chips (Model ready · Documents n · Memory n). Then grouped sections as cards with icon headers (Account, Memory, Model & packs, Voice, Devices, About), collapsed by default for admin/advanced; destructive items in a separate bottom group. Use `aminSurface` rows on `aminBg` (no grey grouped list). |
| **Onboarding** | Four pages become a fixed `aminDoor` top 45% with the Majlis Orb (low-power idle, static under Reduce Motion) that changes state per page: promise (door opens, 700 ms), model (orb "fills" with download progress ring), mic (listening ring), ready (lantern glow). Bottom sheet in sand with title (serif), 2-line body, primary button lantern-on-ink, progress arch dots. Trilingual language switch top corner on page 1. |
| **Sign-in / Connect** | Top hero arch panel `aminDoor` with DoorMark 96 pt and "Welcome home / مرحباً / സ്വാഗതം" cycling every 4 s (static under Reduce Motion); form card on sand, fields `aminSurface` + `aminLineStrong` border, 52 pt tall, radius 14; primary button full-width aminAccent, disabled state shows hint ("Enter your Amin computer address") not a blank grey pill; "run on this device only" as a secondary card with chip icon, not a heading section. |
| **Documents / Memory** | Empty states use door-arch illustration and a one-line call to action; document rows get file-type icon tile + "cited n times" metadata (reinforces trust). |
| **Voice / Ambient** | Keep. Only align palette tokens (`AminHUD` unchanged) and make the entry mic in composer the same lantern gold as the orb core. |

## 7. Plan for engineering (order)
1. Token values + new tokens in `DesignSystem.swift`, mirror to `amin/web/app.css`; add `Font.aminDisplay/aminAnswer(script:)` helper that picks face by script (detect via existing unicode check in ChatView).
2. Migrate ChatView, MainView, SettingsView, ConnectView to tokens (the biggest single win; do before any new art).
3. Trust bar, answer card, sources strip, composer.
4. Welcome hero, onboarding orb, sign-in hero, sidebar.
5. Motion and haptics; icon set; pattern.

## 8. Acceptance checklist (unchanged, applied to this refresh)
- [ ] No text truncated at the largest Dynamic Type or in 3 languages (chips and sidebar titles wrap/expand).
- [ ] Full RTL mirror (leading/trailing only; bubble tails, accents bars, composer chips, sources strip scroll origin).
- [ ] Malayalam face and line height ≥ 1.75 in answers; Arabic ≥ 1.65; no clipped ascenders/stacked conjuncts in chips.
- [ ] Reduce Motion: no pulse, no draw-on, no cycling headline; 150 ms fades only.
- [ ] Orb ≥ 60 fps on iPhone 12; no extra full-screen blur or glass layers on Voice.
- [ ] Contrast ≥ 4.5:1 for text (verify new lantern text `8A5A00`, sand-on-door, muted on sand), ≥ 3:1 non-text, also in Increase Contrast.
- [ ] Glass only on controls; never behind long text.

## 9. Open questions
- Serif choice: New York (system, free) vs bundling a Malayalam serif. Recommend New York + Noto Sans Malayalam first, test Malayalam serif later.
- Screens not seen live (chat, settings): re-check this diagnosis with screenshots once a server or model folder is available.
