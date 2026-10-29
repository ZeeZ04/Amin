# D3: Device design spec (beyond iPhone)

Principle: one brand (door mark, teal/sand/saffron), one engine protocol (`Engine`), every device uses its own native idiom. Privacy shows everywhere: a small "On this device" badge, never a cloud icon. Every answer shows its source chip ("From your documents" in saffron, "General knowledge" in grey). Arabic is RTL throughout; layouts mirror.

## Today (MainView.swift)
`NavigationSplitView` (Sidebar: New chat, Chat, Documents, Projects, Settings, Recent) for iPad/Mac/Vision; `PhoneTabs` for iPhone and tvOS. Watch is a single dictation field relaying to the iPhone. Gaps: no inspector, no toolbar commands, no menu-bar window, tvOS reuses phone tabs.

## iPad
- Layout: three columns on regular width. Sidebar 320 pt, chat (min 420 pt), source inspector 340 pt (trailing, `.inspector`, toggled with a toolbar button or ⌘⌥I). Two columns in portrait or Split View; inspector becomes a sheet at compact width.
- Navigation: sidebar sections as now; Recent grouped by Today / Week / Earlier. Tapping a citation chip in an answer opens the inspector at that passage, highlighted, with document title, page, and "Open document".
- Source inspector: tabs Sources (this answer), Document (reader), Memory used. Reader supports select-then-ask.
- Stage Manager / multitasking: resizable window, min 320 x 480 pt; support multiple windows (`WindowGroup` + `openWindow`): "Open chat in new window" from the Recent context menu. Layout switches on size class, never on device idiom. Drag a conversation or document between windows.
- Pencil: in the document reader, circle or underline a passage (PencilKit canvas overlay, `UIPencilInteraction`); on lift, a chip "Ask about this" appears; tap and the recognised text (Vision text recognition, on device) is attached as the quote and the chat opens in the inspector. Squeeze (Pencil Pro) opens the voice ask; double tap toggles the inspector.
- Keyboard: ⌘N new chat, ⌘F search history, ⌘K quick switch, ⌘⏎ send.
- v1: split view, inspector, multi-window, keyboard shortcuts. Later: Pencil circle-to-ask (v1.1), Scribble in the composer (free from the system, verify only).

## Mac
- Window: sidebar 260 pt (min 220) + chat, optional inspector 320 pt; min window 760 x 520. Unified toolbar: sidebar toggle, title, New chat, Model/status pill, Voice, inspector toggle. Search field in the toolbar (⌘F) across conversations and documents.
- Menus: File (New chat ⌘N, Add document ⌘O, Export answer ⇧⌘E), Edit, View (Toggle sidebar ⌥⌘S, inspector ⌥⌘I), Conversation (Regenerate ⌘R, Copy answer ⇧⌘C, Voice mode ⌥⌘V), Window. Settings scene at ⌘, (tabs: General, Models, Voice, Memory, Privacy).
- Quick-ask window: a menu-bar extra (`MenuBarExtra`, door mark) plus a global hotkey, default ⌥Space (user-configurable; warn if it clashes with Spotlight alternates). A floating non-activating panel, 640 pt wide, centred upper third, single field with mic button; answer streams below up to 360 pt tall, citations as chips; ⏎ ask, ⌘⏎ continue in main window, Esc dismiss, ⌘C copy. Registered via `KeyboardShortcuts` (MIT) or Carbon `RegisterEventHotKey` (no permission prompt, preferred). Also reachable by "Hey Amin" when voice is on.
- Drag-and-drop: drop files (PDF, DOCX, TXT, MD, images) on the Documents view, the window, or the Dock icon; drop shows "Add to Amin" target with progress per file and a "Indexed, on this device" confirmation. Drag a citation chip out to get the source file. Folder drop = watched folder (later).
- Dock and Services: "Ask Amin about selection" Services item (v1.1).
- v1: window, toolbar, menus, shortcuts, drag-and-drop, quick-ask hotkey. Later: watched folders, Services, Shortcuts actions beyond the existing intent.

## Vision Pro
- Main window: glass-material window, 1100 x 700 pt default, same sidebar + chat. Sidebar is a leading column; large 17+ pt body text, minimum hit target 60 pt, hover effects on all controls.
- Ornaments: bottom ornament (mic, new chat, documents, sources) so the window body stays clear; trailing ornament shows the source inspector for the selected citation.
- Voice orb volume: a `WindowGroup` with `.windowStyle(.volumetric)`, 0.4 m cube. The orb is the HUD from task 2: idle slow breathing teal, listening reacts to voice level (scale and glow), thinking orbits saffron particles, speaking pulses with TTS amplitude. Citations float as small cards around the orb, gaze-and-pinch to expand to the window. "Hey Amin" starts it; look away for 30 s and it sleeps. Spatial audio: voice anchored at the orb.
- Always keep a passthrough-friendly dim; no full immersion in v1.
- v1: window + bottom ornament. v1.1: orb volume. Later: documents as spatial panels, immersive study space.

