$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$version = (Get-Content .\VERSION -Raw).Trim()

if (-not $version) {
    throw "VERSION is empty"
}

$status = git status --porcelain
if ($status) {
    Write-Host "Working tree is not clean:" -ForegroundColor Yellow
    git status --short
    throw "Commit all changes before creating a release tag."
}

$tag = "v$version"

git rev-parse $tag 2>$null
if ($LASTEXITCODE -eq 0) {
    throw "Tag $tag already exists."
}

Write-Host "Creating release tag $tag"
git tag -a $tag -m "Task Tracker $tag"

Write-Host ""
Write-Host "Tag created locally."
Write-Host "Push it with:"
Write-Host "  git push origin $tag"
