# Requires PowerShell 7. Run once; existing outputs are never overwritten.
# Copies existing RevC meshes without changing geometry, scale, or source files.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$taskRoot = [IO.Path]::GetFullPath('E:\CyberArm\mechanical')
$sourceRoot = Join-Path $taskRoot 'arduino_reference_revC'
$printRoot = Join-Path $taskRoot '打印'

function Assert-Contained([string]$Path, [string]$Root) {
    $absolute = [IO.Path]::GetFullPath($Path)
    $prefix = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    if (-not $absolute.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside intended root: $absolute"
    }
    # Do not copy through junctions or symbolic links.
    $probe = $absolute
    while ($probe -and $probe.Length -ge $Root.Length) {
        if (Test-Path -LiteralPath $probe) {
            $item = Get-Item -LiteralPath $probe -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Reparse point is not allowed: $probe"
            }
        }
        $probe = [IO.Path]::GetDirectoryName($probe)
    }
    return $absolute
}

$full = @(Get-Content -LiteralPath (Join-Path $sourceRoot 'print_manifest.json') -Raw -Encoding utf8 | ConvertFrom-Json)
$trials = @(Get-Content -LiteralPath (Join-Path $sourceRoot 'fit_coupon_manifest.json') -Raw -Encoding utf8 | ConvertFrom-Json)
if ($full.Count -ne 12 -or $trials.Count -ne 6 -or ($full | Measure-Object quantity -Sum).Sum -ne 16) {
    throw 'Unexpected source manifest; re-review the packaging plan.'
}
$names = @{
    ARD_01_Base = '底座壳'; ARD_02_Foot_1 = '支脚'; ARD_03_Waist = '回转盘与肩部支架'
    ARD_04_Arm_01 = '大臂'; ARD_05_Arm_02_v3 = '小臂'; ARD_06_Arm_03 = '腕部支架'
    ARD_07_Gripper_base = '夹爪底板'; ARD_08_gear1 = '从动齿轮连杆'
    ARD_09_Link_Left = '夹爪短连杆'; ARD_10_Jaw_Left = '左夹爪'
    ARD_08_gear2 = '主动齿轮连杆'; ARD_10_Jaw_Right = '右夹爪'
}
$trialNames = @{
    S01 = '底座回转_MG996R圆盘'; S02 = '肩关节_MG996R圆盘'; S03 = '肘关节_MG996R圆盘'
    S04 = '腕旋转_MG90S双臂'; S05 = '腕俯仰_MG90S十字长臂'; S06 = '夹爪驱动_MG90S单臂'
}
$allDir = '01_所有完整打印件'
$trialDir = '02_先打印的接口试装片'
$noCouponDir = '03_不单独打印试片的零件'
$couponParts = @($trials.source_part | Sort-Object -Unique)
if ($couponParts.Count -ne 5) { throw 'Unexpected interface coverage.' }
$plan = [Collections.Generic.List[object]]::new()
function Add-CopyPlan($Item, [string]$Relative, [string]$Kind, [string]$Label, [string]$Id, [int]$Quantity) {
    $src = Assert-Contained $Item.file $sourceRoot
    $dst = Assert-Contained (Join-Path $printRoot $Relative) $printRoot
    if (-not (Test-Path -LiteralPath $src -PathType Leaf)) { throw "Missing source: $src" }
    if (Test-Path -LiteralPath $dst) { throw "Refusing to overwrite: $dst" }
    $plan.Add([pscustomobject]@{
        kind = $Kind; id = $Id; label = $Label; quantity = $Quantity
        source = $src; destination = $dst; relative_path = $Relative
        bounds_mm = $Item.bounds_mm; sha256 = (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash
    })
}
$index = 0
foreach ($part in $full) {
    $index++
    if (-not $names.ContainsKey($part.object)) { throw "Unknown part: $($part.object)" }
    $label = $names[$part.object]
    $filename = '{0:D2}_{1}_打印{2}件__{3}' -f $index, $label, $part.quantity, [IO.Path]::GetFileName($part.file)
    Add-CopyPlan $part (Join-Path $allDir $filename) '完整件' $label $part.object $part.quantity
    if ($part.object -notin $couponParts) {
        Add-CopyPlan $part (Join-Path $noCouponDir $filename) '完整件分类副本_无专用接口试片' $label $part.object $part.quantity
    }
}
foreach ($trial in $trials) {
    if (-not $trialNames.ContainsKey($trial.id) -or $trial.source_part -notin $full.object) { throw 'Unknown coupon.' }
    $filename = '{0}_{1}_试装1件_mm.stl' -f $trial.id, $trialNames[$trial.id]
    Add-CopyPlan $trial (Join-Path $trialDir $filename) '局部试装片_不用于整机装配' $trialNames[$trial.id] $trial.id 1
}
if ($plan.Count -ne 25 -or @($plan.destination | Sort-Object -Unique).Count -ne 25) { throw 'Invalid copy plan.' }
$manifestPath = Assert-Contained (Join-Path $printRoot '文件来源与校验.json') $printRoot
$csvPath = Assert-Contained (Join-Path $printRoot '打印数量清单.csv') $printRoot
foreach ($output in @($manifestPath, $csvPath)) {
    if (Test-Path -LiteralPath $output) { throw "Refusing to overwrite: $output" }
}

# Preflight is complete. Only create destinations and copy, never delete or move.
foreach ($entry in $plan) {
    $parent = [IO.Path]::GetDirectoryName($entry.destination)
    if (-not (Test-Path -LiteralPath $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
    Copy-Item -LiteralPath $entry.source -Destination $entry.destination -ErrorAction Stop
}
foreach ($entry in $plan) {
    $actual = (Get-FileHash -LiteralPath $entry.destination -Algorithm SHA256).Hash
    $sourceNow = (Get-FileHash -LiteralPath $entry.source -Algorithm SHA256).Hash
    if ($actual -ne $entry.sha256 -or $sourceNow -ne $entry.sha256) { throw "Hash mismatch: $($entry.destination)" }
}
$summary = [ordered]@{
    version = 'RevC'; generated_at = (Get-Date).ToString('o'); units = 'mm (import STL at 100%)'
    final_print_release = $false; geometry_modified = $false; source_files_modified = $false
    full_part_types = 12; assembled_printed_instances = 16; coupon_types = 6
    no_dedicated_coupon_part_types = 7; total_stl_copies = 25; all_sha256_checks_passed = $true
    warning = 'Folder 03 duplicates a subset of folder 01. Do not print both sets. No dedicated coupon does not mean fit or strength is verified.'
    files = @($plan.ToArray())
}
$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding utf8
$plan | Select-Object @{n='分类';e={$_.kind}}, @{n='编号';e={$_.id}}, @{n='零件';e={$_.label}},
    @{n='每套所需数量';e={$_.quantity}}, @{n='文件';e={$_.relative_path}},
    @{n='尺寸包围盒_mm';e={($_.bounds_mm | ForEach-Object { [Math]::Round($_, 3) }) -join ' x '}},
    @{n='注意';e={if ($_.kind -like '完整件分类副本*') {'与01文件夹重复，不重复打印；仍需完整件试装'} elseif ($_.id -like 'S0*') {'只测试局部接口，不能装入整机'} else {'整套数量；文件本身仅含一个零件'}}} |
    Export-Csv -LiteralPath $csvPath -NoTypeInformation -Encoding utf8BOM
[pscustomobject]$summary | Select-Object version, full_part_types, assembled_printed_instances, coupon_types, no_dedicated_coupon_part_types, total_stl_copies, all_sha256_checks_passed | ConvertTo-Json
