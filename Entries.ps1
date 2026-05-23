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

# Entries.ps1
# Persistence (flat JSON files) + domain operations.
# Depends on $script:Cfg and on Influence.ps1.

# ---- JSON helpers ----------------------------------------------------------

function Read-Json {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $null }
    $raw = Get-Content -Path $Path -Raw -Encoding UTF8
    if (-not $raw) { return $null }
    return ($raw | ConvertFrom-Json)
}

function Write-Json {
    param($Obj, [string]$Path)
    $dir = Split-Path $Path -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $Obj | ConvertTo-Json -Depth 6 | Set-Content -Path $Path -Encoding UTF8
}

# ---- Path helpers ----------------------------------------------------------

function Get-EntriesDir { Join-Path $script:Cfg.DataRoot 'entries' }
function Get-EntryPath  { param([int]$Id)    Join-Path (Get-EntriesDir) ("{0}.json" -f $Id) }
function Get-UserPath   { param([string]$Id) Join-Path (Join-Path $script:Cfg.DataRoot 'users') ("{0}.json" -f $Id) }

# ---- Entries ---------------------------------------------------------------

function Get-AllEntries {
    $dir = Get-EntriesDir
    if (-not (Test-Path $dir)) { return @() }
    @(Get-ChildItem -Path $dir -Filter '*.json' |
        Where-Object { $_.Name -match '^\d+\.json$' } |
        ForEach-Object { Read-Json $_.FullName })
}

function Get-Entry  { param([int]$Id) Read-Json (Get-EntryPath $Id) }
function Save-Entry { param($Entry)  Write-Json $Entry (Get-EntryPath ([int]$Entry.id)) }

# ---- Users -----------------------------------------------------------------

function Get-User {
    param([string]$Id, [string]$DisplayName)
    $p = Get-UserPath $Id
    $u = Read-Json $p
    if (-not $u) {
        $u = [pscustomobject]@{
            id                 = $Id
            display_name       = $DisplayName
            influence          = $script:Cfg.StartingInfluence
            last_login         = $null
            return_bonus_total = 0
        }
        Write-Json $u $p
    }
    return $u
}

function Save-User { param($User) Write-Json $User (Get-UserPath $User.id) }

# ---- Counter ---------------------------------------------------------------

function Get-NextId {
    $p = Join-Path $script:Cfg.DataRoot 'counters.json'
    $c = Read-Json $p
    if (-not $c) { $c = [pscustomobject]@{ next_entry_id = 1 } }
    $id = [int]$c.next_entry_id
    $c.next_entry_id = $id + 1
    Write-Json $c $p
    return $id
}

# ---- Search ----------------------------------------------------------------
# Broad by design: matches ANY query word across title + body (a false "no results"
# would cause duplicate entries). Ranks by how many words matched. Narrow in the grid.
function Search-Entries {
    param([string]$Term)
    $t = $Term.Trim()
    if (-not $t) { return @() }
    $words = @($t -split '\s+' | Where-Object { $_ -ne '' })
    $results = foreach ($e in (Get-AllEntries)) {
        $combined = "$($e.title) `n $($e.body)"
        $hits = 0
        foreach ($w in $words) { if ($combined -like "*$w*") { $hits++ } }
        if ($hits -gt 0) {
            $inTitle = $false
            foreach ($w in $words) { if ($e.title -like "*$w*") { $inTitle = $true; break } }
            [pscustomobject]@{
                id      = [int]$e.id
                title   = $e.title
                tag     = (Get-DisplayTag $e)
                cost    = (Get-AccessCost $e)
                updated = $e.updated
                cited   = if ($e.PSObject.Properties['cited_by'] -and $e.cited_by) { [string]$e.cited_date } else { '' }
                where   = if ($inTitle) { 'title' } else { 'body' }
                hits    = $hits
            }
        }
    }
    @($results | Sort-Object @{ Expression = { - $_.hits } }, @{ Expression = { $_.where -ne 'title' } }, title)
}

# ---- Validations list helpers ----------------------------------------------

function Get-Validations {
    param($Entry)
    if ($Entry.PSObject.Properties['validations'] -and $Entry.validations) { return @($Entry.validations) }
    if ($Entry.PSObject.Properties['validated_by'] -and $Entry.validated_by) {
        return @([pscustomobject]@{ by = $Entry.validated_by; date = $Entry.validated_date })
    }
    return @()
}

