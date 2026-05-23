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

# Checklist.ps1  (optional)
# The combined interactive detail view: header + validations + checkable steps + actions.
# -ReadOnly hides the actions (used for viewing prior versions). Requires a real console host.
# Delete this file and Invoke-DetailFlow falls back to Show-DetailStatic.

function ConvertTo-ChecklistItems {
    param([string]$Body)
    $items = New-Object System.Collections.ArrayList
    foreach ($l in ($Body -split "`n")) {
        $m = [regex]::Match($l, '^\s*-\s*\[( |x|X)\]\s?(.*)$')
        if ($m.Success) {
            [void]$items.Add([pscustomobject]@{ IsBox = $true;  Checked = ($m.Groups[1].Value -match '[xX]'); Text = $m.Groups[2].Value })
        } else {
            [void]$items.Add([pscustomobject]@{ IsBox = $false; Checked = $false; Text = $l })
        }
    }
    return $items
}

function Render-ChecklistBlock {
    param($Items, $BoxIdx, [int]$Cur, [int]$BaseRow)
    $width = [math]::Max(1, [Console]::WindowWidth - 1)
    for ($i = 0; $i -lt $Items.Count; $i++) {
        [Console]::SetCursorPosition(0, $BaseRow + $i)
        $it = $Items[$i]
        if ($it.IsBox) {
            $isSel  = ($BoxIdx.Count -gt 0 -and $BoxIdx[$Cur] -eq $i)
            $cursor = if ($isSel) { '>' } else { ' ' }
            $mark   = if ($it.Checked) { '[x]' } else { '[ ]' }
            $line   = ("{0} {1} {2}" -f $cursor, $mark, $it.Text).PadRight($width)
            if ($isSel) { Write-Host $line -ForegroundColor Cyan -NoNewline }
            else        { Write-Host $line -NoNewline }
        } else {
            Write-Host (("    {0}" -f $it.Text).PadRight($width)) -ForegroundColor DarkGray -NoNewline
        }
    }
}

# Renders the entry. Returns improve|validate|citation|history|back.
# In -ReadOnly mode only space/Esc are active and only 'back' is returned.
function Show-DetailInteractive {
    param($Entry, [switch]$ReadOnly)
    $arr = ([char]0x2191).ToString() + ([char]0x2193).ToString()   # up/down arrows
    $items  = ConvertTo-ChecklistItems -Body $Entry.body
    $boxIdx = @()
    for ($i = 0; $i -lt $items.Count; $i++) { if ($items[$i].IsBox) { $boxIdx += $i } }

    try {
        Clear-Host
        $tag = Get-DisplayTag $Entry
        $titlePrefix = if ($ReadOnly) { "(prior version) " } else { "" }
        Write-Host ($titlePrefix + $Entry.title)
        Write-Host ("{0}  .  v{1}  .  {2}  .  updated {3}" -f $tag, $Entry.version, $Entry.author, $Entry.updated) -ForegroundColor DarkGray
        if ($Entry.cited_by) {
            $cd = if ($Entry.PSObject.Properties['cited_date'] -and $Entry.cited_date) { " on $($Entry.cited_date)" } else { "" }
            Write-Host ("Citation requested by {0}{1} - improve this contribution to help clarify" -f $Entry.cited_by, $cd) -ForegroundColor Yellow
        }
        $vals = Get-Validations $Entry
        if ($vals.Count -eq 0) { Write-Host "not yet validated" -ForegroundColor DarkGray }
        else { foreach ($v in $vals) { Write-Host ("validated by {0} on {1}" -f $v.by, $v.date) -ForegroundColor DarkGray } }
        Write-Host ('-' * 60)

        $baseRow = [Console]::CursorTop
        $cur = 0
        Render-ChecklistBlock -Items $items -BoxIdx $boxIdx -Cur $cur -BaseRow $baseRow

        [Console]::SetCursorPosition(0, $baseRow + $items.Count)
        Write-Host ('-' * 60)
        if ($ReadOnly) {
            Write-Host (" [$arr] Move    [Space] Check Off Step    [Esc] Back") -ForegroundColor DarkGray
        } else {
            Write-Host (" [$arr] Move   [Space] Check Off Step   [I]mprove   [C]itation Request   [V]alidate   [H]istory   [Esc] Back") -ForegroundColor DarkGray
        }

        while ($true) {
            $key = [Console]::ReadKey($true)
            switch ($key.Key) {
                'UpArrow'   { if ($boxIdx.Count -gt 0 -and $cur -gt 0)                 { $cur--; Render-ChecklistBlock -Items $items -BoxIdx $boxIdx -Cur $cur -BaseRow $baseRow } }
                'DownArrow' { if ($boxIdx.Count -gt 0 -and $cur -lt $boxIdx.Count - 1) { $cur++; Render-ChecklistBlock -Items $items -BoxIdx $boxIdx -Cur $cur -BaseRow $baseRow } }
                'Spacebar'  { if ($boxIdx.Count -gt 0) { $i = $boxIdx[$cur]; $items[$i].Checked = -not $items[$i].Checked; Render-ChecklistBlock -Items $items -BoxIdx $boxIdx -Cur $cur -BaseRow $baseRow } }
                'I'         { if (-not $ReadOnly) { return 'improve' } }
                'V'         { if (-not $ReadOnly) { return 'validate' } }
                'C'         { if (-not $ReadOnly) { return 'citation' } }
                'H'         { if (-not $ReadOnly) { return 'history' } }
                'Escape'    { return 'back' }
            }
        }
    } catch {
        return (Show-DetailStatic -Entry $Entry)
    }
}
