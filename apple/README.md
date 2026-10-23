# Amin for Apple platforms

One SwiftUI app for **iPhone, iPad, Mac, Vision Pro and Apple TV**, plus an
**Apple Watch** app that asks through the paired iPhone.

```bash
cd apple && xcodegen && open Amin.xcodeproj
```

Set your team in `project.yml` (`DEVELOPMENT_TEAM`) to run the apps on a
device. The simulators need no team.

## How it connects

Today the app talks to an Amin server on your home network: `make serve` on
the Mac, then enter the address it prints, such as `192.168.1.20:8000`. Every
answer, citation, document and conversation stays on that computer.

The app reaches answers through the `Engine` protocol (`Sources/Kit/AminClient.swift`).
The on-device engine plugs in behind the same protocol once it passes its
gate: Gemma 4 E4B, 4-bit, through MLX Swift (ADR-014). That will let the app
run with no server at all.

## What each platform gets

| | chat + citations | documents | voice | hands-free |
|---|---|---|---|---|
| iPhone, iPad | yes; sources open in an inspector | Files, plus the document camera (scanned to PDF, OCR'd by Amin) | voice mode | "Hey Siri, ask Amin" |
| Mac | yes, with ⌘N for a new chat | Finder | voice mode | "Hey Siri, ask Amin" |
| Vision Pro | yes | Files | voice mode | Siri |
| Apple TV | yes, with Siri Remote dictation | read-only list | — | — |
| Apple Watch | dictated questions, answered through the iPhone | — | — | Siri |

iPhone and Apple Watch allow no third-party background wake word, so
hands-free there is the Siri shortcut. The "Hey Amin" wake word lives in the
web app and on always-on devices (E37).

## Layout

```
project.yml          XcodeGen spec; Amin.xcodeproj is generated, not committed
Sources/Kit/         shared: models, API client and Engine, brand, Watch relay
Sources/App/         the SwiftUI app (every platform except watchOS)
Sources/Watch/       the watchOS app
Resources/           asset catalog: app icon rendered from amin/web/icon.svg
```

Not done yet: layered icons for Apple TV and Vision Pro, project permissions
and sharing (they're in the web app for now), and the on-device engine.
