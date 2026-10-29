# D2: Live talking assistant HUD ("Majlis Orb")

**Identity (original, not Marvel):** no cold blue, no hexagon grid. The orb is a *lantern*: saffron core inside teal rings, ticks like a Hijri/astrolabe dial (60 ticks, 12 long = hours of the day), with muqarnas-style 8-point rosette ring as a quiet pattern. Room is deep teal, never black.

## Colours
- bg: radial #0A3F3C centre to #062E2C edge, +#031A19 vignette at 60% opacity
- ring/ticks idle: sand #F3EFE4 at 18%; active: sand 70%
- core (listening): saffron #E3A72F, glow #FFE7AE; speaking: teal-light #8FD3C9 / #2A8C84 (matches web orb); thinking: saffron to teal sweep; interrupted flash: #FFE7AE
- text: #F3EFE4 answer, #BFD6D2 secondary, #9FC1BB tertiary

## Orb (stage size: 38% of short side; phone 220 pt; TV 520 pt at 1080p). Layers, back to front
1. Halo: radial gradient, radius 1.6R, blur 40.
2. Core disc R=0.42 of stage, radial gradient (centre 40/35%).
3. Rings: 3 thin circles at 0.62R/0.74R/0.86R, 1.5 pt stroke (TV 2.5).
4. Tick dial at 0.94R: 60 ticks, short 6 pt/long 14 pt, 1.5 pt wide, rotates.
5. Particles: 48 motes (TV 120), 2 pt, sand 40%.
6. Waveform ring: 96 radial bars at 0.5R, length = level.

| State | Core | Rings | Ticks | Wave/particles |
|---|---|---|---|---|
| idle (wake armed) | saffron at 35% sat, scale 0.8, breathe 4.0 s ±3% | static 18% | rotate 1 rev/120 s | motes drift 4 pt/s, no wave |
| listening | saffron, scale 0.82+0.3*level (smoothed 80 ms) | ring 1 expands with level, ring 2/3 lag 120/240 ms | rev 40 s; ticks within the 90° arc at top light up to 100% as level peaks | 96-bar ring driven by 16-band FFT, mirrored; motes pulled inward 8% |
| thinking | breathe 1.4 s 0.92-1.0 | one ring "scans" 360° in 1.6 s (angular gradient, saffron head) | rev 12 s, clockwise (RTL: same; spin is not directional text) | motes orbit at 0.7R, speed x2 |
| speaking | teal-light, scale 0.9+0.2*TTS-amplitude | rings ripple outward every 700 ms, fade 900 ms | rev 60 s | wave ring in teal, word-onset pulse |
| interrupted | flash #FFE7AE 120 ms, snap to listening | rings collapse to 0.6R in 160 ms (ease-in) | pause 200 ms | motes burst inward; haptic .rigid (iOS) |

Transitions: 280 ms `easeInOut`; interrupt 120-160 ms. Level mapping reuses `(db+50)/40` from VoiceSession.

## Layout
- **Ambient (Mac/TV, 16:9):** orb centre-left at 40% x. Right column (36% width): transcript. Panels in the four corners, 32 pt margin (TV 64 pt).
- **Phone/iPad portrait:** orb top third (centre y 30%), transcript below, one panel row. iPad landscape = ambient layout with two panels.
- **Transcript:** "You" line 22 pt (TV 40) #BFD6D2, live words fade in 120 ms, partial words 60% opacity until final. Answer 28 pt (TV 52) sand, line height 1.35, max 3 lines visible, older lines fade to 30% and scroll up. Speaker label 12 pt caps tracking 1.2, saffron.
- Karaoke highlight: spoken word full sand, upcoming 55%.

## Citations during voice
Never read URLs aloud; spoken: "from your Biology notes, page 4". On screen: chip under the answer, 14 pt (TV 26), pill r=999, #0E5E5A fill, saffron 1 pt border, doc icon + short name + page. Chip appears at the sentence's end, slide-up 8 pt/200 ms; tap/focus opens source. Active chip glows while its sentence is spoken. Uncited general answers show a sand outline "General knowledge" chip.

