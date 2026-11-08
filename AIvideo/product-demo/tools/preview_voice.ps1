param([Parameter(Mandatory=$true)][string]$Plan, [Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer,Windows.Media.SpeechSynthesis,ContentType=WindowsRuntime]
$null = [Windows.Media.SpeechSynthesis.SpeechSynthesisStream,Windows.Media.SpeechSynthesis,ContentType=WindowsRuntime]
$config = Get-Content -LiteralPath $Plan -Raw -Encoding UTF8 | ConvertFrom-Json
$voice = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::new()
$method = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
$await = $method.MakeGenericMethod([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
try {
    $selected = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | Where-Object { $_.DisplayName -eq $config.voice -and $_.Language -eq 'ja-JP' } | Select-Object -First 1
    if ($null -eq $selected) { throw 'The configured Japanese voice is not installed.' }
    $voice.Voice = $selected
    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
    for ($i = 0; $i -lt $config.shots.Count; $i++) {
        $shot = $config.shots[$i]
        if (-not $shot.caption) { continue }
        $line = if ($shot.speech) { $shot.speech } else { $shot.caption }
        $op = $voice.SynthesizeTextToStreamAsync($line)
        $task = $await.Invoke($null,@($op))
        $task.GetAwaiter().GetResult() | Out-Null
        $stream = [System.IO.WindowsRuntimeStreamExtensions]::AsStreamForRead($task.Result)
        $path = Join-Path $OutputDirectory ('{0:D2}.wav' -f $i)
        $out = [IO.File]::Create($path)
        try { $stream.CopyTo($out) } finally { $out.Dispose(); $stream.Dispose(); $task.Result.Dispose() }
    }
} finally { $voice.Dispose() }
