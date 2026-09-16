[CmdletBinding()]
param(
    [string[]]$Roots,
    [string]$OutputRoot = 'D:\CLAUDE\security-audit-swarm\local-results',
    [int64]$MaxTextBytes = 8MB
)

$ErrorActionPreference = 'Stop'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$runDir = Join-Path $OutputRoot $stamp
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

if (-not $Roots -or $Roots.Count -eq 0) {
    $Roots = Get-CimInstance Win32_LogicalDisk |
        Where-Object { $_.DriveType -in 2, 3 } |
        ForEach-Object { "$($_.DeviceID)\" }
}

$findingsPath = Join-Path $runDir 'findings.jsonl'
$gitPath = Join-Path $runDir 'git-repositories.jsonl'
$errorsPath = Join-Path $runDir 'errors.jsonl'
$statusPath = Join-Path $runDir 'status.json'
$targetsPath = Join-Path $runDir 'target-artifacts.jsonl'

$textExtensions = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
@(
    '.txt','.md','.json','.jsonl','.yaml','.yml','.toml','.ini','.conf','.config',
    '.xml','.html','.htm','.js','.mjs','.cjs','.ts','.tsx','.jsx','.py','.ps1',
    '.psm1','.psd1','.sh','.bash','.zsh','.bat','.cmd','.env','.properties',
    '.dockerfile','.lock'
) | ForEach-Object { [void]$textExtensions.Add($_) }

$targetExtensions = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
@('.exe','.dll','.msi','.msix','.appx','.apk','.jar','.ps1','.bat','.cmd','.sh','.py','.js','.ts','.zip','.7z','.rar','.tar','.gz') |
    ForEach-Object { [void]$targetExtensions.Add($_) }

$patterns = [ordered]@{
    exact_zero_words       = '(?i)(?<![0-9])(?:produce|producing|output|emit|return|respond(?:ing)?)\s+(?:absolutely\s+)?(?:zero|0)\s+words(?![0-9])'
    empty_response_order   = '(?i)(?:output|return|produce|emit)\s+(?:an?\s+)?empty\s+(?:response|message|reply)'
    silence_order          = '(?i)(?:do\s+not|don''t|never)\s+(?:respond|reply|output|say\s+anything)'
    ignore_instructions    = '(?i)ignore\s+(?:all|any|the|your|previous|prior|above)\s+(?:instructions?|prompts?|rules?|messages?)'
    role_impersonation     = '(?i)(?:^|[\r\n<\[])\s*(?:system|developer|assistant|tool)\s*(?:message)?\s*[:>\]]'
    system_markup          = '(?i)<\/?(?:system|system-reminder|developer|assistant|tool)[^>]*>'
    prompt_injection       = '(?i)prompt[-_ ]?inject(?:ion|ed)?|indirect[-_ ]prompt|jailbreak'
    secret_exfiltration    = '(?i)(?:\.ssh|\.aws|\.azure|\.config[/\\]gcloud|credentials|api[_-]?key|auth\.json).{0,180}(?:upload|send|post|fetch|curl|invoke-webrequest|requests?\.)'
    pipe_to_shell          = '(?i)(?:curl|wget|irm|invoke-restmethod|invoke-webrequest).{0,240}(?:\|\s*(?:bash|sh)|iex|invoke-expression)'
    powershell_downloadexec= '(?i)(?:downloadstring|invoke-expression|\biex\b|frombase64string).{0,220}(?:http|https|invoke|start-process|reflection|assembly)'
    reverse_shell          = '(?i)(?:/dev/tcp/|nc\s+-e|ncat\s+.*--exec|powershell.{0,120}tcpclient|socket\(.{0,160}connect\()'
    crypto_miner           = '(?i)(?:xmrig|stratum\+tcp|minerd|cryptonight|monero[-_ ]?pool)'
    agent_projects         = '(?i)\b(?:openclaw|moltbot|clawdbot|hermes[-_ ]agent|nousresearch/hermes-agent)\b'
}

$excludedDirNames = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
@('System Volume Information','$RECYCLE.BIN') | ForEach-Object { [void]$excludedDirNames.Add($_) }

$stats = [ordered]@{
    started = (Get-Date).ToString('o')
    roots = $Roots
    files_seen = 0L
    text_files_scanned = 0L
    bytes_text_scanned = 0L
    findings = 0L
    target_artifacts = 0L
    git_repositories = 0L
    errors = 0L
    current_path = $null
    completed = $false
}

function Write-JsonLine {
    param([string]$Path, [object]$Value)
    $line = $Value | ConvertTo-Json -Compress -Depth 8
    [System.IO.File]::AppendAllText($Path, $line + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Write-Status {
    $stats.current_path = $script:currentPath
    $tmp = "$statusPath.tmp"
    $stats | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $tmp -Encoding utf8
    Move-Item -Force -LiteralPath $tmp -Destination $statusPath
}

function Record-Error {
    param([string]$Path, [System.Exception]$Exception)
    $stats.errors++
    Write-JsonLine -Path $errorsPath -Value ([ordered]@{
        time = (Get-Date).ToString('o')
        path = $Path
        error_type = $Exception.GetType().FullName
        message = $Exception.Message
    })
}

function Get-SafeHash {
    param([string]$Path)
    $stream = $null
    $sha = $null
    try {
        $stream = [System.IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete)
        $sha = [Security.Cryptography.SHA256]::Create()
        $bytes = $sha.ComputeHash($stream)
        return -join ($bytes | ForEach-Object { $_.ToString('x2') })
    } catch {
        Record-Error -Path $Path -Exception $_.Exception
        return $null
    } finally {
        if ($sha) { $sha.Dispose() }
        if ($stream) { $stream.Dispose() }
    }
}

function Test-TextCandidate {
    param([System.IO.FileInfo]$File)
    if ($File.Length -gt $MaxTextBytes) { return $false }
    if ($textExtensions.Contains($File.Extension)) { return $true }
    return $File.Name -match '^(?i)(?:Dockerfile|Makefile|AGENTS\.md|CLAUDE\.md|GEMINI\.md|SKILL\.md|SECURITY\.md|package-lock\.json|pnpm-lock\.yaml|uv\.lock)$'
}

function Scan-File {
    param([System.IO.FileInfo]$File)
    $stats.files_seen++
    $script:currentPath = $File.FullName

    $isTargetName = $File.FullName -match '(?i)openclaw|moltbot|clawdbot|hermes|claude-code-router|grok'
    $isRecentExecutable = $targetExtensions.Contains($File.Extension) -and $File.LastWriteTimeUtc -gt (Get-Date).ToUniversalTime().AddDays(-120)
    if ($isTargetName -or $isRecentExecutable) {
        $signature = $null
        if ($File.Extension -in '.exe','.dll','.msi','.msix','.appx','.ps1') {
            try {
                $sig = Get-AuthenticodeSignature -LiteralPath $File.FullName
                $signature = [ordered]@{ status = [string]$sig.Status; signer = $sig.SignerCertificate.Subject }
            } catch {
                Record-Error -Path $File.FullName -Exception $_.Exception
            }
        }
        Write-JsonLine -Path $targetsPath -Value ([ordered]@{
            path = $File.FullName
            size = $File.Length
            modified_utc = $File.LastWriteTimeUtc.ToString('o')
            sha256 = Get-SafeHash -Path $File.FullName
            signature = $signature
            reason = if ($isTargetName) { 'target-name' } else { 'recent-executable-or-script' }
        })
        $stats.target_artifacts++
    }

    if (-not (Test-TextCandidate -File $File)) { return }

    try {
        $content = [System.IO.File]::ReadAllText($File.FullName)
        $stats.text_files_scanned++
        $stats.bytes_text_scanned += $File.Length
        $matched = [System.Collections.Generic.List[string]]::new()
        foreach ($entry in $patterns.GetEnumerator()) {
            if ([regex]::IsMatch($content, $entry.Value, [Text.RegularExpressions.RegexOptions]::CultureInvariant, [TimeSpan]::FromSeconds(2))) {
                $matched.Add($entry.Key)
            }
        }
        if ($matched.Count -gt 0) {
            Write-JsonLine -Path $findingsPath -Value ([ordered]@{
                path = $File.FullName
                size = $File.Length
                modified_utc = $File.LastWriteTimeUtc.ToString('o')
                sha256 = Get-SafeHash -Path $File.FullName
                categories = $matched
            })
            $stats.findings++
        }
    } catch {
        Record-Error -Path $File.FullName -Exception $_.Exception
    }

    if (($stats.files_seen % 2000) -eq 0) { Write-Status }
}

function Walk-Directory {
    param([string]$Directory)
    $pending = [System.Collections.Generic.Stack[string]]::new()
    $pending.Push($Directory)

    while ($pending.Count -gt 0) {
        $dir = $pending.Pop()
        $script:currentPath = $dir
        try {
            $dirInfo = [System.IO.DirectoryInfo]::new($dir)
            if (($dirInfo.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { continue }
            if ($excludedDirNames.Contains($dirInfo.Name)) { continue }

            if (Test-Path -LiteralPath (Join-Path $dir '.git')) {
                Write-JsonLine -Path $gitPath -Value ([ordered]@{ path = $dir; discovered_utc = (Get-Date).ToUniversalTime().ToString('o') })
                $stats.git_repositories++
            }

            foreach ($file in [System.IO.Directory]::EnumerateFiles($dir)) {
                try { Scan-File -File ([System.IO.FileInfo]::new($file)) }
                catch { Record-Error -Path $file -Exception $_.Exception }
            }
            foreach ($child in [System.IO.Directory]::EnumerateDirectories($dir)) {
                try {
                    $childInfo = [System.IO.DirectoryInfo]::new($child)
                    if (($childInfo.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0 -and -not $excludedDirNames.Contains($childInfo.Name)) {
                        $pending.Push($child)
                    }
                } catch { Record-Error -Path $child -Exception $_.Exception }
            }
        } catch {
            Record-Error -Path $dir -Exception $_.Exception
        }

        if (($stats.files_seen % 2000) -eq 0) { Write-Status }
    }
}

Write-Status
foreach ($root in $Roots) {
    if (Test-Path -LiteralPath $root) { Walk-Directory -Directory $root }
}

$stats.completed = $true
$stats.completed_at = (Get-Date).ToString('o')
Write-Status
$runDir
