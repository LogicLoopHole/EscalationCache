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

# EscalationCache.ps1  -- alpha entry point
# Run from a real console host (conhost / Windows Terminal), NOT the ISE:
#   powershell -ExecutionPolicy Bypass -File .\EscalationCache.ps1
# There is no Quit command; close the window (or Ctrl+C) to exit.

# ---- Config (tune the economy here) ----------------------------------------
$script:Cfg = @{
    DataRoot            = (Join-Path $PSScriptRoot 'data')
    StartingInfluence   = 5
    ReturnBonus         = 1
    ReturnBonusIdleDays = 7
    ReturnBonusCap      = 10
    StaleAfterDays      = 180
    CostCap             = 8
    CostPerDays         = 60
    BaseCost            = @{ submitted = 1; tested = 2; approved = 1; superseded = 1; stale = 2 }
    UseWinFormsEditor   = $true   # set $false to force the Notepad editor
}

# ---- Load libraries (core first, optional last) ----------------------------
. (Join-Path $PSScriptRoot 'Influence.ps1')
. (Join-Path $PSScriptRoot 'Entries.ps1')
. (Join-Path $PSScriptRoot 'UI.ps1')
if (Test-Path (Join-Path $PSScriptRoot 'Editor.ps1'))    { . (Join-Path $PSScriptRoot 'Editor.ps1') }
if (Test-Path (Join-Path $PSScriptRoot 'Checklist.ps1')) { . (Join-Path $PSScriptRoot 'Checklist.ps1') }

# Last-resort editor if Editor.ps1 was deleted entirely.
if (-not (Get-Command Invoke-BodyEditor -ErrorAction SilentlyContinue)) {
    function Invoke-BodyEditor {
        param([string]$SeedText = '', [string]$Title = 'Contribution body')
        $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("ec_{0}.txt" -f ([guid]::NewGuid().ToString('N')))
        Set-Content -Path $tmp -Value $SeedText -Encoding UTF8
        Start-Process -FilePath notepad.exe -ArgumentList $tmp -Wait
        $c = ''
        if (Test-Path $tmp) { $c = Get-Content -Path $tmp -Raw -Encoding UTF8; Remove-Item $tmp -ErrorAction SilentlyContinue }
        if ($null -eq $c) { return '' }
        $c = $c -replace "`r`n", "`n" -replace "`r", "`n"
        return ($c -replace '\s+$', '')
    }
}

# ---- Seed data (first run only) --------------------------------------------
function Initialize-SeedData {
    if ((Get-AllEntries).Count -gt 0) { return }

    # Dates relative to today so cost shows a real fresh->stale spread.
    # Entry 4 is validated long ago, so 'stale' and its high cost are *computed*.
    $ago = { param([int]$n) (Get-Date).AddDays(-$n).ToString('yyyy-MM-dd') }

    $seed = @(
        [pscustomobject]@{
            id = 1; title = 'SCCM app deployment fails silently on VPN'
            body = (@(
                '- [ ] Disconnect VPN before initiating deployment',
                '- [ ] Run deployment from Software Center manually',
                '- [ ] Reconnect VPN once installation reaches downloading state',
                '- [ ] If still failing: run ccmrepair.exe') -join "`n")
            tag = 'approved'; cited_by = $null; version = 2; author = 'K. Marsh'
            updated = (& $ago 10); validations = @([pscustomobject]@{ by = 'K. Marsh'; date = (& $ago 10) })
        },
        [pscustomobject]@{
            id = 2; title = 'Outlook search empty after mailbox migration'
            body = (@(
                '- [ ] Open Indexing Options',
                '- [ ] Remove and re-add Outlook data store',
                '- [ ] Allow index to rebuild',
                '- [ ] Restart Outlook') -join "`n")
            tag = 'tested'; cited_by = 'R. Vasquez'; cited_date = (& $ago 60); version = 1; author = 'D. Okafor'
            updated = (& $ago 90); validations = @([pscustomobject]@{ by = 'D. Okafor'; date = (& $ago 90) })
        },
        [pscustomobject]@{
            id = 3; title = 'Teams audio drops on docked Surface devices'
            body = (@(
                '- [ ] Set dock as default comms device',
                '- [ ] Pin dock audio in Teams devices',
                '- [ ] Disable exclusive control for dock audio') -join "`n")
            tag = 'submitted'; cited_by = $null; version = 1; author = 'R. Vasquez'
            updated = (& $ago 3); validations = @()
        },
        [pscustomobject]@{
            id = 4; title = 'Printer spooler crash after KB5034441'
            body = (@(
                '- [ ] net stop spooler',
                '- [ ] Clear the PRINTERS spool folder',
                '- [ ] Reinstall affected printer drivers',
                '- [ ] net start spooler') -join "`n")
            tag = 'tested'; cited_by = $null; version = 1; author = 'T. Nguyen'
            updated = (& $ago 400); validations = @([pscustomobject]@{ by = 'T. Nguyen'; date = (& $ago 400) })
        }
    )
    foreach ($e in $seed) { Save-Entry $e }
    Write-Json ([pscustomobject]@{ next_entry_id = 5 }) (Join-Path $script:Cfg.DataRoot 'counters.json')

    $tool = [pscustomobject]@{
        id = 'app-installer'; name = 'App Installer (SCCM wrapper)'
        description = 'Runs SCCM deployment command with correct flags and logs usage.'
        access_cost_base = 3; backing_entry_id = 1
    }
    Write-Json $tool (Join-Path (Join-Path $script:Cfg.DataRoot 'tools') 'app-installer.json')
}

