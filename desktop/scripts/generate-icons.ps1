param(
  [Parameter(Mandatory = $true)]
  [string]$Source
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$brandingDir = Join-Path $repoRoot 'assets\branding'
$desktopAssetsDir = Join-Path $repoRoot 'desktop\assets'
$frontendPublicDir = Join-Path $repoRoot 'simulator\frontend\public'

foreach ($directory in @($brandingDir, $desktopAssetsDir, $frontendPublicDir)) {
  [System.IO.Directory]::CreateDirectory($directory) | Out-Null
}

function New-ResizedPngBytes {
  param(
    [System.Drawing.Image]$Image,
    [int]$Size
  )

  $bitmap = New-Object System.Drawing.Bitmap($Size, $Size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $bitmap.SetResolution(96, 96)
  $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
  try {
    $graphics.Clear([System.Drawing.Color]::Transparent)
    $graphics.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceCopy
    $graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
    $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $graphics.DrawImage($Image, 0, 0, $Size, $Size)
  }
  finally {
    $graphics.Dispose()
  }

  $stream = New-Object System.IO.MemoryStream
  try {
    $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
    return $stream.ToArray()
  }
  finally {
    $stream.Dispose()
    $bitmap.Dispose()
  }
}

function Save-Png {
  param(
    [System.Drawing.Image]$Image,
    [int]$Size,
    [string]$Path
  )

  [byte[]]$pngBytes = @(New-ResizedPngBytes -Image $Image -Size $Size)
  [System.IO.File]::WriteAllBytes($Path, $pngBytes)
}

$sourceImage = [System.Drawing.Image]::FromFile((Resolve-Path $Source))
try {
  Save-Png -Image $sourceImage -Size 1024 -Path (Join-Path $brandingDir 'cyberarm-icon.png')
  Save-Png -Image $sourceImage -Size 512 -Path (Join-Path $desktopAssetsDir 'icon.png')
  Save-Png -Image $sourceImage -Size 256 -Path (Join-Path $frontendPublicDir 'icon.png')

  $sizes = @(16, 20, 24, 32, 40, 48, 64, 128, 256)
  $images = [System.Collections.ArrayList]::new()
  foreach ($size in $sizes) {
    [byte[]]$pngBytes = @(New-ResizedPngBytes -Image $sourceImage -Size $size)
    [void]$images.Add($pngBytes)
  }
  $iconPath = Join-Path $desktopAssetsDir 'icon.ico'
  $stream = [System.IO.File]::Create($iconPath)
  $writer = New-Object System.IO.BinaryWriter($stream)
  try {
    $writer.Write([uint16]0)
    $writer.Write([uint16]1)
    $writer.Write([uint16]$sizes.Count)

    $offset = 6 + (16 * $sizes.Count)
    for ($index = 0; $index -lt $sizes.Count; $index++) {
      $sizeByte = if ($sizes[$index] -eq 256) { 0 } else { $sizes[$index] }
      $writer.Write([byte]$sizeByte)
      $writer.Write([byte]$sizeByte)
      $writer.Write([byte]0)
      $writer.Write([byte]0)
      $writer.Write([uint16]1)
      $writer.Write([uint16]32)
      $writer.Write([uint32]$images[$index].Length)
      $writer.Write([uint32]$offset)
      $offset += $images[$index].Length
    }

    foreach ($image in $images) {
      $writer.Write($image)
    }
  }
  finally {
    $writer.Dispose()
    $stream.Dispose()
  }
}
finally {
  $sourceImage.Dispose()
}

Write-Host "Generated CyberArm icons from $Source"
