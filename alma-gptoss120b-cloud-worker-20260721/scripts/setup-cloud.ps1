param(
    [switch]$ConfirmCloudWrites
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

if (-not $ConfirmCloudWrites) {
    Write-Host 'Dry safety stop: this script configures Worker secrets and deploys cloud resources.'
    Write-Host 'Review README.md, then rerun with -ConfirmCloudWrites.'
    exit 2
}

if (-not (Get-Command npx.cmd -ErrorAction SilentlyContinue)) {
    throw 'npx.cmd is required.'
}

Write-Host 'Checking the existing Cloudflare login...'
npx --yes wrangler whoami

Write-Host 'Enter the Groq free-tier API key. Wrangler stores it as an encrypted Worker secret.'
npx --yes wrangler secret put GROQ_API_KEY

Write-Host 'Enter a new private chat access token. Use a long random value and save it in your password manager.'
npx --yes wrangler secret put CHAT_ACCESS_TOKEN

Write-Host 'Deploying UI, gateway, quota Durable Object, and static assets to Cloudflare...'
npx --yes wrangler deploy

