param([ValidateSet('Plan','Move','Verify')][string]$Mode='Plan')
$ErrorActionPreference='Stop'
$taskRoot=[IO.Path]::GetFullPath('E:\CyberArm\mechanical')
$recordRoot=Join-Path $taskRoot 'archive\_整理记录\20260908'
$manifestPath=Join-Path $recordRoot 'move_manifest.json'

function Assert-Scoped([string]$path) {
    $full=[IO.Path]::GetFullPath($path)
    if (-not $full.StartsWith($taskRoot+'\',[StringComparison]::OrdinalIgnoreCase)) { throw "Outside mechanical: $full" }
    $probe=$full
    while ($probe -and $probe -ne $taskRoot) {
        if (Test-Path -LiteralPath $probe) {
            $info=Get-Item -LiteralPath $probe -Force
            if ($info.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse point: $probe" }
        }
        $probe=[IO.Path]::GetDirectoryName($probe)
    }
    return $full
}
function Save-Record([string]$path,$value) {
    $null=Assert-Scoped $path
    [IO.File]::WriteAllText($path,($value | ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
}

if ($Mode -eq 'Plan') {
    if (Test-Path -LiteralPath $manifestPath) { throw 'Plan already exists. Do not replace the original move record.' }
    $entries=[Collections.Generic.List[object]]::new()
    function Add-Entry([string]$from,[string]$to) {
        $src=Assert-Scoped (Join-Path $taskRoot $from)
        $dst=Assert-Scoped (Join-Path $taskRoot $to)
        if (-not (Test-Path -LiteralPath $src)) { throw "Missing source: $src" }
        if (Test-Path -LiteralPath $dst) { throw "Destination exists: $dst" }
        $entries.Add([PSCustomObject]@{from=$src;to=$dst})
    }
    foreach ($folder in @('arduino_reference_replica','arduino_reference_revB','blender_arm_v2','blender_arm_v3','blender_arm_v4')) {
        Add-Entry $folder ('archive\'+$folder)
    }
    Add-Entry 'exports' 'archive\fusion_v1\exports'
    Add-Entry '__pycache__' 'archive\caches\__pycache__'
    foreach ($name in @('CyberArm_MG90S_Assembly_v1.step','CyberArm_MG90S_Printable_v1.f3d','CyberArm_MG90S_v1.png','ArduinoArm_imported_raw.png')) {
        Add-Entry $name ('archive\fusion_v1\'+$name)
    }
    Add-Entry 'README.md' 'archive\fusion_v1\README_original.md'
    Add-Entry 'arduino_reference_revC\Arduino_Replica_RevC_Connections.blend1' 'archive\backups\RevC\Arduino_Replica_RevC_Connections.blend1'
    foreach ($file in Get-ChildItem -LiteralPath $taskRoot -File -Filter '*.py') { Add-Entry $file.Name ('scripts\'+$file.Name) }
    foreach ($file in Get-ChildItem -LiteralPath $taskRoot -File -Filter '*.log') { Add-Entry $file.Name ('logs\'+$file.Name) }
    foreach ($name in @('servo_bounds.json','servo_geometry.json')) { Add-Entry $name ('inspection_data\'+$name) }
    $inventory=[Collections.Generic.List[object]]::new()
    foreach ($entry in $entries) {
        $item=Get-Item -LiteralPath $entry.from
        $files=if($item.PSIsContainer){@(Get-ChildItem -LiteralPath $entry.from -File -Recurse -Force)}else{@($item)}
        foreach ($file in $files) {
            $dest=if($item.PSIsContainer){$entry.to+$file.FullName.Substring($entry.from.Length)}else{$entry.to}
            $null=Assert-Scoped $file.FullName; $null=Assert-Scoped $dest
            $inventory.Add([PSCustomObject]@{from=$file.FullName;to=$dest;bytes=$file.Length;sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash})
        }
    }
    if (($inventory.to | Sort-Object -Unique).Count -ne $inventory.Count) { throw 'Duplicate destinations' }
    $protected=[Collections.Generic.List[object]]::new()
    foreach ($folder in @('arduino_reference_revC','fusion_reference_review','MG996R Servo Motor','servo配件','伺服电机模型_ mg90S_ Tower Pro(Servo_爱给网_aigei_com')) {
        foreach ($file in Get-ChildItem -LiteralPath (Join-Path $taskRoot $folder) -File -Recurse -Force) {
            if ($inventory.from -contains $file.FullName) { continue }
            $protected.Add([PSCustomObject]@{path=$file.FullName;sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash})
        }
    }
    $null=New-Item -ItemType Directory -Path $recordRoot -Force
    Save-Record $manifestPath ([PSCustomObject]@{created=(Get-Date).ToString('o');root=$taskRoot;entries=$entries;files=$inventory;protected_files=$protected})
    [PSCustomObject]@{entries=$entries.Count;files=$inventory.Count;bytes=($inventory | Measure-Object bytes -Sum).Sum;protected=$protected.Count;manifest=$manifestPath} | ConvertTo-Json
    exit
}

$plan=Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($plan.root -ne $taskRoot) { throw 'Wrong workspace in manifest' }
if ($Mode -eq 'Move') {
    # Entire preflight is completed before the first move; never overwrite.
    foreach ($entry in $plan.entries) {
        $null=Assert-Scoped $entry.from; $null=Assert-Scoped $entry.to
        if (-not(Test-Path -LiteralPath $entry.from)) {throw "Source absent: $($entry.from)"}
        if (Test-Path -LiteralPath $entry.to) {throw "Target exists: $($entry.to)"}
    }
    foreach ($file in $plan.files) {
        if ((Get-FileHash -LiteralPath $file.from -Algorithm SHA256).Hash -ne $file.sha256) {throw "Source changed: $($file.from)"}
    }
    foreach ($entry in $plan.entries) {
        $null=New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($entry.to)) -Force
        Move-Item -LiteralPath $entry.from -Destination $entry.to
        Write-Output "Moved: $($entry.from.Substring($taskRoot.Length+1)) -> $($entry.to.Substring($taskRoot.Length+1))"
    }
}
$problems=[Collections.Generic.List[string]]::new()
$updatesPath=Join-Path $recordRoot 'path_updates.json'
$updates=if(Test-Path -LiteralPath $updatesPath){@(Get-Content -LiteralPath $updatesPath -Raw | ConvertFrom-Json)}else{@()}
foreach ($file in $plan.files) {
    if (-not(Test-Path -LiteralPath $file.to)) {$problems.Add("Missing $($file.to)");continue}
    $update=@($updates | Where-Object {$_.path -eq $file.to})
    if ($update.Count -eq 1) {
        $null=Assert-Scoped $update[0].backup
        if ($update[0].before_sha256 -ne $file.sha256 -or (Get-FileHash -LiteralPath $update[0].backup -Algorithm SHA256).Hash -ne $file.sha256) {$problems.Add("Original backup mismatch $($file.to)")}
        if ((Get-FileHash -LiteralPath $file.to -Algorithm SHA256).Hash -ne $update[0].after_sha256) {$problems.Add("Unexpected script change $($file.to)")}
    } elseif ((Get-FileHash -LiteralPath $file.to -Algorithm SHA256).Hash -ne $file.sha256) {$problems.Add("Changed $($file.to)")}
}
foreach ($file in $plan.protected_files) {
    if (-not(Test-Path -LiteralPath $file.path)) {$problems.Add("Missing protected $($file.path)");continue}
    if ((Get-FileHash -LiteralPath $file.path -Algorithm SHA256).Hash -ne $file.sha256) {$problems.Add("Changed protected $($file.path)")}
}
Save-Record (Join-Path $recordRoot 'final_hash_verification.json') ([PSCustomObject]@{time=(Get-Date).ToString('o');checked_moved=$plan.files.Count;documented_path_updates=$updates.Count;checked_protected=$plan.protected_files.Count;problems=$problems})
if ($problems.Count) { throw ($problems -join "`n") }
Write-Output "Verified: $($plan.files.Count) moved files and $($plan.protected_files.Count) protected files; all SHA256 values match."
