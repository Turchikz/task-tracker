[CmdletBinding()]
param(
    [string]$BackupDir = "",
    [ValidateRange(1, 365)]
    [int]$Keep = 30
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if ([string]::IsNullOrWhiteSpace($BackupDir)) {
    $ProjectParent = Split-Path $ProjectDir -Parent
    $BackupDir = Join-Path $ProjectParent "backups\task-tracker"
}

$BackupDir = [System.IO.Path]::GetFullPath($BackupDir)
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

$LogFile = Join-Path $BackupDir "backup_windows.log"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$WorkDir = Join-Path $BackupDir ".tasktracker_$Stamp"
$Archive = Join-Path $BackupDir "tasktracker_backup_$Stamp.tar.gz"
$TempArchive = "$Archive.tmp"
$ChecksumFile = "$Archive.sha256"

$ContainerDbDump = "/tmp/tasktracker_backup_$Stamp.dump"
$ContainerMediaArchive = "/tmp/tasktracker_media_$Stamp.tar.gz"

function Write-BackupLog {
    param([string]$Message)
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Invoke-DockerCompose {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & docker compose @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose завершился с кодом ${LASTEXITCODE}: $($Arguments -join ' ')"
    }
}

function Get-RunningServices {
    $services = @(& docker compose ps --status running --services)
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось получить состояние Docker Compose."
    }
    return @($services | ForEach-Object { "$_".Trim() } | Where-Object { $_ })
}

Push-Location $ProjectDir

try {
    Write-BackupLog "Начало резервного копирования. ProjectDir=$ProjectDir"

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Команда docker не найдена. Установите/запустите Docker Desktop."
    }

    & docker info --format "{{.ServerVersion}}" *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Desktop не запущен или Docker Engine недоступен."
    }

    if (-not (Get-Command tar.exe -ErrorAction SilentlyContinue)) {
        throw "tar.exe не найден. На Windows 10/11 он обычно входит в состав системы."
    }

    $running = Get-RunningServices
    if ($running -notcontains "db") {
        throw "Контейнер db не запущен. Backup не создан."
    }

    if (Test-Path $WorkDir) {
        Remove-Item -Recurse -Force $WorkDir
    }
    New-Item -ItemType Directory -Path $WorkDir | Out-Null

    # PostgreSQL custom-format dump is first written inside the Linux container.
    # This avoids PowerShell 5.1 binary stdout redirection, which can corrupt data.
    Write-BackupLog "Создание PostgreSQL dump..."
    $dbCommand = 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --file="' + $ContainerDbDump + '"'
    Invoke-DockerCompose @("exec", "-T", "db", "sh", "-c", $dbCommand)

    $DatabaseDump = Join-Path $WorkDir "database.dump"
    Invoke-DockerCompose @("cp", "db:$ContainerDbDump", $DatabaseDump)
    Invoke-DockerCompose @("exec", "-T", "db", "rm", "-f", $ContainerDbDump)

    if (-not (Test-Path $DatabaseDump) -or (Get-Item $DatabaseDump).Length -le 0) {
        throw "database.dump пустой или не создан."
    }

    # Media are stored in a Docker named volume. Build the archive inside web
    # and copy the resulting file to the Windows host.
    if ($running -contains "web") {
        Write-BackupLog "Создание архива media..."
        $mediaPython = "import os,tarfile; os.makedirs('/app/media', exist_ok=True); t=tarfile.open('$ContainerMediaArchive','w:gz'); t.add('/app/media', arcname='.'); t.close()"
        Invoke-DockerCompose @("exec", "-T", "web", "python", "-c", $mediaPython)

        $MediaArchive = Join-Path $WorkDir "media.tar.gz"
        Invoke-DockerCompose @("cp", "web:$ContainerMediaArchive", $MediaArchive)
        Invoke-DockerCompose @("exec", "-T", "web", "rm", "-f", $ContainerMediaArchive)

        if (-not (Test-Path $MediaArchive) -or (Get-Item $MediaArchive).Length -le 0) {
            throw "media.tar.gz пустой или не создан."
        }
        $containsMedia = "yes"
    }
    else {
        Write-BackupLog "Контейнер web не запущен: media не включены в эту копию."
        $containsMedia = "no"
    }

    $version = "unknown"
    $VersionFile = Join-Path $ProjectDir "VERSION"
    if (Test-Path $VersionFile) {
        $version = (Get-Content $VersionFile -Raw).Trim()
        Copy-Item $VersionFile (Join-Path $WorkDir "VERSION")
    }

    # A release ZIP has no .git folder. Git metadata is optional.
    $commit = "unknown"
    if ((Test-Path (Join-Path $ProjectDir ".git")) -and (Get-Command git -ErrorAction SilentlyContinue)) {
        try {
            # Do not capture native stderr as a terminating PowerShell error.
            $gitOutput = & git -C $ProjectDir rev-parse --short HEAD 2>$null
            if ($LASTEXITCODE -eq 0 -and $gitOutput) {
                $commit = ([string](@($gitOutput)[0])).Trim()
            }
        } catch {
            $commit = "unknown"
        }
    }

    $EnvExample = Join-Path $ProjectDir ".env.example"
    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample (Join-Path $WorkDir "env.example")
    }

    $Manifest = @"
