# Colibri DeepSeek-V4-Flash-REAP-150b download — idle priority, capped workers.
# Run detached (see launcher below). Never touches mic/keshev processes.
$ErrorActionPreference = "Continue"
$env:HF_HUB_ENABLE_HF_TRANSFER = "1"
$repo = "puwaer/DeepSeek-V4-Flash-0731-reap-150b"
$dest = "C:\models\colibri\DeepSeek-V4-Flash-reap-150b"
$log  = "D:\CLAUDE\colibri-pc\download.log"

"[$(Get-Date -Format o)] START download repo=$repo dest=$dest max-workers=2" | Out-File -FilePath $log -Append -Encoding utf8

hf download $repo --local-dir $dest --max-workers 2 *>> $log

"[$(Get-Date -Format o)] hf download EXITED code=$LASTEXITCODE" | Out-File -FilePath $log -Append -Encoding utf8
