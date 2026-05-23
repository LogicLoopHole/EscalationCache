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

# Editor.ps1  (spike)
# Body input behind a single swappable contract:
#   Invoke-BodyEditor [-SeedText <string>] -> final string (LF), or $null on cancel.

function Invoke-BodyEditor {
    param([string]$SeedText = '', [string]$Title = 'Contribution body')

    $useWinForms = $true
    if ($script:Cfg -and $script:Cfg.ContainsKey('UseWinFormsEditor')) {
        $useWinForms = $script:Cfg.UseWinFormsEditor
    }

    if ($useWinForms) {
        try {
            return (Show-WinFormsEditor -SeedText $SeedText -Title $Title)
        } catch {
            Write-Host ("WinForms editor failed ({0}) - using Notepad instead." -f $_.Exception.Message) -ForegroundColor Yellow
            Start-Sleep -Milliseconds 1500
        }
    }
    return (Invoke-NotepadEditor -SeedText $SeedText)
}

function Show-WinFormsEditor {
    param([string]$SeedText = '', [string]$Title = 'Contribution body')

    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    try { [System.Windows.Forms.Application]::EnableVisualStyles() } catch { }

    # A multiline TextBox renders breaks only on CRLF; expand stored LF for display.
    $display = ($SeedText -replace "`r`n", "`n") -replace "`n", "`r`n"

    $form = New-Object System.Windows.Forms.Form
    $form.Text          = $Title
    $form.Size          = New-Object System.Drawing.Size(660, 600)
    $form.StartPosition = 'CenterScreen'
    $form.MinimumSize   = New-Object System.Drawing.Size(440, 380)
    $form.TopMost       = $true

    # --- Top row: the step button and a hint ---
    $btnStep = New-Object System.Windows.Forms.Button
    $btnStep.Text     = 'Add Check-off Step'
    $btnStep.Size     = New-Object System.Drawing.Size(150, 30)
    $btnStep.Location = New-Object System.Drawing.Point(12, 10)
    $btnStep.Anchor   = ([System.Windows.Forms.AnchorStyles]::Top -bor [System.Windows.Forms.AnchorStyles]::Left)
    # Always begins a new line, so caret position doesn't matter.
    $btnStep.Add_Click({
        $t = $script:EditorTB
        $pos = $t.SelectionStart
        $needNL = ($pos -gt 0 -and $t.Text.Substring($pos - 1, 1) -ne "`n")
        $prefix = if ($needNL) { "`r`n" } else { "" }
        $t.SelectedText = $prefix + '- [ ] '
        $t.Focus()
    })
    $form.Controls.Add($btnStep)

    $hint = New-Object System.Windows.Forms.Label
    $hint.Text     = "adds  - [ ]  on a new line"
    $hint.AutoSize  = $true
    $hint.ForeColor = [System.Drawing.Color]::Gray
    $hint.Location  = New-Object System.Drawing.Point(172, 18)
    $hint.Anchor    = ([System.Windows.Forms.AnchorStyles]::Top -bor [System.Windows.Forms.AnchorStyles]::Left)
    $form.Controls.Add($hint)

    # --- Body ---
    $tb = New-Object System.Windows.Forms.TextBox
    $tb.Multiline    = $true
    $tb.AcceptsReturn = $true
    $tb.AcceptsTab   = $true
    $tb.ScrollBars   = 'Vertical'
    $tb.WordWrap     = $true
    $tb.Font         = New-Object System.Drawing.Font('Consolas', 10)
    $tb.Location     = New-Object System.Drawing.Point(12, 48)
    $tb.Size         = New-Object System.Drawing.Size(628, 458)
    $tb.Anchor       = ([System.Windows.Forms.AnchorStyles]::Top -bor
                         [System.Windows.Forms.AnchorStyles]::Bottom -bor
                         [System.Windows.Forms.AnchorStyles]::Left -bor
                         [System.Windows.Forms.AnchorStyles]::Right)
    $tb.Text         = $display
    $form.Controls.Add($tb)
    $script:EditorTB = $tb

    # --- Bottom row: OK / Cancel ---
    $btnOK = New-Object System.Windows.Forms.Button
    $btnOK.Text         = 'OK'
    $btnOK.Size         = New-Object System.Drawing.Size(90, 32)
    $btnOK.Location     = New-Object System.Drawing.Point(448, 516)
    $btnOK.Anchor       = ([System.Windows.Forms.AnchorStyles]::Bottom -bor [System.Windows.Forms.AnchorStyles]::Right)
    $btnOK.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.Controls.Add($btnOK)

    $btnCancel = New-Object System.Windows.Forms.Button
    $btnCancel.Text         = 'Cancel'
    $btnCancel.Size         = New-Object System.Drawing.Size(90, 32)
    $btnCancel.Location     = New-Object System.Drawing.Point(548, 516)
    $btnCancel.Anchor       = ([System.Windows.Forms.AnchorStyles]::Bottom -bor [System.Windows.Forms.AnchorStyles]::Right)
    $btnCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.Controls.Add($btnCancel)

    $form.CancelButton = $btnCancel
    $form.Add_Shown({ $form.Activate(); $script:EditorTB.Focus(); $script:EditorTB.Select($script:EditorTB.TextLength, 0) })

    $result = $form.ShowDialog()
    $text   = $tb.Text
    $form.Dispose()
    if (Get-Command Set-ConsoleForeground -ErrorAction SilentlyContinue) { Set-ConsoleForeground }

    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
        return ($text -replace "`r`n", "`n" -replace "`r", "`n")
    }
    return $null
}

function Invoke-NotepadEditor {
    param([string]$SeedText = '')
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("ec_{0}.txt" -f ([guid]::NewGuid().ToString('N')))
    $out = ($SeedText -replace "`r`n", "`n") -replace "`n", "`r`n"
    Set-Content -Path $tmp -Value $out -Encoding UTF8 -NoNewline
    Start-Process -FilePath notepad.exe -ArgumentList $tmp -Wait
    $content = ''
    if (Test-Path $tmp) {
        $content = Get-Content -Path $tmp -Raw -Encoding UTF8
        Remove-Item $tmp -ErrorAction SilentlyContinue
    }
    if (Get-Command Set-ConsoleForeground -ErrorAction SilentlyContinue) { Set-ConsoleForeground }
    if ($null -eq $content) { return '' }
    $content = $content -replace "`r`n", "`n" -replace "`r", "`n"
    return ($content -replace '\s+$', '')
}
