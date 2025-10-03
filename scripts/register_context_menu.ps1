$ErrorActionPreference = "Stop"
$python = (Get-Command python -ErrorAction SilentlyContinue).Path
if (-not $python) { $python = (Get-Command py -ErrorAction SilentlyContinue).Path }
if (-not $python) { Write-Error "Python not found in PATH" }


$cmd = '"' + $python + '" -m sloan.app --open "%1"'


New-Item -Path "Registry::HKEY_CLASSES_ROOT\*\shell\Edit with Sloan" -Force | Out-Null
Set-ItemProperty -Path "Registry::HKEY_CLASSES_ROOT\*\shell\Edit with Sloan" -Name "" -Value "Edit with Sloan"
New-Item -Path "Registry::HKEY_CLASSES_ROOT\*\shell\Edit with Sloan\command" -Force | Out-Null
Set-ItemProperty -Path "Registry::HKEY_CLASSES_ROOT\*\shell\Edit with Sloan\command" -Name "" -Value $cmd
Write-Host "Registered context menu: Edit with Sloan"

$verb = "Registry::HKEY_CLASSES_ROOT\*\shell\Edit with Sloan"
New-Item -Path $verb -Force | Out-Null
Set-ItemProperty -Path $verb -Name "" -Value "Edit with Sloan"
Set-ItemProperty -Path $verb -Name "Icon" -Value "$PSScriptRoot\..\src\sloan\assets\icon.ico"
# Command
$cmdKey = "$verb\command"
New-Item -Path $cmdKey -Force | Out-Null
Set-ItemProperty -Path $cmdKey -Name "" -Value $cmd
