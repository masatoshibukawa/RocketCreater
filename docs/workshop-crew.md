# Workshop guides

The single design screen includes three procedural 3D mechanics with gray overalls,
yellow helmets, a workbench and a tool cart. The visual reference is
`final output ui example/drafts/07-analysis-explained.png`: guides stay in a separate
foreground stage so they cannot cover dimensions, results, graphs or controls.
They are illustrative guides, not human-clearance geometry or manufactured parts.
They are not inserted into exported images, drawings or videos.

## State and operation boundaries

| Observed application state | Guide behavior |
| --- | --- |
| Active design tool call, flow-analysis job, production or manufacturing generation | Inspect a part, check a clipboard and use a tool |
| No job, queued job, between tool calls or question awaiting an answer | Wait with subtle breathing and glances |
| A previously observed live operation finishes successfully | Put tools away, carry the toolbox and wipe the bench for six seconds, then wait |
| Error, interruption, failed/unconverged result or lost flow-analysis connection | Stop moving and wait for review |

Restoring an already completed result does not replay cleanup. A reference seed alone
is not a successful design. Concurrent operations prioritize live work over saved results.
No pose, elapsed animation time or visual control can start a calculation, acknowledge
a physical check, submit a print job or change a result's pass/fail status. Flow-analysis
polling continues through connection loss and tab changes while its uncertainty is visible.

Display and motion settings are saved locally. Reduced-motion preferences stop the guide
loops and model auto-rotation; manual model rotation remains available. Hiding the guides
unmounts their renderer. Hidden documents suspend the guide loop. WebGL failure shows
a static illustration and the same textual status. Renderer resources are disposed on unmount.

## Verification

From `web`, with Node 24 or newer for native TypeScript stripping:

```sh
node --test tests/workshopActivity.test.mjs
npx tsc --noEmit
npm run build
```

The operation-state tests cover unfinished tool calls, question waits, tool failures,
cancellation, seed-only results, observed completion, cleanup expiry and concurrent jobs.
The Python API stream test checks anti-buffering headers; paid design execution remains
disabled unless explicitly enabled by the existing environment setting.

For browser checks, use an isolated local replay server with clearly labeled recorded
physics results. Verify inspection, waiting, cleanup, interruption, error, hidden/paused
guides, reduced motion and a narrow viewport without calling a paid generation API or
submitting a printer job. A replay is UI verification, not evidence of a new analysis.
