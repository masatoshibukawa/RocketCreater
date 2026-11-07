param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$Spec,
    [Parameter(Mandatory=$true)][string]$Training,
    [Parameter(Mandatory=$true)][string]$Output,
    [Parameter(Mandatory=$true)][string]$Runtime,
    [Parameter(Mandatory=$true)][string]$CupyPath,
    [Parameter(Mandatory=$true)][string]$CudaPath,
    [Parameter(Mandatory=$true)][string]$CudaDllDir,
    [string]$OllamaUrl = 'http://127.0.0.1:11439',
    [string]$Model = 'gemma4:12b',
    [switch]$ResumeStage6Report
)
$ErrorActionPreference = 'Stop'
$env:PYTHONPATH = (Resolve-Path -LiteralPath $CupyPath).Path
$env:CUDA_PATH = (Resolve-Path -LiteralPath $CudaPath).Path
$env:CFD_CUDA_DLL_DIR = (Resolve-Path -LiteralPath $CudaDllDir).Path
$env:PATH = $env:CFD_CUDA_DLL_DIR + ';' + $env:PATH
$env:ROCKETWRIGHT_OLLAMA_URL = $OllamaUrl
$env:ROCKETWRIGHT_LOCAL_MODEL = $Model
$preflightPath = $Output + '-preflight.json'
if ($ResumeStage6Report) { $preflightPath = $Output + '-resume-preflight.json' }

# This process and its children only. No registry, credentials or global configuration changes.
@'
import json, os, sys
from pathlib import Path
from rocketwright.agent.local_runtime import LocalDirector
from rocketwright.analysis.runtime import Runtime
from rocketwright.analysis.service import code_hash
handle = os.add_dll_directory(os.environ['CFD_CUDA_DLL_DIR'])
import cupy as cp
import numpy as np
director = LocalDirector()
if director.model not in director.models():
    raise SystemExit('Requested local model is unavailable')
runtime = Runtime.model_validate_json(Path(sys.argv[1]).read_text(encoding='utf-8'))
if not runtime.cfd_enabled or 'fem' not in runtime.capabilities():
    raise SystemExit('Native CFD and FEM capabilities must be configured')
if float(cp.arange(10).sum()) != 45:
    raise SystemExit('GPU preflight failed')
data = dict(source_hash=code_hash(), numpy=np.__version__, cupy=cp.__version__,
            model=director.model, gpu_count=cp.cuda.runtime.getDeviceCount(),
            planner='local_llm', claude_requests=0)
Path(sys.argv[2]).write_text(json.dumps(data,indent=2),encoding='utf-8')
print(json.dumps(data),flush=True)
'@ | & $Python - $Runtime $preflightPath
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$stageArguments = @($Spec, $Training, $Output, $Runtime, '--planner', 'local_llm', '--through', '7')
if ($ResumeStage6Report) { $stageArguments += '--resume-stage6-report' }
& $Python -X utf8 -u -m scripts.run_learning_stages @stageArguments
exit $LASTEXITCODE
