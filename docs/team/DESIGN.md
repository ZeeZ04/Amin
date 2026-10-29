# Amin v1 design direction (Lead Designer)

Tokens: `apple/Sources/Kit/DesignSystem.swift` (D4, resolved). Never hard-code hex, sizes or durations in views; use `Color.amin*`, `Font.amin(_:script:)`, `AminSpace`, `AminRadius`, `AminMotion`, `AminHUD`. Existing `Theme.swift` names (`aminTeal`, `aminTealDeep`, `aminSaffron`, `aminSand`, `DoorMark`) stay for brand art only.

## 1. Principles
1. Trust is shown: every answer states its source, or says "No source in your documents".
2. Calm, sand and teal. System chrome (Liquid Glass) outside, brand inside content. No glass on glass or behind long text.
3. Saffron is rare: orb core, source highlight, dark-mode focus. Never text on light.
4. Three scripts are equal: leading/trailing only, extra leading for Arabic and Malayalam, nothing truncated.
5. Motion informs, then yields to Reduce Motion.

## 2. v1 inventory (priority order)
**iPhone:** 1 Chat + source sheet. 2 Onboarding and model download. 3 Voice. 4 Documents (import, scan). 5 Memory. 6 Settings (Model section). 7 Error banners.
**iPad:** 1 Three-column split with source inspector. 2 Keyboard shortcuts. Same screens as iPhone inside it.
**Mac:** 1 Window, toolbar, inspector. 2 Menus and Settings scene. 3 Drag-and-drop documents. 4 Quick-ask panel (⌥Space).
**Voice HUD:** 1 Phone/iPad-portrait orb. 2 Mac fullscreen ambient layout. Cut: iPad ambient mode.
**Deferred:** Vision, TV, Watch beyond current, Android, Pencil, multi-window, orb volume, Services, particles, side panels other than Time and Source.

## 3. Per screen
| Screen | Components | Key values | Detail |
|---|---|---|---|
| Chat | Answer card, Citation chip, Composer, Empty state | card 16 radius, 16 pad; composer 22 radius, line-strong, grows to 6 lines; user bubble `aminAccent`/`aminOnAccent`; answer `aminAnswer` plus `aminLineHeight` | D1 §2; D4 §6 |
| Source sheet | Source panel | detents medium/large; passage in `aminSurface`, highlight `aminGold` 25% | D1 §2 |
| Onboarding | DoorMark 96, primary button, Empty state | 4 pages, bg `aminBg`, CTA `aminAccent`; Skip never on page 2 | D1 §1 |
| Voice (phone) | Voice orb button | orb 220 (`AminHUD.orbPhone`), bg `AminHUD.bg*`, End 56 tall | D1 §3, D2 |
| Documents | Empty state, list row | file icon 36, status icon plus text, delete confirm | D1 §4 |
| Memory | Memory row | 2 lines, "Only on this device", swipe Forget, Undo 6 s | D1 §5 |
| Settings | grouped list | Model first, Privacy states "No account. No analytics." | D1 §6 |
| Errors | inline banner | glass capsule, 5 s, VoiceOver keeps | D1 §7 |
| iPad | split view, Source panel as `.inspector` | sidebar 320, chat min 420, inspector 340; sheet at compact | D3 iPad |
| Mac | toolbar, menus, Quick-ask | sidebar 260, inspector 320, min 760x520; panel 640 wide | D3 Mac |
| HUD | Voice orb button (HUD form), HUD chip | `AminHUD` colours; 6 layers; states per D2 table; transcript 22/28 pt | D2 |

## 4. Resolved disagreements
- Card radius: D1 20, D4 16 wins (`AminRadius.lg`). HUD panels 20 become 16.
- Dark teal text: D1 "aminTealLight" dropped; use `aminAccentInk`. Teal fills use `aminAccent`, not raw `aminTeal`, so dark passes 4.5:1.
- Citation chip: D1 capsule, D3 saffron, D4 8-radius accent wash. D4 wins in chat; saffron only on the highlight. HUD chips stay pill with `AminHUD.chipFill`.
- Line height: D1 `lineSpacing(4/6/6)` replaced by `aminLineHeight(script)` (0/12%/22%).
- Motion: D1 `.smooth(0.35)`/`.snappy(0.25)` and D2 280 ms lose to `AminMotion` (spring 0.35/0.85; 150/250/400 ms). Orb alone uses `bouncy`. HUD state change 250 ms, interrupt 150 ms. Idle breathe 4.0 s.
- Icons: `mic.fill`, `lock.shield` per D4 §4. "Memory" is the screen name; "Teach Amin" is its header only.
- Inspector widths stay native (340 iPad, 320 Mac); 400 is web only.
- Malayalam: body 17 floor (D1) and nothing under 13 (D4); lineLimit 2 on chips.
- Screen background `aminBg`; `aminSand` only in illustrations.
- D2's FFT 16-band ring is cut: one smoothed level (alpha 0.35, `(db+50)/40`).

## 5. Acceptance checklist (simulator)
- [ ] Dynamic Type XXL and AX5: no truncated answers, chips wrap, composer grows, tab labels stay, HUD captions scale.
- [ ] Dark mode and Increase Contrast: all text from role colours, no raw hex outside `AminHUD`; focus ring teal light, saffron dark.
- [ ] RTL Arabic: layouts mirror, chevrons flip, orb, waveform and clock do not; filenames and `[1]` stay LTR (FSI/PDI); no letter-spacing.
- [ ] Malayalam: Noto Sans Malayalam loads (`UIAppFonts`), conjuncts not clipped, 22% extra leading, no text under 13 pt.
- [ ] Reduced Motion: springs become 150 ms fades; orb is static ring with level bar, scale within ±5%; no rotation.
- [ ] VoiceOver: answer reads text then sources; label chip read aloud; orb "Amin, listening" announced on state change only; DoorMark hidden; "Answer ready" posted.
- [ ] Orb holds 60 fps on a device (30 fps idle), one `Canvas`, transform/opacity only; Instruments shows no dropped frames over a 2 minute conversation, Low Power Mode pauses it.
- [ ] Touch targets at least 44; no colour-only state.
