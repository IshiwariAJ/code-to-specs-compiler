# Kitchen sink PowerShell sample.
# Purpose: compile supported constructs and expose unsupported constructs as warnings.

$Script:MaxPoints = 1000
$Script:PremiumThreshold = 100000
$Script:AuditCounter = 0

class Purchase {
    [int]$Price
    [string]$Category

    Purchase([int]$price, [string]$category) {
        $this.Price = $price
        $this.Category = $category
    }
}

function Get-UserBenefit {
    <#
    .SYNOPSIS
    Supported-heavy function with guards, loops, try/catch/finally and condition chains.
    #>
    param(
        [string]$Status,
        [string]$Rank,
        [object[]]$PurchaseHistory,
        [switch]$DryRun
    )

    if ($Status -ne "ACTIVE") {
        throw "inactive user"
    }

    $totalAmount = 0
    foreach ($history in $PurchaseHistory) {
        $totalAmount += $history.Price
    }

    try {
        $configText = Get-Content -Path "config.json" -ErrorAction Stop
        Write-Output $configText
    } catch {
        Write-Error $_
        throw $_
    } finally {
        $Script:AuditCounter += 1
        Write-Output "benefit calculation finished"
    }

    if ($DryRun) {
        return @{ Points = 0; Message = "dry run"; Level = "basic" }
    } elseif ($totalAmount -ge $Script:PremiumThreshold -and $Rank -eq "Gold") {
        return @{ Points = $Script:MaxPoints; Message = "premium benefit"; Level = "premium" }
    } elseif ($totalAmount -ge 50000) {
        return @{ Points = 500; Message = "standard benefit"; Level = "standard" }
    } else {
        return @{ Points = 100; Message = "basic benefit"; Level = "basic" }
    }
}

function Inspect-UnsupportedFlow {
    <#
    .SYNOPSIS
    Unsupported-heavy function for extraction warning checks.
    #>
    param(
        [hashtable]$User,
        [int[]]$Values
    )

    $index = 0
    $total = 0

    while ($index -lt $Values.Count) {
        $total += $Values[$index]
        $index += 1
    }

    do {
        $total -= 1
    } until ($total -le 1000)

    for ($i = 0; $i -lt $Values.Count; $i++) {
        if ($Values[$i] -lt 0) {
            continue
        }
        $total += $Values[$i]
    }

    switch ($User.Status) {
        "ACTIVE" { $total += 10 }
        "BANNED" { $total -= 100 }
        default { $total += 0 }
    }

    $Values |
        Where-Object { $_ -gt 0 } |
        ForEach-Object { Write-Output $_ }

    return $total
}

filter Select-Positive {
    if ($_ -gt 0) {
        $_
    }
}

