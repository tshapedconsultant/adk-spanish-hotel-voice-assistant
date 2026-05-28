# Initialize this folder as a Git repo and prepare the first push to GitHub.
# Run from the repository root: .\scripts\init_github_repo.ps1 -RemoteUrl "https://github.com/USER/REPO.git"

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RemoteUrl
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "Git is not installed or not on PATH. Install from https://git-scm.com/download/win"
}

try {
    git rev-parse --is-inside-work-tree *> $null
    if ($LASTEXITCODE -ne 0) { throw }
} catch {
    Write-Error "Configure Git identity first (once per machine): git config --global user.name `"Your Name`"; git config --global user.email `"you@example.com`""
}

if (Test-Path ".env") {
    Write-Host "OK: .env exists locally and is gitignored (will not be committed)." -ForegroundColor Green
} else {
    Write-Host "Tip: copy .env.example to .env and add your API keys for local dev." -ForegroundColor Yellow
}

if (-not (Test-Path ".git")) {
    git init
    git branch -M main
}

git add .
git status

$trackedEnv = git ls-files --error-unmatch .env 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Error ".env is tracked by git — remove it before pushing: git rm --cached .env"
}

Write-Host ""
Write-Host "Review 'git status' above. Then run:" -ForegroundColor Cyan
Write-Host "  git commit -m `"Initial commit: Spanish hotel voice assistant`""
Write-Host "  git remote add origin $RemoteUrl"
Write-Host "  git push -u origin main"
