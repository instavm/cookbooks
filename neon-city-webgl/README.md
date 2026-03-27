# Neon City WebGL

Fullscreen WebGL cityscape for `instavm cookbook deploy neon-city-webgl`.

It renders a neon-dusk skyline with procedural towers, reflective streets,
light trails, drifting particles, and a looping robot pedestrian. The app is
zero-key and runs entirely in the browser after the static assets are served.

## Local Run

```bash
npm ci
npm run build
PORT=3000 node server.mjs
```

Open `http://127.0.0.1:3000`.

## Deploy

```bash
instavm cookbook deploy neon-city-webgl
```

## Assets

- `public/robots/RobotExpressive.glb`
  - Source: the official three.js `RobotExpressive` example asset
  - Attribution: model by Tomas Laulhe, modifications by Don McCurdy
  - License: CC0 1.0, per the official three.js example page

## Stack

- `three`
- `@react-three/fiber`
- `@react-three/drei`
- `@react-three/postprocessing`
- `postprocessing`
- `lamina`
- `maath`
- `simplex-noise`
- `gsap`
