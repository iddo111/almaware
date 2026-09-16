"""
Haiku 30-minute system health check + fix + optimize.
Uses claude-haiku-4-5 to diagnose, prioritize, and auto-fix issues.

Run: python haiku_healthcheck.py
"""
import subprocess, json, time, os, sys, datetime
from pathlib import Path

LOG = Path("D:/CLAUDE/tools/haiku-healthcheck/healthcheck.log")
LOG.parent.mkdir(parents=True, exist_ok=True)

def log(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (r.stdout + r.stderr).strip()
    except Exception as e:
        return f"ERROR: {e}"

def gather_stats():
    stats = {}
    stats["cpu_usage"]     = run("powershell -c \"(Get-WmiObject Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average\"")
    stats["memory"]        = run("powershell -c \"$os=Get-WmiObject Win32_OperatingSystem; [math]::Round(($os.TotalVisibleMemorySize-$os.FreePhysicalMemory)/$os.TotalVisibleMemorySize*100,1)\"")
    stats["disk_c"]        = run("powershell -c \"(Get-PSDrive C | Select-Object -ExpandProperty Used) / ((Get-PSDrive C | Select-Object -ExpandProperty Used)+(Get-PSDrive C | Select-Object -ExpandProperty Free)) * 100 | % {[math]::Round($_,1)}\"")
    stats["disk_d"]        = run("powershell -c \"(Get-PSDrive D | Select-Object -ExpandProperty Used) / ((Get-PSDrive D | Select-Object -ExpandProperty Used)+(Get-PSDrive D | Select-Object -ExpandProperty Free)) * 100 | % {[math]::Round($_,1)}\"")
    stats["gpu_temp"]      = run("nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total --format=csv,noheader")
    stats["gpu_processes"] = run("nvidia-smi --query-compute-apps=pid,used_memory,name --format=csv,noheader")
    stats["top_cpu_procs"] = run("powershell -c \"Get-Process | Sort-Object CPU -Descending | Select-Object -First 8 Name,CPU,WorkingSet | ConvertTo-Csv -NoTypeInformation\"")
    stats["top_mem_procs"] = run("powershell -c \"Get-Process | Sort-Object WorkingSet -Descending | Select-Object -First 8 Name,CPU,WorkingSet | ConvertTo-Csv -NoTypeInformation\"")
    stats["startup_items"] = run("powershell -c \"Get-CimInstance Win32_StartupCommand | Select-Object Name,Command | ConvertTo-Csv -NoTypeInformation\"")
    stats["event_errors"]  = run("powershell -c \"Get-EventLog -LogName System -EntryType Error -Newest 10 | Select-Object TimeGenerated,Source,Message | ConvertTo-Csv -NoTypeInformation\"")
    stats["disk_queue"]    = run("powershell -c \"(Get-Counter '\\PhysicalDisk(_Total)\\Avg. Disk Queue Length').CounterSamples.CookedValue\"")
    stats["audio_device"]  = run("powershell -c \"(Get-WmiObject -Class Win32_SoundDevice | Where-Object {$_.Status -eq 'OK'} | Select-Object Name) | ConvertTo-Csv -NoTypeInformation\"")
    stats["ollama_running"] = run("powershell -c \"(Get-Process ollama -ErrorAction SilentlyContinue | Measure-Object).Count\"")
    stats["uptime_hours"]  = run("powershell -c \"[math]::Round((Get-Date - (gcim Win32_OperatingSystem).LastBootUpTime).TotalHours, 1)\"")
    return stats

def call_haiku(system_prompt, user_msg, max_tokens=2000):
    # Backend: Max plan via CLI shim (default). Set HEALTHCHECK_BACKEND=api for SDK.
    import os, sys
    if os.environ.get("HEALTHCHECK_BACKEND", "max").lower() == "max":
        sys.path.insert(0, r"D:\CLAUDE\_shared")
        from claude_max_client import Anthropic
        client = Anthropic()
    else:
        import anthropic
        client = anthropic.Anthropic()
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_msg}]
    )
    return msg.content[0].text

SYSTEM = """You are a Windows 11 system health agent. The machine runs:
- RTX 3070 Ti (8GB VRAM), 16-32GB RAM
- Focusrite Scarlett Solo USB audio interface
- Ollama LLM server (GPU-heavy when active)
- D:/CLAUDE project directory with AI/ML work
- Two Heltec V4 LoRa modules on COM3/COM4

Your job: analyze system stats, identify issues, output a JSON plan with quick fixes and heavy fixes.
Always output valid JSON. Be terse. Prioritize stability and performance."""

def phase1_diagnose(stats):
    log("Phase 1: Haiku diagnosing system...")
    prompt = f"""Analyze these Windows 11 system stats and output a JSON health report.

STATS:
{json.dumps(stats, indent=2)}

Output JSON with this exact structure:
{{
  "health_score": 0-100,
  "issues": [
    {{"severity": "critical|high|medium|low", "title": "...", "detail": "...", "fix_type": "quick|heavy|manual"}}
  ],
  "quick_fixes": [
    {{"title": "...", "powershell": "..."}}
  ],
  "heavy_fixes": [
    {{"title": "...", "detail": "...", "powershell": "..."}}
  ],
  "memory_cleaners": [
    {{"title": "...", "powershell": "..."}}
  ],
  "summary": "one sentence"
}}"""
    return call_haiku(SYSTEM, prompt, max_tokens=3000)

