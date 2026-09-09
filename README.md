# chiikaAir

Gesture-controlled webcam overlay for Windows: grab and drag virtual objects,
capture and browse screenshots, and create draggable, linkable text/code
blocks -- all with your bare hands (and, experimentally, your mouth) in front
of a webcam. No mouse, no keyboard for navigation.

This is the kind of "manipulate virtual objects with your webcam" effect you
see in short-form computer-vision demos, built up step by step from a plain
hand-tracking loop into a small floating desktop widget with its own
mini gesture language.

## Relation to the Chiika ecosystem

`chiikaAir` is a sibling project to [`chiikaScreen`](../chiikaScreen) (a local
screen-vision assistant backed by a small VLM): both are local, offline,
perception-driven overlay agents, just with a different input modality --
screen+vision there, hand/face gestures here. There is no integration layer
between the two yet (none of the Chiika repos expose a plugin/IPC system as
of this writing), but the intent is for gesture events produced here (pinch,
fist, spread, circle-link, mouth-"O") to eventually become an input adapter
for a future `chiikaAgent` orchestration layer, alongside chiikaScreen's
screen-vision input.

## Features

- **`pinch_drag.py`** -- the original proof of concept: pinch thumb+index to
  grab and drag a virtual circle.
- **`screenshot_gallery.py`** -- the main app. A borderless, always-on-top
  webcam window pinned to a screen corner:
  - **Screenshots**: hold a closed fist ~0.4s to capture the screen; the
    shot is added to a gallery (max 4, FIFO -- oldest drops off). Point at a
    thumbnail to select it, spread thumb+index apart to view it fullscreen,
    pinch to return.
  - **Blocks**: hover the `+` button to create a text block, or `<>` for a
    code block (dark background). Max 4 blocks. Pinch-drag to move them,
    drag onto the trash button (bottom-right, held briefly) to delete.
  - **Linking**: trace a circle in the air over a block, then point at a
    second block to link them. Linked blocks are always shown connected by
    an arrow in the corner view; while a linked block is zoomed, the same
    arrow lets you jump straight to the linked block (chainable).
  - **Text & code**: a zoomed block accepts typed text directly. On a code
    block, a held fist runs the code (Python `exec`, output shown inline).
- **`mouth_launcher.py`** -- experimental: shape your mouth into an "O" to
  launch Excel; do it again once Excel is open to bring up Windows' Task
  View instead of relaunching it.

## Architecture

| Module | Responsibility |
|---|---|
| `hand_tracker.py` | Wraps MediaPipe's `HandLandmarker` (Tasks API). Returns 21 hand landmarks in pixel coordinates per detected hand, plus `Hand.is_fist()` (finger-curl geometry: each fingertip closer to the wrist than its own PIP joint). |
| `face_tracker.py` | Wraps MediaPipe's `FaceLandmarker` with blendshapes enabled. Returns a `{blendshape_name: score}` dict per frame (e.g. `mouthFunnel` for an "O" shape). |
| `hold_timer.py` | `HoldTimer`: wall-clock-based "how long has this condition stayed true" tracker, used for every hold-to-trigger gesture (fist-to-capture, hover-to-select, spread-to-fullscreen, pinch-to-return, drag-to-trash, fist-to-run). Wall-clock, not frame-count, so timing doesn't drift with the webcam's actual FPS. |
| `overlay_window.py` | Turns a plain OpenCV window into a borderless, always-on-top panel via `pywin32` (Win32 window handle lookup + style/position editing) -- OpenCV's own window API has no concept of either. |
| `circle_gesture.py` | `CircleDetector`: heuristic recognizer for a circle traced by a fingertip (rolling trail of recent points, checks the swept angle around its centroid and that it closes back near its start). Used to initiate a block link. |
| `blocks.py` | `BlockManager`: block creation/deletion/dragging/linking and all block rendering (corner view + fullscreen view), including the rounded-rect drawing helper OpenCV doesn't provide natively. |
| `code_runner.py` | Executes a code block's text via Python's `exec`, capturing stdout/stderr. No sandboxing -- it's your own code, typed by your own hand, run on your own machine. |
| `screenshot_gallery.py` | Main app: webcam loop, screen capture (`mss`), gesture state machine, and orchestration of all of the above. |
| `mouth_launcher.py` | Standalone demo of face-blendshape gestures, kept separate from the main app pending further testing. |
| `pinch_drag.py` | The original minimal demo the rest of the app grew out of. |

