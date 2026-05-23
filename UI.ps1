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

# UI.ps1
# Presentation surfaces (CLI + WinForms) and shared GUI helpers. No business logic.

$script:Rule = ('-' * 60)

# Win32 helper so the console regains focus after a dialog closes (fixes "frozen menu").
try {
    if (-not ('WinFocus' -as [type])) {
        Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinFocus {
    [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
    [DllImport("user32.dll")]   public static extern bool SetForegroundWindow(IntPtr hWnd);
}
"@
    }
} catch { }

function Set-ConsoleForeground {
    try { [void][WinFocus]::SetForegroundWindow([WinFocus]::GetConsoleWindow()) } catch { }
}

function Initialize-Gui {
    if ($script:GuiReady) { return $true }
    try {
        Add-Type -AssemblyName System.Windows.Forms | Out-Null
        Add-Type -AssemblyName System.Drawing | Out-Null
        [System.Windows.Forms.Application]::EnableVisualStyles()
        $script:GuiReady = $true
    } catch { $script:GuiReady = $false }
    return $script:GuiReady
}

# Hidden topmost form used as a dialog owner so message boxes come to the front.
function New-TopmostOwner {
    $o = New-Object System.Windows.Forms.Form
    $o.TopMost = $true; $o.ShowInTaskbar = $false
    $o.StartPosition = 'CenterScreen'
    $o.Size = New-Object System.Drawing.Size(1, 1)
    $o.Opacity = 0
    $o.Show(); $o.Activate(); $o.Hide()
    return $o
}

# Modal OK notice (replaces the too-fast green flash). CLI fallback waits for Enter.
function Show-Notice {
    param([string]$Message, [string]$Kind = 'info')   # info | warn
    if (Initialize-Gui) {
        $icon = if ($Kind -eq 'warn') { [System.Windows.Forms.MessageBoxIcon]::Warning } else { [System.Windows.Forms.MessageBoxIcon]::Information }
        $owner = New-TopmostOwner
        [void][System.Windows.Forms.MessageBox]::Show($owner, $Message, 'EscalationCache', [System.Windows.Forms.MessageBoxButtons]::OK, $icon)
        $owner.Dispose()
        Set-ConsoleForeground
        return
    }
    Write-Host ""
    Write-Host $Message -ForegroundColor $(if ($Kind -eq 'warn') { 'Yellow' } else { 'Green' })
    Read-Host "(press Enter)" | Out-Null
}

function Read-Title {
    param([string]$Default)
    $label = if ($Default) { "Title [$Default]" } else { "Title" }
    $val = Read-Host $label
    if (-not $val) { return $Default }
    return $val
}

# Generic Yes/No confirm with nicer framing; CLI fallback.
function Confirm-Action {
    param([string]$Title, [string]$Message)
    if (Initialize-Gui) {
        $owner = New-TopmostOwner
        $res = [System.Windows.Forms.MessageBox]::Show(
            $owner, $Message, $Title,
            [System.Windows.Forms.MessageBoxButtons]::YesNo,
            [System.Windows.Forms.MessageBoxIcon]::Question)
        $owner.Dispose()
        Set-ConsoleForeground
        return ($res -eq [System.Windows.Forms.DialogResult]::Yes)
    }
    Write-Host ""
    Write-Host $Message -ForegroundColor Yellow
    return ((Read-Host "[Y/N]") -match '^[Yy]')
}

# Yes/No spend confirmation with the balance in the message; CLI fallback.
function Confirm-Spend {
    param([string]$Title, [int]$Cost, [int]$Balance)
    if (Initialize-Gui) {
        $owner = New-TopmostOwner
        $msg = ("Open `"{0}`"?`r`n`r`nCost: {1} influence`r`nYour balance: {2}" -f $Title, $Cost, $Balance)
        $res = [System.Windows.Forms.MessageBox]::Show(
            $owner, $msg, 'Confirm spend',
            [System.Windows.Forms.MessageBoxButtons]::YesNo,
            [System.Windows.Forms.MessageBoxIcon]::Question)
        $owner.Dispose()
        Set-ConsoleForeground
        return ($res -eq [System.Windows.Forms.DialogResult]::Yes)
    }
    Write-Host ("`nOpen `"{0}`" for {1} influence?  (balance {2})" -f $Title, $Cost, $Balance) -ForegroundColor Yellow
    return ((Read-Host "[Y/N]") -match '^[Yy]')
}

# ---- WinForms results picker (filterable, topmost) -------------------------

function Update-PickerList {
    param([string]$Filter)
    $lv = $script:PickerLV
    $lv.BeginUpdate()
    $lv.Items.Clear()
    foreach ($r in $script:PickerResults) {
        if (-not $Filter -or ($r.title -like "*$Filter*")) {
            $it = New-Object System.Windows.Forms.ListViewItem([string]$r.title)
            [void]$it.SubItems.Add([string]$r.tag)
            [void]$it.SubItems.Add([string]$r.cost)
            [void]$it.SubItems.Add([string]$r.updated)
            [void]$it.SubItems.Add([string]$r.cited)
            $it.Tag = $r.id
            [void]$lv.Items.Add($it)
        }
    }
    if ($lv.Items.Count -gt 0) { $lv.Items[0].Selected = $true; $lv.Items[0].Focused = $true }
    $lv.EndUpdate()
}

function Show-EntryPicker {
    param($Results)
    if (-not (Initialize-Gui)) { return (Show-ResultsCli -Results $Results) }
    try {
        $script:PickerResults = $Results

        $form = New-Object System.Windows.Forms.Form
        $form.Text = 'Search results'
        $form.Size = New-Object System.Drawing.Size(760, 470)
        $form.StartPosition = 'CenterScreen'
        $form.TopMost = $true

        $lbl = New-Object System.Windows.Forms.Label
        $lbl.Text = 'Filter:'; $lbl.AutoSize = $true
        $lbl.Location = New-Object System.Drawing.Point(12, 15)
        $form.Controls.Add($lbl)

        $txt = New-Object System.Windows.Forms.TextBox
        $txt.Location = New-Object System.Drawing.Point(62, 12)
        $txt.Size = New-Object System.Drawing.Size(670, 22)
        $txt.Anchor = ([System.Windows.Forms.AnchorStyles]::Top -bor [System.Windows.Forms.AnchorStyles]::Left -bor [System.Windows.Forms.AnchorStyles]::Right)
        $form.Controls.Add($txt)

        $lv = New-Object System.Windows.Forms.ListView
        $lv.Location = New-Object System.Drawing.Point(12, 44)
        $lv.Size = New-Object System.Drawing.Size(720, 340)
        $lv.View = 'Details'; $lv.FullRowSelect = $true; $lv.MultiSelect = $false; $lv.HideSelection = $false
        $lv.Anchor = ([System.Windows.Forms.AnchorStyles]::Top -bor [System.Windows.Forms.AnchorStyles]::Bottom -bor [System.Windows.Forms.AnchorStyles]::Left -bor [System.Windows.Forms.AnchorStyles]::Right)
        [void]$lv.Columns.Add('Title', 300)
        [void]$lv.Columns.Add('Trust Tier', 95)
        [void]$lv.Columns.Add('Influence', 70)
        [void]$lv.Columns.Add('Updated', 90)
        [void]$lv.Columns.Add('Citation Requested', 125)
        $form.Controls.Add($lv)
        $script:PickerLV = $lv

        $btnOpen = New-Object System.Windows.Forms.Button
        $btnOpen.Text = 'Open'; $btnOpen.Size = New-Object System.Drawing.Size(90, 30)
        $btnOpen.Location = New-Object System.Drawing.Point(538, 396)
        $btnOpen.Anchor = ([System.Windows.Forms.AnchorStyles]::Bottom -bor [System.Windows.Forms.AnchorStyles]::Right)
        $btnOpen.DialogResult = [System.Windows.Forms.DialogResult]::OK
        $form.Controls.Add($btnOpen)

        $btnCancel = New-Object System.Windows.Forms.Button
        $btnCancel.Text = 'Cancel'; $btnCancel.Size = New-Object System.Drawing.Size(90, 30)
        $btnCancel.Location = New-Object System.Drawing.Point(638, 396)
        $btnCancel.Anchor = ([System.Windows.Forms.AnchorStyles]::Bottom -bor [System.Windows.Forms.AnchorStyles]::Right)
        $btnCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
        $form.Controls.Add($btnCancel)

        $form.AcceptButton = $btnOpen
        $form.CancelButton = $btnCancel

        $txt.Add_TextChanged({ Update-PickerList -Filter $this.Text })
        $lv.Add_DoubleClick({ $btnOpen.PerformClick() })
        $form.Add_Shown({ $form.Activate(); $txt.Focus() })

        Update-PickerList -Filter ''
        $result = $form.ShowDialog()

        $selId = $null
        if ($result -eq [System.Windows.Forms.DialogResult]::OK -and $lv.SelectedItems.Count -gt 0) {
            $selId = $lv.SelectedItems[0].Tag
        }
        $form.Dispose()
        Set-ConsoleForeground
        if ($null -ne $selId) {
            return ($Results | Where-Object { $_.id -eq [int]$selId } | Select-Object -First 1)
        }
        return $null
    } catch {
        return (Show-ResultsCli -Results $Results)
    }
}

function Show-ResultsCli {
    param($Results)
    Clear-Host
    Write-Host ("Results ({0})" -f $Results.Count)
    Write-Host $script:Rule
    for ($i = 0; $i -lt $Results.Count; $i++) {
        $r = $Results[$i]
        Write-Host ("{0,2}. {1}" -f ($i + 1), $r.title)
        $cz = if ($r.cited) { $r.cited } else { '-' }
        Write-Host ("     [{0}]   influence {1}   updated {2}   citation {3}   matched in {4}" -f $r.tag, $r.cost, $r.updated, $cz, $r.where) -ForegroundColor DarkGray
    }
    Write-Host $script:Rule
    $sel = Read-Host "number to open, or Enter to cancel"
    if ($sel -match '^\d+$') {
        $idx = [int]$sel - 1
        if ($idx -ge 0 -and $idx -lt $Results.Count) { return $Results[$idx] }
    }
    return $null
}

# Static (non-interactive) detail fallback. Returns an action string.
function Show-DetailStatic {
    param($Entry)
    Clear-Host
    $tag = Get-DisplayTag $Entry
    Write-Host $Entry.title
    Write-Host ("{0}  .  v{1}  .  {2}  .  updated {3}" -f $tag, $Entry.version, $Entry.author, $Entry.updated) -ForegroundColor DarkGray
    if ($Entry.cited_by) {
        $cd = if ($Entry.PSObject.Properties['cited_date'] -and $Entry.cited_date) { " on $($Entry.cited_date)" } else { "" }
        Write-Host ("Citation requested by {0}{1} - improve this contribution to help clarify" -f $Entry.cited_by, $cd) -ForegroundColor Yellow
    }
    $vals = Get-Validations $Entry
    if ($vals.Count -eq 0) { Write-Host "not yet validated" -ForegroundColor DarkGray }
    else { foreach ($v in $vals) { Write-Host ("validated by {0} on {1}" -f $v.by, $v.date) -ForegroundColor DarkGray } }
    Write-Host $script:Rule
    foreach ($line in ($Entry.body -split "`n")) { Write-Host $line }
    Write-Host $script:Rule
    Write-Host " [I] Improve   [C] Citation Request   [V] Validate   [H] History   [B] Back"
    switch -Regex (Read-Host ">") {
        '^[Ii]$' { return 'improve' }
        '^[Vv]$' { return 'validate' }
        '^[Cc]$' { return 'citation' }
        '^[Hh]$' { return 'history' }
        default  { return 'back' }
    }
}

function Show-Tools {
    param($Tools)
    Clear-Host
    Write-Host "Tools"
    Write-Host $script:Rule
    if (-not $Tools -or $Tools.Count -eq 0) {
        Write-Host " (none seeded)"
    } else {
        for ($i = 0; $i -lt $Tools.Count; $i++) {
            $t = $Tools[$i]
            Write-Host ("{0,2}. {1}   cost {2}" -f ($i + 1), $t.name, (Get-ToolCost $t))
            Write-Host ("     {0}" -f $t.description) -ForegroundColor DarkGray
        }
    }
    Write-Host $script:Rule
    Write-Host " [#] Run      [Esc] Back" -ForegroundColor DarkGray
}
