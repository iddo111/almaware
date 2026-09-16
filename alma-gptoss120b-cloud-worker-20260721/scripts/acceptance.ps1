param(
    [Parameter(Mandatory = $true)]
    [string]$BaseUrl
)

$ErrorActionPreference = 'Stop'
$BaseUrl = $BaseUrl.TrimEnd('/')
if ($BaseUrl -notmatch '^https://') { throw 'Acceptance requires a public HTTPS cloud URL.' }
if ($BaseUrl -match 'localhost|127\.0\.0\.1|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.') {
    throw 'Local/private endpoints are forbidden by the Chat 120 cloud contract.'
}

$secure = Read-Host 'Private Alma access token' -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $accessToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    $status = Invoke-RestMethod -Uri "$BaseUrl/api/status" -Method Get -TimeoutSec 30
    if ($status.runtime -ne 'cloudflare-worker') { throw 'runtime is not cloudflare-worker' }
    if ($status.model -ne 'openai/gpt-oss-120b') { throw 'wrong model id' }
    if ($status.localFallback -ne $false -or $status.dgxFallback -ne $false) { throw 'a local/DGX fallback is exposed' }
    if (-not $status.uiHostedInCloud -or -not $status.gatewayHostedInCloud -or -not $status.inferenceHostedInCloud) {
        throw 'one or more cloud truth fields are false'
    }

    $nonce = 'ALMA_CLOUD_OK_' + [Guid]::NewGuid().ToString('N')
    $headers = @{ 'X-Alma-Access' = $accessToken }
    $body = @{ messages = @(@{ role = 'user'; content = "Reply with only this exact token: $nonce" }); temperature = 0.35; max_completion_tokens = 512 } | ConvertTo-Json -Depth 5
    $response = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/api/chat" -Method Post -Headers $headers -ContentType 'application/json' -Body $body -TimeoutSec 180

    if ([int]$response.StatusCode -ne 200) { throw "chat returned HTTP $($response.StatusCode)" }
    if ($response.Headers['X-Alma-Runtime'] -ne 'cloudflare-worker') { throw 'missing cloud runtime header' }
    if ($response.Headers['X-Alma-Model'] -ne 'openai/gpt-oss-120b') { throw 'missing exact model header' }
    if ($response.Headers['X-Alma-Local-Fallback'] -ne 'false') { throw 'local fallback header is not false' }
    if ($response.Content -notmatch [Regex]::Escape($nonce)) { throw 'generation was empty or did not return the nonce' }

    Start-Sleep -Milliseconds 900
    $verified = Invoke-RestMethod -Uri "$BaseUrl/api/status" -Method Get -TimeoutSec 30
    if (-not $verified.generationVerified) { throw 'status did not record the real generation' }

    [pscustomobject]@{
        VERIFIED = $true
        Url = $BaseUrl
        Runtime = $verified.runtime
        Provider = $verified.provider
        Model = $verified.model
        NonemptyGeneration = $true
        LocalFallback = $verified.localFallback
        LastGenerationAt = $verified.lastGenerationAt
    } | Format-List
} finally {
    if ($ptr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
    $accessToken = $null
}
