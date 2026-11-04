# RocketWright web UI

The default entry is now a dark production workbench for the local bottle-workshop trial.
It connects human analysis checkpoints, saved evidence, production downloads and separate
design/flight videos. See [local workbench operation](../docs/workbench.md).
The general conversation screen remains available. Paid design calls are disabled by default;
the API returns HTTP 423 until explicitly enabled during the final connection review.

Single-screen Next.js (App Router, TypeScript, React 19) frontend for the RocketWright design
agent. Light theme, Japanese labels, no navigation; the audience is hackathon judges and the
general public, with the engineering detail folded into a collapsible 「詳細（エンジニア向け）」
area at the bottom right. Charts use Recharts only; the 3D view uses plain three.js.

## Layout

```
┌──────────────────────── status strip: app name + 待機中 / 設計中（試行 n）/ 完了 / エラー ─────────────────┐
│ chat                 │ 3D model of the displayed design          │ 図面 (SVG side view + download)     │
│  example chips       │   tier badge · お手本：<reference> ·        │ 軌道／飛行 (ascent profile or       │
│  request textarea    │   overall length / diameter               │   altitude vs time)                 │
│  設計を開始/中断/リセット│                                           │ 部品 (BOM table + CSV)              │
│  conversation        ├───────────────────────────────────────────┤ 詳細（エンジニア向け）, collapsed:    │
│  clarifying question │ 費用: big total, stacked breakdown bar,   │   仮想打ち上げ (DispersionPanel),    │
│   + reply box        │   itemised list with notes / 仮置き tags   │   試行ログ, 設計案, レビュー, 公式     │
└──────────────────────┴───────────────────────────────────────────┴─────────────────────────────────────┘
```

- 3 columns at >= 1200 px, 2 columns (chat | rest) between 800 and 1199 px, one column below.
- **Displayed design** (centre and right panels): the latest *passing* candidate, else the latest
  attempt that carries a design, else the reference seed. Clicking a row / card in 詳細 overrides
  the rule until the next run (`selectDisplayedDesign` in `app/lib/designState.ts` is pure).
- No hero numbers (altitude, success rate) on the main screen by the owner's decision; they live
  inside 詳細.

## Run

Requirements: Node >= 18.18 and the Python backend.

```bash
# backend (repository root)
uv run uvicorn api.main:app --reload --port 8000

# frontend
cd web
npm install
npm run dev          # http://localhost:3000
```

The backend allows CORS from `http://localhost:3000` and `http://127.0.0.1:3000`.

### Environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE` | `/backend` | Same-origin API prefix, or an explicit backend origin. |
| `ROCKETWRIGHT_API_URL` | `http://127.0.0.1:8000` | Server-side target of the `/backend` forwarding rule. |

Put it in `web/.env.local` to override, e.g. `NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000`.

### Dependencies

`next`, `react`, `react-dom`, `recharts` (charts) and `three` + `@types/three` (3D view). No UI kit.

## How it works

- `app/lib/sse.ts`: pure SSE parser (`parseSseChunk`) for the `fetch` ReadableStream; the request
  is a POST, so `EventSource` cannot be used.
- `app/lib/designState.ts`: pure reducer that folds `AgentEvent`s (thinking / text / tool_call /
  tool_result / candidate / review / final / error / question) into UI state, plus the pure
  selectors `selectDisplayedDesign` and `findAttemptByDesign`. It also keeps the normalised
  `requirement` (from the `classify_requirement` tool_call), the `derive_requirements` result
  (`derived`, each quantity with its `formula` string), the reference seed design and
  `pendingQuestion`.
- `app/lib/useDesignStream.ts`: the hook that POSTs to `/design` and drives the reducer; `answer()`
  implements the clarifying-question fallback below.
- `app/lib/useDesignSummary.ts`: fetches `POST /artifacts/summary` for the displayed design
  (300 ms debounce, cached by the design's canonical JSON for the page's lifetime) and then the
  SVG text of `drawing.url`.
- `app/lib/model3d.ts`: `buildProceduralModel(design)` returns a `THREE.Group`; `loadStl(url)` is
  the STL hook (see below).
- `app/lib/chartTheme.ts`: Recharts colours for the light palette, shared by the charts.
- `app/components/*`: presentational client components. `StatusStrip`, `ChatPanel`, `ModelViewer`,
  `CostPanel`, `DrawingPanel`, `FlightChart`, `BomPanel`, `DetailsPanel` form the layout;
  `AttemptLog`, `CandidateCards`, `ReviewPanel`, `DispersionPanel` and `TierBadge` (now a chip,
  plus `ClassifyNotes`) are reused inside it.

Every number shown comes from a tool result or a backend endpoint; the UI only converts units
(`format.ts`). Provenance violations reported by the backend are shown as errors in the chat.

### Clarifying questions (fallback)

`POST /design` takes a single `text` and has no conversation memory. When the agent emits a
`question` event, the chat shows it as a question bubble with a reply box. Sending the reply
restarts the loop with the request so far plus the answer appended:

## Build verification

The integrated production build and TypeScript checks passed with Node 24.19.0 and the committed
pnpm lockfile. The existing candidate card required an explicit bottle-tier guard for TypeScript
narrowing. UI rendering uses plain CSS and Recharts; no additional UI kit was introduced.