## Apple TV
- 10-foot UI: custom, not phone tabs. Top tab bar (Ask, Documents, Projects, Settings), body text minimum 29 pt, titles 48 pt, safe area 90 pt side and 60 pt top, focus scale 1.1 with saffron focus ring. Chat shows only the current exchange, large; history in a side sheet (swipe left).
- Siri Remote: press and hold the mic button to speak (on-device dictation on the Apple TV, or relay to the iPhone/Mac if Amin cannot run on the box); the orb fills the centre while listening. Play/Pause reads the answer aloud. Menu goes back. Typing on a TV is poor, so no keyboard flow except iPhone Continuity keyboard.
- Content: answers as short cards (title 48 pt, body 3 lines, "More" expands), citations as 3 large chips. Ambient idle: slow door-mark animation, dim to avoid burn-in.
- Constraint: tvOS has no persistent local file storage and little RAM, so v1 is a client to the owner's Mac/iPhone over the local network (Bonjour, encrypted); privacy badge reads "Your home network only".
- v1: tabs + Siri Remote voice ask as a client. Later: documents browsing, family profiles.

## Apple Watch
- Home screen: big mic button (full width, 44 pt+ tall) over the door mark; tap and speak (dictation sheet), answer appears as a short card: source tag, then one to three sentences (answer is shortened for the watch, "Continue on iPhone" Handoff for the rest). Keep the text field as fallback, but voice first. Wrist raise to speak (double-tap gesture on Series 9+: opens the mic).
- Reading: answers over 3 lines scroll with the Digital Crown; speak aloud on a button (speaker).
- Complications (WidgetKit, accessory families): circular = door mark launches voice ask; rectangular = last answer's first line plus "Ask"; corner = mark; inline = "Ask Amin". Tapping starts listening immediately via deep link.
- Smart Stack: relevance widget (`RelevanceConfiguration`) shows "Ask Amin" with the next calendar context only if the user has indexed it; no fabricated content. Action Button (Ultra) maps to the voice ask.
- v1: mic-first ask via iPhone relay, circular and rectangular complications. Later: Smart Stack relevance, direct watchOS on-device small answers, Handoff of whole conversations.

## Android (phone and tablet)
- Same brand in Material 3: colour roles derived from the Amin teal (primary), sand (tertiary), saffron (accent for citations); dynamic colour off by default so the brand holds, optional in Settings. Typography: Roboto Flex for Latin, Noto Naskh Arabic, Noto Sans Malayalam. Door mark as adaptive and monochrome themed icon.
- Phone: bottom navigation bar (Chat, Documents, Projects, Settings), 80 dp, large composer with mic, history in a modal drawer, predictive back. Voice orb as a full-screen sheet with the same states.
- Tablet and foldable: Material adaptive layouts (`NavigableListDetailPaneScaffold` / `NavigationSuiteScaffold`): navigation rail at medium width (80 dp), permanent drawer at expanded (360 dp), a supporting pane (360 dp) for sources. Window size classes drive it; support desktop windowing and drag-and-drop of documents into the app.
- Platform integration: share target ("Ask Amin about this"), assistant role later, home-screen widget, quick settings tile.
- Engine: later (task 1 puts Android after Apple); needs a licensed on-device runtime (llama.cpp MIT or LiteRT Apache-2.0, check Gemma terms). Build Compose, not a web wrapper.
- v1: not shipped. Spec only; design tokens exported from the Apple palette so the Android build starts from the same file.

## Home hub (always-on ambient)
- Target: a dedicated tablet or smart display on a stand (iPad in Guided Access / StandBy-like mode, or Android tablet kiosk). Landscape, 10-foot-lite: text minimum 28 pt, tap targets 64 pt.
- Idle: dim, slow-breathing orb and a clock; OLED/burn-in safe (shift position every minute, brightness by ambient light). "Hey Amin" wakes it, the orb grows to fill the screen (JARVIS HUD, task 2), the answer is shown large with citations as cards on the sides, and read aloud. Optional family profiles chosen by voice.
- Privacy: visible mic-state ring (teal idle off, saffron listening), hardware mute honoured, no camera use. Needs a power-connected, local-network Amin host or an on-device engine.
- v1: ship as an iPad mode ("Ambient" toggle in Settings) reusing the orb and wake word. Later: dedicated hardware, multi-room.

## Summary of v1
iPad (split, inspector, windows), Mac (toolbar, menus, quick-ask hotkey, drag-drop), Vision (window + ornaments), TV (voice ask client), Watch (mic-first, complications), iPad ambient mode. Later: Pencil circle-to-ask, orb volume, Android, dedicated hub, Services and watched folders.
