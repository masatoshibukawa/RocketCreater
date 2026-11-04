param(
    [string]$OutputPath = (Join-Path $PSScriptRoot '..\palette-preview.png')
)

Add-Type -AssemblyName System.Drawing
$culture = [System.Globalization.CultureInfo]::InvariantCulture
$rows = Import-Csv -LiteralPath (Join-Path $PSScriptRoot '..\palette-contrast.csv')
$groups = @($rows | Group-Object palette)
if ($groups.Count -ne 4) { throw 'Expected four palettes.' }

$bitmap = [System.Drawing.Bitmap]::new(1200, 920)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$titleFont = [System.Drawing.Font]::new('Segoe UI', 28, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
$headingFont = [System.Drawing.Font]::new('Segoe UI', 24, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
$bodyFont = [System.Drawing.Font]::new('Segoe UI', 18, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
$codeFont = [System.Drawing.Font]::new('Consolas', 16, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)

function Draw-Label {
    param([string]$Value, [System.Drawing.Font]$Font, [string]$Color, [int]$X, [int]$Y)
    $brush = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml($Color))
    try { $graphics.DrawString($Value, $Font, $brush, $X, $Y) }
    finally { $brush.Dispose() }
}

function Draw-Box {
    param([string]$Color, [int]$X, [int]$Y, [int]$Width, [int]$Height)
    $brush = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml($Color))
    try { $graphics.FillRectangle($brush, $X, $Y, $Width, $Height) }
    finally { $brush.Dispose() }
}

try {
    $graphics.Clear([System.Drawing.ColorTranslator]::FromHtml('#14181C'))
    Draw-Label 'Four palettes, four directions' $titleFont '#F1F5F9' 40 24
    Draw-Label 'Original study palettes | opaque sRGB pairs | not a full-page accessibility audit' $bodyFont '#B8C4D0' 40 68
    for ($index = 0; $index -lt $groups.Count; $index++) {
        $group = $groups[$index]
        $x = 40 + ($index % 2) * 580
        $y = 120 + [Math]::Floor($index / 2) * 380
        $textRow = $group.Group | Where-Object role -EQ 'text'
        $mutedRow = $group.Group | Where-Object role -EQ 'muted'
        $accentRow = $group.Group | Where-Object role -EQ 'onAccent'
        $borderRow = $group.Group | Where-Object role -EQ 'border'
        Draw-Box $textRow.background $x $y 540 350
        Draw-Label $group.Name $headingFont $textRow.foreground ($x + 24) ($y + 20)
        Draw-Label 'Readable body text, with a clear hierarchy.' $bodyFont $textRow.foreground ($x + 24) ($y + 70)
        Draw-Label 'Supporting text remains readable.' $bodyFont $mutedRow.foreground ($x + 24) ($y + 104)
        Draw-Box $accentRow.background ($x + 24) ($y + 152) 230 48
        Draw-Label 'Primary action example' $bodyFont $accentRow.foreground ($x + 36) ($y + 162)
        $ratio = [double]::Parse($textRow.ratio, $culture).ToString('F2', $culture)
        Draw-Label ('Text ' + $textRow.foreground + ' / ' + $textRow.background) $codeFont $textRow.foreground ($x + 24) ($y + 222)
        Draw-Label ('Contrast ' + $ratio + ':1 | text / surface') $codeFont $mutedRow.foreground ($x + 24) ($y + 250)
        Draw-Box $borderRow.foreground ($x + 24) ($y + 298) 492 2
        Draw-Label ('Accent ' + $accentRow.background + ' | Border ' + $borderRow.foreground) $codeFont $mutedRow.foreground ($x + 24) ($y + 312)
    }
    Draw-Label 'Study date: 2026-11-04 | Numbers are calculated color contrast ratios.' $bodyFont '#B8C4D0' 40 892
    $bitmap.Save([System.IO.Path]::GetFullPath($OutputPath), [System.Drawing.Imaging.ImageFormat]::Png)
    Write-Output ([System.IO.Path]::GetFullPath($OutputPath))
}
finally {
    $titleFont.Dispose()
    $headingFont.Dispose()
    $bodyFont.Dispose()
    $codeFont.Dispose()
    $graphics.Dispose()
    $bitmap.Dispose()
}