Task Tracker Windows host backup
created_at=$(Get-Date -Format o)
version=$version
git_commit=$commit
project_dir=$ProjectDir
contains_database=yes
contains_media=$containsMedia
real_env_included=no
host_os=Windows
"@
    Set-Content -Path (Join-Path $WorkDir "manifest.txt") -Value $Manifest -Encoding UTF8

    Write-BackupLog "Упаковка переносимого архива..."
    if (Test-Path $TempArchive) {
        Remove-Item -Force $TempArchive
    }

    & tar.exe -czf $TempArchive -C $WorkDir .
    if ($LASTEXITCODE -ne 0) {
        throw "tar.exe завершился с кодом $LASTEXITCODE."
    }

    if (-not (Test-Path $TempArchive) -or (Get-Item $TempArchive).Length -le 0) {
        throw "Финальный архив не создан."
    }

    Move-Item -Force $TempArchive $Archive

    $hash = (Get-FileHash -Algorithm SHA256 -Path $Archive).Hash.ToLowerInvariant()
    $archiveName = [System.IO.Path]::GetFileName($Archive)
    Set-Content -Path $ChecksumFile -Value "$hash  $archiveName" -Encoding ASCII
    Set-Content -Path (Join-Path $BackupDir "latest.txt") -Value $archiveName -Encoding ASCII

    # Expose status metadata to Django via a dedicated read-only bind mount.
    # Neither PostgreSQL dump nor media archive is mounted into the web service.
    $StatusDir = Join-Path $ProjectDir "backup_status"
    New-Item -ItemType Directory -Force -Path $StatusDir | Out-Null
    $StatusFile = Join-Path $StatusDir "backup_status.json"
    $TempStatus = "$StatusFile.tmp"
    $metadata = @{
        completed_at = [DateTime]::UtcNow.ToString("o")
        archive_name = $archiveName
        size_bytes = (Get-Item $Archive).Length
        media_included = ($containsMedia -eq "yes")
        sha256 = $hash
        host_os = "Windows"
    }
    $metadata | ConvertTo-Json -Depth 3 | Set-Content -Path $TempStatus -Encoding UTF8
    Move-Item -Path $TempStatus -Destination $StatusFile -Force

    # Retain only the newest N complete archives.
    $old = @(
        Get-ChildItem -Path $BackupDir -Filter "tasktracker_backup_*.tar.gz" -File |
        Sort-Object LastWriteTime -Descending |
        Select-Object -Skip $Keep
    )

    foreach ($item in $old) {
        Remove-Item -Force $item.FullName
        $sidecar = "$($item.FullName).sha256"
        if (Test-Path $sidecar) {
            Remove-Item -Force $sidecar
        }
    }

    Write-BackupLog "Backup создан: $Archive"
    Write-BackupLog "SHA-256: $ChecksumFile"
    Write-Host ""
    Write-Host "Готово. Архив находится ВНЕ Docker volumes:" -ForegroundColor Green
    Write-Host "  $Archive"
    Write-Host "  $ChecksumFile"
}
catch {
    Write-BackupLog "ОШИБКА: $($_.Exception.Message)"
    throw
}
finally {
    # Best-effort cleanup inside containers if an earlier step failed.
    try {
        if (Get-Command docker -ErrorAction SilentlyContinue) { & docker compose exec -T db rm -f $ContainerDbDump *> $null }
    } catch {}
    try {
        if (Get-Command docker -ErrorAction SilentlyContinue) { & docker compose exec -T web rm -f $ContainerMediaArchive *> $null }
    } catch {}

    if (Test-Path $WorkDir) {
        Remove-Item -Recurse -Force $WorkDir
    }
    if (Test-Path $TempArchive) {
        Remove-Item -Force $TempArchive
    }

    Pop-Location
}
