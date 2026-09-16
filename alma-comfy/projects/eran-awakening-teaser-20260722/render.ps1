$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$outputDir = Join-Path $projectRoot 'output'
$provenanceDir = Join-Path $projectRoot 'provenance'
$image = Join-Path $projectRoot 'assets\flux2-klein-fixed-seed.png'
$motion = Join-Path $projectRoot 'assets\wan-ti2v-canary.mp4'
$music = Join-Path $projectRoot 'assets\ace-step-fixed-seed-424242.wav'
$master = Join-Path $outputDir 'ERAN-Awakening-Teaser-1080p-SDR.mp4'
$probe = Join-Path $provenanceDir 'ffprobe.json'
$decodeLog = Join-Path $provenanceDir 'full-decode.log'
$receipt = Join-Path $provenanceDir 'render-receipt.json'

New-Item -ItemType Directory -Force -Path $outputDir, $provenanceDir | Out-Null

foreach ($source in @($image, $motion, $music)) {
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Missing source asset: $source"
    }
}

$filter = @'
[0:v]scale=1920:1920:flags=lanczos,crop=1920:1080:0:350,split=3[s1base][s2base][s4base];
[s1base]zoompan=z='1.055-0.035*on/47':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1920x1080:fps=24,trim=duration=2,setpts=PTS-STARTPTS,eq=brightness=-0.24:contrast=1.08:saturation=0.88,vignette=PI/4,fade=t=in:st=0:d=0.30,fade=t=out:st=1.72:d=0.28[s1];
[s2base]zoompan=z='1.00+0.075*on/71':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)-35':d=1:s=1920x1080:fps=24,trim=duration=3,setpts=PTS-STARTPTS,eq=brightness=-0.02:contrast=1.07:saturation=1.12,colorbalance=bs=.04:gs=.015,vignette=PI/5,fade=t=in:st=0:d=0.24,fade=t=out:st=2.72:d=0.28[s2];
[1:v]fps=24,scale=1920:1108:flags=lanczos,crop=1920:1080:0:14,split=2[wforward][wreverse];
[wreverse]reverse[wrev];
[wforward][wrev]concat=n=2:v=1:a=0,loop=loop=4:size=34:start=0,setpts=N/24/TB,trim=duration=3,setpts=PTS-STARTPTS,eq=contrast=1.08:saturation=1.08,colorbalance=rs=.025:bs=.02,vignette=PI/5,noise=alls=1.5:allf=t,fade=t=in:st=0:d=0.24,fade=t=out:st=2.72:d=0.28[s3];
[s4base]zoompan=z='1.08-0.055*on/47':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)-20':d=1:s=1920x1080:fps=24,trim=duration=2,setpts=PTS-STARTPTS,eq=brightness=-0.20:contrast=1.10:saturation=0.90,vignette=PI/4,fade=t=in:st=0:d=0.28,fade=t=out:st=1.55:d=0.45[s4];
[s1][s2][s3][s4]concat=n=4:v=1:a=0,subtitles=filename='captions.ass',format=yuv420p[v];
[2:a]atrim=0:10,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.70,afade=t=out:st=8.55:d=1.45,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,aformat=channel_layouts=stereo[a]
'@

Push-Location $projectRoot
try {
    & ffmpeg -y -hide_banner -loglevel warning `
        -loop 1 -framerate 24 -t 10 -i $image `
        -i $motion `
        -i $music `
        -filter_complex $filter `
        -map '[v]' -map '[a]' -t 10 `
        -c:v libx264 -preset slow -crf 16 -profile:v high -level 4.2 `
        -color_primaries bt709 -color_trc bt709 -colorspace bt709 `
        -c:a aac -b:a 256k -ar 48000 -ac 2 `
        -movflags +faststart $master
    if ($LASTEXITCODE -ne 0) { throw "FFmpeg render failed with exit code $LASTEXITCODE" }

    & ffprobe -v error -show_entries 'format=filename,duration,size,bit_rate:stream=index,codec_name,codec_type,width,height,pix_fmt,r_frame_rate,sample_rate,channels,color_space,color_transfer,color_primaries' -of json $master | Set-Content -LiteralPath $probe -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "ffprobe failed with exit code $LASTEXITCODE" }

    & ffmpeg -v error -i $master -map 0:v:0 -map 0:a:0 -f null - 2>&1 | Set-Content -LiteralPath $decodeLog -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "Full decode failed with exit code $LASTEXITCODE" }

    $masterItem = Get-Item -LiteralPath $master
    $masterHash = (Get-FileHash -LiteralPath $master -Algorithm SHA256).Hash.ToLowerInvariant()
    $sourceHashes = Get-FileHash -Algorithm SHA256 -LiteralPath $image, $motion, $music
    $payload = [ordered]@{
        status = 'technical-pass-human-review-pending'
        rendered_at = (Get-Date).ToString('o')
        project_id = 'eran-awakening-teaser-20260722'
        artifact = $master
        artifact_bytes = $masterItem.Length
        artifact_sha256 = $masterHash
        duration_seconds = 10
        output = [ordered]@{
            width = 1920
            height = 1080
            fps = 24
            color = 'SDR BT.709'
            video = 'H.264 High, yuv420p'
            audio = 'AAC-LC, 48 kHz, stereo, 256 kb/s, -16 LUFS target'
        }
        sources = @($sourceHashes | ForEach-Object {
            [ordered]@{ path = $_.Path; sha256 = $_.Hash.ToLowerInvariant() }
        })
        gates = @('artifact-nonempty','ffprobe-pass','full-video-audio-decode-pass','source-hashes-recorded','-16-LUFS-target')
        truth = 'AI-generated teaser; not documentary footage; SDR is not labeled HDR'
        human_review = 'pending'
    }
    $payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $receipt -Encoding utf8
    Write-Output $master
    Write-Output $masterHash
}
finally {
    Pop-Location
}
