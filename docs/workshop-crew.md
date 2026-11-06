# Workshop guides

The design screen shows the drafted workshop pictures with moving heads and hands. The layers are
cut from `final output ui example/drafts/` 02 and 06 by `scripts/build_workshop_layers.py` and
moved with CSS in `web/app/workshop-scene.css`. The pictures are decoration: they are not
human-clearance geometry or manufactured parts, and they are not inserted into exported images,
drawings or videos.

## State and operation boundaries

| Observed application state | Guide behavior |
| --- | --- |
| Active design tool call, flow-analysis job, production or manufacturing generation | Move at the busy tempo |
| No job, queued job, between tool calls or question awaiting an answer | Rest the tool and look around |
| A previously observed live operation finishes successfully | Lower the hands and return the tool to the tray for six seconds, then wait |
| Error, interruption, failed/unconverged result or lost flow-analysis connection | Stop moving and wait for review |

Restoring an already completed result does not replay cleanup. A reference seed alone
is not a successful design. Concurrent operations prioritize live work over saved results.
No pose, elapsed animation time or visual control can start a calculation, acknowledge
a physical check, submit a print job or change a result's pass/fail status. Flow-analysis
polling continues through connection loss and tab changes while its uncertainty is visible.

Display and motion settings are saved locally. Reduced-motion preferences stop the guide
loops and model auto-rotation; manual model rotation remains available. Hiding the guides
unmounts their renderer. Hidden documents suspend the guide loop.
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

Current-design CAD, printing, manual and film jobs also feed this presentation state.
See [the saved design production flow](design-production-flow.md) for the current screen and API.

For browser checks, use an isolated local replay server with clearly labeled recorded
physics results. Verify inspection, waiting, cleanup, interruption, error, hidden/paused
guides, reduced motion and a narrow viewport without calling a paid generation API or
submitting a printer job. A replay is UI verification, not evidence of a new analysis.
