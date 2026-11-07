# Renders each slide of deliverables/presentation.pptx to a PNG via PowerPoint.
# Usage: powershell -File deliverables/build/render.ps1 <outDir>
param([string]$OutDir)
$deck = (Resolve-Path (Join-Path $PSScriptRoot "..\presentation.pptx")).Path
New-Item -ItemType Directory -Force $OutDir | Out-Null
Get-ChildItem $OutDir -Filter "slide-*.png" | Remove-Item -Force
$app = New-Object -ComObject PowerPoint.Application
try {
  $p = $app.Presentations.Open($deck, $true, $false, $true)  # WithWindow must be true: windowless open fails on decks with pictures here
  foreach ($s in $p.Slides) { $s.Export((Join-Path $OutDir ("slide-{0:D2}.png" -f $s.SlideIndex)), "PNG", 1600, 900) }
  $p.Close()
} finally { $app.Quit() }
Get-ChildItem $OutDir -Filter "slide-*.png" | ForEach-Object { $_.FullName }