# ---- Small helpers ---------------------------------------------------------
# Modal OK notice (was a fast green flash). Color maps to icon kind.
function Show-Flash {
    param([string]$Message, [string]$Color = 'Green')
    $kind = if ($Color -eq 'Red' -or $Color -eq 'Yellow') { 'warn' } else { 'info' }
    Show-Notice -Message $Message -Kind $kind
}

# Body first, then a terminal preview, then the title (titled as a summary of the work).
# Returns @{ title; body } or $null if the editor was cancelled.
function Read-Contribution {
    param([string]$SeedBody = '', [string]$DefaultTitle = '', [string]$EditorTitle = 'Contribution')
    $body = Invoke-BodyEditor -SeedText $SeedBody -Title $EditorTitle
    if ($null -eq $body) { return $null }
    Clear-Host
    Write-Host "Preview - review your write-up, then give it a title" -ForegroundColor DarkGray
    Write-Host ('-' * 60)
    if ([string]::IsNullOrWhiteSpace($body)) { Write-Host "(empty)" -ForegroundColor DarkGray }
    else { foreach ($l in ($body -split "`n")) { Write-Host $l } }
    Write-Host ('-' * 60)
    $title = Read-Title -Default $DefaultTitle
    return [pscustomobject]@{ title = $title; body = $body }
}

# ---- Flows -----------------------------------------------------------------

function Open-Entry {
    param($User, [int]$Id)
    $entry = Get-Entry $Id
    if (-not $entry) { return }
    $cost = Get-AccessCost $entry
    if (-not (Confirm-Spend -Title $entry.title -Cost $cost -Balance $User.influence)) { return }
    if (-not (Use-Influence $User $cost)) {
        Show-Flash "Not enough influence." 'Red'; return
    }
    Invoke-DetailFlow -User $User -Entry $entry
}

function Invoke-DetailFlow {
    param($User, $Entry)
    $interactive = [bool](Get-Command Show-DetailInteractive -ErrorAction SilentlyContinue)
    while ($true) {
        $Entry = Get-Entry $Entry.id
        if (-not $Entry) { return }
        $action = if ($interactive) { Show-DetailInteractive -Entry $Entry } else { Show-DetailStatic -Entry $Entry }
        switch ($action) {
            'improve' {
                $c = Read-Contribution -SeedBody $Entry.body -DefaultTitle $Entry.title -EditorTitle 'Improve - edit the fix, then re-title'
                if ($null -ne $c) {
                    Update-Entry -Entry $Entry -Title $c.title -Body $c.body -User $User | Out-Null
                    Show-Flash "Improved (+3). Contribution set to submitted."
                }
            }
            'validate' {
                if (Get-Validations $Entry | Where-Object { $_.by -eq $User.display_name }) {
                    Show-Flash "You have already validated this." 'Yellow'
                } elseif (Confirm-Action -Title 'Go on record' -Message "Validating adds your name and today's date to this entry, vouching that this fix works. That is what makes it trustworthy for the next person.`r`n`r`nReady to go on record?") {
                    $r = Confirm-Entry -Entry $Entry -User $User
                    if ($null -eq $r) { Show-Flash "You have already validated this." 'Yellow' }
                    else              { Show-Flash "Validated (+5). Your name is on record." }
                }
            }
            'citation' {
                if ($Entry.cited_by -eq $User.display_name) {
                    Clear-Citation -Entry $Entry -User $User | Out-Null
                    Show-Flash "Citation request cleared."
                } elseif ($Entry.cited_by) {
                    Show-Flash ("Already flagged by {0}." -f $Entry.cited_by) 'Yellow'
                } elseif (Confirm-Action -Title 'Request a citation' -Message "A citation request flags that something here looks unverified or inaccurate, so the next person knows to double-check - and it nudges someone to improve it. Information ages; this keeps it honest.`r`n`r`nDo you have a specific concern to flag?") {
                    Set-Citation -Entry $Entry -User $User | Out-Null
                    Show-Flash "Citation requested."
                }
            }
            'history' { Invoke-HistoryFlow -User $User -Entry $Entry }
            'back'    { return }
        }
    }
}

