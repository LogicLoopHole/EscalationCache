#
# The MIT License (MIT)
#
# Copyright (c) 2026 LogicLoopHole
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#

# Influence.ps1
# The economy. Isolated on purpose so the formula is easy to find and tune.
# Depends on $script:Cfg (defined in EscalationCache.ps1) and Save-User (Entries.ps1).

# Most-recent validation date across the additive validations list (with legacy fallback).
function Get-LastValidationDate {
    param($Entry)
    $dates = @()
    if ($Entry.PSObject.Properties['validations'] -and $Entry.validations) {
        foreach ($v in @($Entry.validations)) { if ($v.date) { $dates += [datetime]$v.date } }
    }
    if ($Entry.PSObject.Properties['validated_date'] -and $Entry.validated_date) {
        $dates += [datetime]$Entry.validated_date          # legacy single-field entries
    }
    if ($dates.Count -eq 0) { return $null }
    return ($dates | Sort-Object -Descending | Select-Object -First 1)
}

function Get-DaysSinceValidation {
    param($Entry)
    $d = Get-LastValidationDate $Entry
    if ($null -eq $d) { return $null }
    return ([datetime]::Today - $d).Days
}

function Test-IsStale {
    param($Entry)
    $d = Get-DaysSinceValidation $Entry
    if ($null -eq $d) { return $false }
    return ($d -ge $script:Cfg.StaleAfterDays)
}

# Displayed tag. 'stale' is computed here from the date, never stored.
function Get-DisplayTag {
    param($Entry)
    if ($Entry.tag -eq 'superseded')         { return 'superseded' }
    if ($null -eq (Get-LastValidationDate $Entry)) { return $Entry.tag }   # never validated
    if (Test-IsStale $Entry)                 { return 'stale' }
    return $Entry.tag
}

# access_cost = min(cap, max(1, base + floor(days_since_validation / per)))
function Get-AccessCost {
    param($Entry)
    $base = $script:Cfg.BaseCost[$Entry.tag]
    if (-not $base) { $base = 1 }
    $days = Get-DaysSinceValidation $Entry
    if ($null -eq $days) { $days = 0 }
    $cost = $base + [math]::Floor($days / $script:Cfg.CostPerDays)
    $cost = [math]::Max(1, $cost)
    $cost = [math]::Min($script:Cfg.CostCap, $cost)
    return [int]$cost
}

function Add-Influence {
    param($User, [int]$Amount)
    $User.influence = [int]$User.influence + $Amount
    Save-User $User
}

# $true on success, $false if the user cannot afford it.
function Use-Influence {
    param($User, [int]$Amount)
    if ([int]$User.influence -lt $Amount) { return $false }
    $User.influence = [int]$User.influence - $Amount
    Save-User $User
    return $true
}

function Grant-ReturnBonus {
    param($User)
    $granted = 0
    if ($User.last_login) {
        $idle = ([datetime]::Today - [datetime]$User.last_login).Days
        $acc  = if ($User.PSObject.Properties['return_bonus_total']) { [int]$User.return_bonus_total } else { 0 }
        if ($idle -ge $script:Cfg.ReturnBonusIdleDays -and $acc -lt $script:Cfg.ReturnBonusCap) {
            $granted = $script:Cfg.ReturnBonus
            $User.influence = [int]$User.influence + $granted
            $User | Add-Member -NotePropertyName return_bonus_total -NotePropertyValue ($acc + $granted) -Force
        }
    }
    $User.last_login = (Get-Date).ToString('yyyy-MM-dd')
    Save-User $User
    return $granted
}