function Set-Validations {
    param($Entry, $List)
    if ($Entry.PSObject.Properties['validations']) { $Entry.validations = $List }
    else { $Entry | Add-Member -NotePropertyName validations -NotePropertyValue $List -Force }
}

function Set-EntryProp {
    param($Entry, [string]$Name, $Value)
    if ($Entry.PSObject.Properties[$Name]) { $Entry.$Name = $Value }
    else { $Entry | Add-Member -NotePropertyName $Name -NotePropertyValue $Value -Force }
}

# ---- The four contribution actions ----------------------------------------

function New-Entry {
    param([string]$Title, [string]$Body, $User)
    $e = [pscustomobject]@{
        id          = (Get-NextId)
        title       = $Title
        body        = $Body
        tag         = 'submitted'
        cited_by    = $null
        cited_date  = $null
        version     = 1
        author      = $User.display_name
        updated     = (Get-Date).ToString('yyyy-MM-dd')
        validations = @()
    }
    Save-Entry $e
    Add-Influence $User 3
    return $e
}

function Update-Entry {
    param($Entry, [string]$Title, [string]$Body, $User)
    $verPath = Join-Path (Get-EntriesDir) ("{0}.v{1}.json" -f [int]$Entry.id, [int]$Entry.version)
    Write-Json $Entry $verPath          # archive current version

    $Entry.title    = $Title
    $Entry.body     = $Body
    $Entry.tag      = 'submitted'       # trust resets on improvement
    Set-EntryProp $Entry 'cited_by'   $null   # citation resolved by the improvement
    Set-EntryProp $Entry 'cited_date' $null
    $Entry.version  = [int]$Entry.version + 1
    $Entry.author   = $User.display_name
    $Entry.updated  = (Get-Date).ToString('yyyy-MM-dd')
    Set-Validations $Entry @()
    Save-Entry $Entry
    Add-Influence $User 3
    return $Entry
}

# Additive: appends a validation. Returns $null if this user already validated it.
function Confirm-Entry {
    param($Entry, $User)
    $vals = Get-Validations $Entry
    if ($vals | Where-Object { $_.by -eq $User.display_name }) { return $null }
    $today = (Get-Date).ToString('yyyy-MM-dd')
    $vals  = @($vals) + [pscustomobject]@{ by = $User.display_name; date = $today }
    Set-Validations $Entry $vals
    if ($Entry.tag -eq 'submitted') { $Entry.tag = 'tested' }
    $Entry.updated = $today
    Save-Entry $Entry
    Add-Influence $User 5
    return $Entry
}

# Free (no reward) to avoid farming a one-click action.
function Set-Citation {
    param($Entry, $User)
    Set-EntryProp $Entry 'cited_by'   $User.display_name
    Set-EntryProp $Entry 'cited_date' (Get-Date).ToString('yyyy-MM-dd')
    Save-Entry $Entry
    return $Entry
}

function Clear-Citation {
    param($Entry, $User)
    Set-EntryProp $Entry 'cited_by'   $null
    Set-EntryProp $Entry 'cited_date' $null
    Save-Entry $Entry
    return $Entry
}

# ---- Version history -------------------------------------------------------

function Get-PriorVersions {
    param([int]$Id)
    @(Get-ChildItem -Path (Get-EntriesDir) -Filter ("{0}.v*.json" -f $Id) -ErrorAction SilentlyContinue |
        Sort-Object Name |
        ForEach-Object { Read-Json $_.FullName })
}

# ---- Tools -----------------------------------------------------------------

function Get-Tools {
    $dir = Join-Path $script:Cfg.DataRoot 'tools'
    if (-not (Test-Path $dir)) { return @() }
    @(Get-ChildItem -Path $dir -Filter '*.json' | ForEach-Object { Read-Json $_.FullName })
}

function Get-ToolCost {
    param($Tool)
    $base = [int]$Tool.access_cost_base
    $days = 0
    if ($Tool.backing_entry_id) {
        $e = Get-Entry ([int]$Tool.backing_entry_id)
        if ($e) { $d = Get-DaysSinceValidation $e; if ($null -ne $d) { $days = $d } }
    }
    $cost = $base + [math]::Floor($days / $script:Cfg.CostPerDays)
    return [int][math]::Min($script:Cfg.CostCap, [math]::Max(1, $cost))
}