## APIs & libraries used

- **[OpenCV](https://opencv.org/) (`opencv-python`)** -- webcam capture, all
  drawing (rectangles, circles, text, rounded rects built from primitives),
  and window display (`cv2.imshow`/`cv2.namedWindow`/`cv2.waitKey`).
- **[MediaPipe](https://ai.google.dev/edge/mediapipe) (`mediapipe`) -- Tasks
  API**, not the older `mp.solutions` API (removed as of the installed
  `mediapipe==1.0.1`):
  - `mediapipe.tasks.python.vision.HandLandmarker` -- 21-point hand landmark
    detection, `RunningMode.VIDEO` for temporally-consistent tracking across
    frames. Model: [`hand_landmarker.task`](https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task).
  - `mediapipe.tasks.python.vision.FaceLandmarker` -- face mesh + ARKit-style
    blendshape scores (`output_face_blendshapes=True`). Model:
    [`face_landmarker.task`](https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task).
- **[pywin32](https://github.com/mhammond/pywin32)** (`win32gui`, `win32con`,
  `win32api`) -- restyling an OpenCV window to borderless/always-on-top and
  repositioning it (`overlay_window.py`), and synthesizing the Win+Tab key
  combo for Task View (`mouth_launcher.py`).
- **[mss](https://python-mss.readthedocs.io/)** -- fast full-screen capture
  for the screenshot gallery.
- **[NumPy](https://numpy.org/)** -- frame buffer manipulation (blitting
  thumbnails/previews into the display frame, building the black fullscreen
  canvas for a zoomed code block).

## Setup

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Download the two MediaPipe Tasks models (not committed -- see `.gitignore`):

```powershell
mkdir models
curl -L -o models\hand_landmarker.task https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
curl -L -o models\face_landmarker.task https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
```

Then run any of the demos:

```powershell
.venv\Scripts\python pinch_drag.py
.venv\Scripts\python screenshot_gallery.py
.venv\Scripts\python mouth_launcher.py
```

## Gesture reference (`screenshot_gallery.py`)

| Gesture | Effect |
|---|---|
| Closed fist, held ~0.4s | Capture a screenshot (adds to gallery, max 4, FIFO) |
| Point at a thumbnail | Select it, preview enlarged in the corner |
| Point at a block, hover ~0.15s | Select it for zoom |
| Pinch (thumb+index) on a block | Drag it |
| Pinch-drag a block onto the trash, hold ~0.4s | Delete it |
| Hover the `+` / `<>` buttons ~0.15s | Create a text / code block (max 4) |
| Circle traced over a block, then point at a second block | Link the two |
| Spread thumb+index apart (selected photo or block) | Go fullscreen |
| Pinch thumb+index together (fullscreen) | Return to the corner |
| Closed fist, held ~0.4s (fullscreen code block) | Run the code |
| Typed keys (fullscreen text/code block) | Edit its text; Backspace/Enter work; Escape returns |

## Known limitations

- Windows-only (`pywin32`-based window styling and key synthesis).
- Single-hand tracking (`num_hands=1`); gesture thresholds (pinch/spread
  distances, hold durations, circle-detection geometry) are heuristics tuned
  by hand, not learned -- expect to retune `*_THRESHOLD_PX` / `*_HOLD_SECONDS`
  constants to your own webcam distance and hand size.
- Code blocks run via plain `exec()` -- no sandboxing. Fine for your own
  code on your own machine; never wire this up to input you didn't type
  yourself.
- `mouth_launcher.py` tracks Excel's "open" state with a plain flag, not by
  checking the actual process -- closing Excel by hand desyncs it.
- Screenshots and blocks live in memory only; nothing is persisted to disk,
  everything is lost on quit.