def phase2_execute(plan):
    log("Phase 2: Executing quick fixes and memory cleaners...")
    results = []

    # always-safe memory cleanup
    safe_cleaners = [
        ("Clear DNS cache",        "ipconfig /flushdns"),
        ("Clear temp files",       "powershell -c \"Remove-Item $env:TEMP\\* -Recurse -Force -ErrorAction SilentlyContinue\""),
        ("Clear Windows temp",     "powershell -c \"Remove-Item C:\\Windows\\Temp\\* -Recurse -Force -ErrorAction SilentlyContinue\""),
        ("Trim working sets",      "powershell -c \"Get-Process | ForEach-Object { $_.MinWorkingSet=1 }\" "),
        ("Empty recycle bin",      "powershell -c \"Clear-RecycleBin -Force -ErrorAction SilentlyContinue\""),
        ("Flush standby RAM",      "powershell -c \"[System.GC]::Collect()\""),
    ]
    for title, cmd in safe_cleaners:
        out = run(cmd, timeout=20)
        log(f"  [{title}] {out[:80] if out else 'done'}")
        results.append({"fix": title, "result": out[:200]})

    # execute Haiku-generated quick fixes
    try:
        data = json.loads(plan)
        for fix in data.get("quick_fixes", []):
            ps = fix.get("powershell", "")
            if not ps or any(bad in ps.lower() for bad in ["format", "remove-item c:\\windows\\system", "del /f /s"]):
                continue  # safety gate
            log(f"  [Quick fix] {fix['title']}")
            out = run(f"powershell -c \"{ps.replace(chr(34), chr(39))}\"", timeout=30)
            log(f"    → {out[:100] if out else 'done'}")
            results.append({"fix": fix["title"], "result": out[:200]})
    except Exception as e:
        log(f"  [warn] Could not parse Haiku plan: {e}")

    return results

def phase3_report(stats, plan, fix_results):
    log("Phase 3: Haiku writing final report...")
    prompt = f"""Write a terse health report (under 300 words) for a technical user.

Original stats summary: CPU {stats['cpu_usage']}% load, Mem {stats['memory']}% used, GPU: {stats['gpu_temp']}
Haiku plan: {plan[:1000]}
Fixes applied: {json.dumps(fix_results[:5], indent=2)}

Include:
1. Health score + one-line verdict
2. Top 3 issues found
3. What was auto-fixed
4. What still needs manual attention
5. Any heavy fixes recommended

Be direct. No fluff."""
    return call_haiku(SYSTEM, prompt, max_tokens=1000)

def main():
    log("=" * 60)
    log("HAIKU SYSTEM HEALTH CHECK — 30 minute run")
    log("=" * 60)

    t0 = time.time()

    log("Gathering system stats...")
    stats = gather_stats()
    log(f"  CPU: {stats['cpu_usage']}% | Mem: {stats['memory']}% | GPU: {stats['gpu_temp']}")
    log(f"  Disk C: {stats['disk_c']}% | D: {stats['disk_d']}% | Uptime: {stats['uptime_hours']}h")

    plan_raw = phase1_diagnose(stats)
    log(f"Haiku diagnosis complete ({len(plan_raw)} chars)")

    fix_results = phase2_execute(plan_raw)
    log(f"Applied {len(fix_results)} fixes")

    # heavy fix check if time allows
    elapsed = time.time() - t0
    if elapsed < 20 * 60:
        try:
            data = json.loads(plan_raw)
            heavy = data.get("heavy_fixes", [])
            if heavy:
                log(f"Heavy fixes available ({len(heavy)}) — running safe ones...")
                for fix in heavy[:3]:
                    ps = fix.get("powershell", "")
                    if not ps or any(bad in ps.lower() for bad in ["format", "del /f /s /q c:\\"]):
                        continue
                    log(f"  [Heavy] {fix['title']}")
                    out = run(f"powershell -c \"{ps.replace(chr(34), chr(39))}\"", timeout=120)
                    log(f"    → {out[:120] if out else 'done'}")
        except Exception:
            pass

    report = phase3_report(stats, plan_raw, fix_results)
    log("\n" + "=" * 60)
    log("FINAL REPORT:")
    log("=" * 60)
    for line in report.split("\n"):
        log(line)

    total = round((time.time() - t0) / 60, 1)
    log(f"\nDone in {total} minutes. Full log: {LOG}")

    # save full plan for review
    plan_path = LOG.parent / "last_plan.json"
    try:
        plan_path.write_text(plan_raw, encoding="utf-8")
        log(f"Full Haiku plan saved to {plan_path}")
    except Exception:
        pass

if __name__ == "__main__":
    main()