```
<request>

追加情報: <answer>
```

(same seed; repeated answers keep appending). When the backend gains a multi-turn `/design`,
replace the body built in `answer()` (`app/lib/useDesignStream.ts`) with the conversation.

### 3D view and the STL swap point

`ModelViewer.tsx` owns one `WebGLRenderer` per mount (light background, soft shadow on a ground
disc, `OrbitControls` with slow auto-rotate, fit-to-view when the design changes, a
`ResizeObserver` on the container). The model is procedural and mirrors the proportions of
`rocketwright/drawing.py` so the 3D view and the SVG side view agree:

| tier | geometry |
| --- | --- |
| amateur | nose (conical / ogive / elliptical lathe) + body cylinder + trapezoidal fins from `FinSet` (count, root / tip chord, span, sweep) + motor casing and a small nozzle |
| bottle | PET lathe (neck, rounded shoulder, body 3.5 d, dome 0.8 d) with a visible water column at `water_fill_frac`, a cap / nozzle ring, 3 fins when `has_fins`, a parachute pack on top when `has_parachute` |
| commercial / heavy | stacked stage cylinders (d = 0.05 · prop^(1/3) m, length = prop / (1000 · area)), interstage rings, ogive fairing 2.5 d, engine bells (count = `engine_count`, at most 9), and for heavy strap-on boosters (0.4 d wide, 0.6 · L1 long, at most 8) around stage 1 |

To show the teammate's STL instead, replace the one `buildProceduralModel(parsed)` call in
`ModelViewer.tsx` with `loadStl(url)` (from `app/lib/model3d.ts`, uses `STLLoader`) wrapped in a
`THREE.Mesh` inside a `THREE.Group`; everything else (fit, shadow, rotation) stays the same.

## Artifacts, drawings and downloads

- `POST /artifacts/summary {design, requirement|null, width_px|null}` returns `tier`, `cost_jpy`,
  `cost_breakdown[{label, jpy, note, provisional}]`, `bom[{item_id, name, qty, mass_kg, price_jpy,
  source_or_provisional}]`, `drawing{id, url}`, `mass{...}` and `dimensions{length_m, diameter_m}`.
  The cost panel, BOM table, drawing panel and the length / diameter overlay read from it
  (`toDesignSummary` in `app/lib/api.ts` parses it defensively).
- The side-view SVG (`drawing.url`, generated by `rocketwright/drawing.py`) is our own output,
  which is why it is injected with `dangerouslySetInnerHTML`. Candidate cards in 詳細 still render
  their own side view lazily through `POST /artifacts/render`.
- Download links come from the `download` map of an `export_report` / `render_drawing` tool
  result (`exportInfoFromEvents` in `app/lib/api.ts`). The 部品 panel shows the 部品表 CSV link
  when an export exists for the displayed design (else any exported BOM).
- Paths are backend-relative (`/artifacts/rep_1.md`) and are joined onto `NEXT_PUBLIC_API_BASE`
  by `apiUrl`. Artifacts live in the backend process (bounded, not persisted): restart the API and
  the links expire.

## Note on this scaffold (written without a build)

This UI was written on a machine with Node 10 only, so `next build` / `tsc` could not be run.
The first `npm install && npm run build` on a Node >= 18.18 machine may need small fixes; look
here first, in this order:

1. `app/lib/model3d.ts` and `app/components/ModelViewer.tsx`: the three.js imports
   (`three`, `three/examples/jsm/controls/OrbitControls.js`,
   `three/examples/jsm/loaders/STLLoader.js`) and `@types/three` typings (e.g. `MeshPhysicalMaterial`
   options, `STLLoader.load` callback types, `shadow.camera` being an `OrthographicCamera`).
2. Recharts `Tooltip` `formatter` / `labelFormatter` typings in `FlightChart.tsx` and
   `DispersionPanel.tsx`.
3. `next-env.d.ts` generation and the `react-hooks/exhaustive-deps` lint comment in
   `useDesignSummary.ts`.

Removed in this rebuild: the "表示" tier override select that used to sit in `TierBadge` (the
panels now follow the classified tier / displayed design), and the old `TierBadge` panel props
(`attemptCount`, `maxAttempts`, `viewTier`). No component file was deleted.

## 日本語の概要

1 画面・3 列構成です。左が対話（要求の入力、例文チップ、進行の説明、聞き返しへの回答欄）、中央が
表示中の設計案の 3D モデル（上）と費用の内訳（下）、右が図面（側面図 SVG）・軌道／飛行グラフ・部品表、
その下に折りたたみの「詳細（エンジニア向け）」（仮想打ち上げの散布・試行ログ・設計案カード・レビュー・
定量要求の公式）があります。バックエンド（`uv run uvicorn api.main:app --reload --port 8000`）を
起動した上で、`npm install && npm run dev` で http://localhost:3000 を開いてください。
表示される数値はすべてバックエンドのツール結果または `/artifacts/summary` から取り、UI 側では
単位変換のみ行います。聞き返し（question）への回答は、元の要求に「追加情報:」として追記して
設計をやり直します（バックエンドに会話の記憶がないため）。