## Wake indicator ("Hey Amin")
Idle: 8 pt saffron dot at bottom centre beside text "Say 'Hey Amin'" (Arabic: "قل: يا أمين"), dot pulses 1.6 s. On detect: dot becomes a 3-ring ripple from the orb, 400 ms, soft chime (local), core jumps to listening. Mic-off state: dot hollow, strikethrough mic icon. "On device" lock icon always visible, top-left (privacy is the product).

## Side panels (ambient only; hidden on phone except time)
Glass: #F3EFE4 at 6% fill, 1 pt border sand 12%, r=20, blur 20, 260x120 pt (TV 480x220).
- **Time:** 56 pt (TV 120) light, tabular digits; date and Hijri date 14 pt.
- **Source now:** current citation doc, pages, "Local index, 1,204 passages"; or "Amin (on device)".
- **Memory:** "Remembered for Aisha: 3 things" with last 2 as one-line; edit link. Deletable; nothing is shown from other people.
- **Model:** edge-2 / latency of last turn (e.g. 0.9 s), debug-hidden by default.
Dim all panels to 40% after 20 s idle; burn-in: panel offset drifts 2 pt every 5 min (TV).

## Accessibility
- Reduced motion: no rotation, no particles, no scan; state shown by core colour + ring thickness + level-driven scale limited to ±5%; crossfade 150 ms.
- Captions are always on by default in HUD (transcript is captions); size slider 100-200%; contrast >= 7:1 (sand on #0A3F3C = about 11:1).
- VoiceOver: orb is a button "Amin, listening", value updates on state change only (not on level); announce answer via `.accessibilityNotification`; double-tap interrupts. Dynamic Type honoured. Haptics for state changes. Hearing: visual chime flash. Switch Control: orb tap = talk/interrupt.

## RTL
Mirror layout via `layoutDirection`: transcript column moves left of the orb, panels swap corners, chips and karaoke run right-to-left, "Hey Amin" label right-aligned. Orb, rings, waveform and clock digits are not mirrored. Arabic font: SF Arabic/Noto Naskh 1.15x size, line height 1.5; Malayalam needs line height 1.6. Mixed text: wrap with `.environment(\.layoutDirection)` per paragraph, isolate doc names with Unicode FSI/PDI.

## SwiftUI notes
- One `TimelineView(.animation(minimumInterval: 1/60, paused: reduceMotion && state==.idle))` wrapping a single `Canvas`; draw all layers in `context` using `t` and `level`; no per-layer views. Ticks and bars in loops with `context.rotate`/`translateBy` (cheap).
- Glow: `context.addFilter(.blur(radius: 24))` on a copy of the core layer, then `.blendMode(.plusLighter)`; or one Metal `[[stitchable]]` `colorEffect` shader for the core gradient + noise shimmer (iOS 17/macOS 14). TV: gate blur at 1080p.
- Particles: array of structs in `@State`, advanced by `t` delta; cap 48 phone/120 TV.
- Smoothing: `level` through a one-pole filter (alpha 0.35) before drawing; FFT from `AVAudioEngine` tap, 1024 samples, `Accelerate.vDSP`. Replaces the AVAudioRecorder 60 ms metering for waveform; TTS amplitude from `AVSpeechSynthesizer.write` buffers.
- State machine = existing `VoiceSession.State` plus `.interrupted`. Springs: `.smooth(duration: 0.28)`.
- Budget: <= 6% GPU on M-series, 30 fps when idle and ambient (`minimumInterval: 1/30`). tvOS: no focus needed; Siri Remote click = interrupt. Web parity: same layers in `<canvas>` for `amin/web`.
- Always-on: `UIApplication.isIdleTimerDisabled = true`, optional night mode (orb 40% brightness 22:00-06:00).