function Invoke-HistoryFlow {
    param($User, $Entry)
    $vers = @(Get-PriorVersions -Id $Entry.id)
    if ($vers.Count -eq 0) { Show-Flash "No prior versions." 'Yellow'; return }
    Clear-Host
    Write-Host ("History: {0}" -f $Entry.title)
    Write-Host ('-' * 60)
    for ($i = 0; $i -lt $vers.Count; $i++) {
        Write-Host ("{0,2}. v{1}   {2}   {3}   [{4}]   cost {5}" -f ($i + 1), $vers[$i].version, $vers[$i].author, $vers[$i].updated, $vers[$i].tag, (Get-AccessCost $vers[$i]))
    }
    Write-Host ('-' * 60)
    Write-Host "viewing a prior version costs influence based on its age"
    $sel = Read-Host "number to view, or Enter to go back"
    if ($sel -match '^\d+$') {
        $idx = [int]$sel - 1
        if ($idx -ge 0 -and $idx -lt $vers.Count) {
            $v = $vers[$idx]
            $vcost = Get-AccessCost $v
            if (Confirm-Spend -Title ("v{0} (prior) of {1}" -f $v.version, $Entry.title) -Cost $vcost -Balance $User.influence) {
                if (Use-Influence $User $vcost) {
                    if (Get-Command Show-DetailInteractive -ErrorAction SilentlyContinue) {
                        [void](Show-DetailInteractive -Entry $v -ReadOnly)
                    } else {
                        Clear-Host
                        Write-Host ("(prior version) v{0}  .  {1}  .  {2}" -f $v.version, $v.author, $v.updated) -ForegroundColor DarkGray
                        Write-Host ('-' * 60)
                        foreach ($l in ($v.body -split "`n")) { Write-Host $l }
                        Write-Host ('-' * 60)
                        Read-Host "press Enter to return" | Out-Null
                    }
                } else { Show-Flash "Not enough influence." 'Red' }
            }
        }
    }
}

function Invoke-PioneerFlow {
    param($User, [string]$SeedTitle)
    $c = Read-Contribution -SeedBody '' -DefaultTitle $SeedTitle -EditorTitle 'Pioneer - write the fix, then title it'
    if ($null -eq $c) { Show-Flash "Cancelled." 'Yellow'; return }
    $e = New-Entry -Title $c.title -Body $c.body -User $User
    Show-Flash ("Contributed `"{0}`" (+3)." -f $e.title)
}

function Invoke-ToolsFlow {
    param($User)
    while ($true) {
        $tools = @(Get-Tools)
        Show-Tools -Tools $tools
        $choice = $null
        try {
            $k = [Console]::ReadKey($true)
            if ($k.Key -eq 'Escape') { return }
            $choice = [string]$k.KeyChar
        } catch {
            $choice = Read-Host "number, or B to go back"
            if ($choice -match '^[Bb]$') { return }
        }
        if ($choice -match '^\d$') {
            $idx = [int]$choice - 1
            if ($idx -ge 0 -and $idx -lt $tools.Count) {
                $t = $tools[$idx]; $cost = Get-ToolCost $t
                if (Confirm-Spend -Title $t.name -Cost $cost -Balance $User.influence) {
                    if (Use-Influence $User $cost) {
                        Clear-Host
                        Write-Host ("Running: {0} ..." -f $t.name) -ForegroundColor Green
                        Start-Sleep 1
                        Write-Host "(alpha) tool execution is simulated." -ForegroundColor DarkGray
                        Write-Host "press any key to continue" -ForegroundColor DarkGray
                        try { [void][Console]::ReadKey($true) } catch { Read-Host | Out-Null }
                    } else { Show-Flash "Not enough influence." 'Red' }
                }
            }
        }
    }
}

# ---- Bootstrap + main loop -------------------------------------------------
# Render arrow / box glyphs correctly in the console.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$me = $env:USERNAME
if (-not $me) { $me = 'localuser' }
$User = Get-User -Id $me -DisplayName $me
Initialize-SeedData

$bonus = Grant-ReturnBonus $User
if ($bonus -gt 0) { Show-Flash ("Welcome back - return bonus +{0} influence." -f $bonus) }

while ($true) {
    $User = Get-User -Id $me -DisplayName $me   # reflect any balance change
    Clear-Host
    Write-Host "EscalationCache"
    Write-Host ("influence: {0}" -f $User.influence) -ForegroundColor DarkGray
    $recent = @(Get-AllEntries | Sort-Object { [datetime]$_.updated } -Descending | Select-Object -First 3)
    if ($recent.Count -gt 0) {
        Write-Host ""
        Write-Host " recently contributed" -ForegroundColor DarkGray
        foreach ($r in $recent) { Write-Host ("  . {0}" -f $r.title) -ForegroundColor DarkGray }
    }
    Write-Host ""
    $term = Read-Host "Search (or T for tools)"

    if ($term -match '^[Tt]$') { Invoke-ToolsFlow -User $User; continue }
    if (-not $term -or -not $term.Trim()) { continue }

    $results = @(Search-Entries $term)
    if ($results.Count -eq 0) {
        Write-Host ("No results for `"{0}`"" -f $term) -ForegroundColor Yellow
        if ((Read-Host "pioneer this? [Y/N]") -match '^[Yy]') { Invoke-PioneerFlow -User $User -SeedTitle $term }
        continue
    }

    # Grid picker, then open one entry. Backing out of it returns to the search landing.
    $picked = Show-EntryPicker -Results $results
    if ($picked) { Open-Entry -User $User -Id $picked.id }
}
