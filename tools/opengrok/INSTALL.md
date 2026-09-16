# OpenGrok Local Install — D:\CLAUDE Code Search
**For:** Iddo Perez — iddoperez.ai  
**Date:** 2026-05-05  
**Goal:** Searchable, cross-referenced source view of `D:\CLAUDE\` at `http://localhost:8088/source/`

---

## Architecture

```
Browser  ──>  Tomcat 10.1  (port 8088)
                  |
              opengrok.war  (OpenGrok 1.14.11)
                  |
              DATA_ROOT = D:\CLAUDE\tools\opengrok\data\
                  |
              SRC_ROOT  = D:\CLAUDE\
                  |
          Universal Ctags  (symbol cross-reference)
```

All software is free / Apache-licensed. No money spent.

---

## Prerequisites

### Step 1 — Java 21 (JDK)

**Check first:**
```cmd
where java
java -version
```

Java was **not found on PATH** at install time. You need JDK 21.

**Install (run this once, user-level — no admin required for portable):**

Option A — winget (may prompt for UAC once):
```powershell
winget install --id Oracle.JDK.21 --source winget
```

Option B — portable (zero UAC): Download from  
https://download.java.net/java/GA/jdk21/fd2272bbf8e04c3dbaee13770090416c/35/GPL/openjdk-21_windows-x64_bin.zip  
Unzip to `D:\CLAUDE\tools\jdk21\`  
Then set `JAVA_HOME=D:\CLAUDE\tools\jdk21\jdk-21` and add `%JAVA_HOME%\bin` to your user PATH.

**After installing Java, verify:**
```cmd
java -version
# Expected: openjdk version "21" ...
```

> STOP HERE if Java is not yet installed. The rest of this guide requires it.

---

## Step 2 — Apache Tomcat 10.1.54

**Download (run in PowerShell):**
```powershell
$tomcatUrl = "https://dlcdn.apache.org/tomcat/tomcat-10/v10.1.54/bin/apache-tomcat-10.1.54-windows-x64.zip"
$dest = "D:\CLAUDE\tools\opengrok\apache-tomcat-10.1.54-windows-x64.zip"
Invoke-WebRequest -Uri $tomcatUrl -OutFile $dest
Expand-Archive -Path $dest -DestinationPath "D:\CLAUDE\tools\opengrok\tomcat\" -Force
# The zip expands to a subdirectory; flatten it:
$inner = Get-ChildItem "D:\CLAUDE\tools\opengrok\tomcat\" -Directory | Select-Object -First 1
Get-ChildItem $inner.FullName | Move-Item -Destination "D:\CLAUDE\tools\opengrok\tomcat\"
Remove-Item $inner.FullName
Remove-Item $dest
```

**Configure port 8088:**  
Edit `D:\CLAUDE\tools\opengrok\tomcat\conf\server.xml`  
Find the line:
```xml
<Connector port="8080" protocol="HTTP/1.1"
```
Change `8080` → `8088`.

Also find the shutdown port line `<Server port="8005"` and change to `8006` (avoids conflict with other Tomcat instances if any).

---

## Step 3 — OpenGrok 1.14.11

**Download:**
```powershell
$ogUrl = "https://github.com/oracle/opengrok/releases/download/1.14.11/opengrok-1.14.11.tar.gz"
$dest = "D:\CLAUDE\tools\opengrok\opengrok-1.14.11.tar.gz"
Invoke-WebRequest -Uri $ogUrl -OutFile $dest
# Extract using tar (built into Win10/11):
tar -xzf $dest -C "D:\CLAUDE\tools\opengrok\opengrok\"
Remove-Item $dest
```

After extraction you should have:
```
D:\CLAUDE\tools\opengrok\opengrok\
  opengrok-1.14.11\
    lib\
      opengrok.jar
      opengrok-tools.tar.gz
    doc\
    README.md
```

**Install OpenGrok Python tools** (required for the indexer wrapper):
```powershell
pip install opengrok-tools
# OR directly from the tarball:
pip install "D:\CLAUDE\tools\opengrok\opengrok\opengrok-1.14.11\lib\opengrok-tools.tar.gz"
```

---

## Step 4 — Universal Ctags 6.1.0

Universal Ctags provides the symbol cross-reference that makes OpenGrok genuinely useful.

**Download portable binary:**
```powershell
$ctagsUrl = "https://github.com/universal-ctags/ctags-win32/releases/download/v6.1.0/ctags-v6.1.0-x64.zip"
$dest = "D:\CLAUDE\tools\opengrok\ctags\ctags-v6.1.0-x64.zip"
Invoke-WebRequest -Uri $ctagsUrl -OutFile $dest
Expand-Archive -Path $dest -DestinationPath "D:\CLAUDE\tools\opengrok\ctags\" -Force
Remove-Item $dest
```

After extraction: `D:\CLAUDE\tools\opengrok\ctags\ctags.exe` should exist.

**Test:**
```cmd
D:\CLAUDE\tools\opengrok\ctags\ctags.exe --version
# Expected: Universal Ctags 6.1.0
```

**Windows Defender note:** Defender occasionally false-flags ctags.exe as a PUA (Potentially Unwanted Application) because it parses arbitrary source files. If Windows blocks it:

1. Open Windows Security → Virus & threat protection → Protection history
2. Find the ctags.exe block entry → Allow
3. OR add an exclusion (PowerShell as admin):
```powershell
Add-MpPreference -ExclusionPath "D:\CLAUDE\tools\opengrok\ctags\ctags.exe"
```

---

## Step 5 — Deploy WAR and Initial Index

**5a. Deploy the WAR to Tomcat:**
```powershell
# The WAR is inside the OpenGrok lib dir
Copy-Item "D:\CLAUDE\tools\opengrok\opengrok\opengrok-1.14.11\lib\source.war" `
          "D:\CLAUDE\tools\opengrok\tomcat\webapps\source.war"
```

**5b. Start Tomcat (first time) so it unpacks the WAR:**
```cmd
D:\CLAUDE\tools\opengrok\tomcat\bin\startup.bat
```
Wait ~10 seconds for Tomcat to unpack `source.war` into `tomcat\webapps\source\`.

**5c. Run the initial index:**
```powershell
$env:JAVA_HOME = "C:\Program Files\Java\jdk-21"  # adjust if portable install
$jar = "D:\CLAUDE\tools\opengrok\opengrok\opengrok-1.14.11\lib\opengrok.jar"
$ctags = "D:\CLAUDE\tools\opengrok\ctags\ctags.exe"
$src = "D:\CLAUDE"
$data = "D:\CLAUDE\tools\opengrok\data"
$webinf = "D:\CLAUDE\tools\opengrok\tomcat\webapps\source\WEB-INF"

java -Djava.util.logging.config.file="$webinf\logging.properties" `
     -jar $jar `
     -s $src `
     -d $data `
     -c $ctags `
     -W "$webinf\configuration.xml" `
     -H -P -S -G -U "http://localhost:8088/source"
```

First index of `D:\CLAUDE\` takes 5-20 minutes depending on file count. Subsequent reindexes of changed files only take seconds to minutes.

**5d. Verify deployment:**
Open: http://localhost:8088/source/

You should see the OpenGrok search interface with your source tree.

---

## Step 6 — Launcher Script

See `D:\CLAUDE\tools\opengrok\start_opengrok.cmd` — double-click to start Tomcat and open the browser.

---

## Step 7 — Weekly Reindex

See `D:\CLAUDE\tools\opengrok\reindex.ps1` — schedule this with Task Scheduler or run manually.

To schedule weekly (PowerShell as admin):
```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NonInteractive -File D:\CLAUDE\tools\opengrok\reindex.ps1"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 3am
Register-ScheduledTask -TaskName "OpenGrok-Weekly-Reindex" -Action $action `
    -Trigger $trigger -Description "Re-index D:\CLAUDE in OpenGrok"
```

---

## Directory Layout (Final)

```
D:\CLAUDE\tools\opengrok\
  tomcat\                    ← Tomcat 10.1.54 unpacked
    bin\startup.bat
    bin\shutdown.bat
    conf\server.xml          ← port 8088
    webapps\source\          ← unpacked by Tomcat on first start
      WEB-INF\
        configuration.xml    ← written by first index run
  opengrok\
    opengrok-1.14.11\
      lib\opengrok.jar
  ctags\
    ctags.exe                ← v6.1.0 portable
  data\                      ← index data (large, gitignore this)
  INSTALL.md                 ← this file
  start_opengrok.cmd         ← double-click launcher
  reindex.ps1                ← weekly reindex script
```

---

## Browsing Your Code

**URL:** http://localhost:8088/source/

**Key features:**
- Full-text search across all files in `D:\CLAUDE\`
- Symbol cross-reference (click a function name → see all uses)
- Directory tree navigation
- File annotation / blame view
- Search scoped to a subdirectory (e.g., only `whatsapp-bridge\`)

**Useful search examples:**
- `ara-action-1` → find all files referencing the Ara action schema
- `def handle_` → all Python handler functions
- `ALLOWED_NUMBERS` → see every place the WA allowlist is defined
- `type:py path:whatsapp-bridge` → Python files in that folder only

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Tomcat starts but port 8088 already in use | Check `netstat -an \| findstr 8088` — another process owns the port. Change to 8089 in `server.xml`. |
| `configuration.xml` not found | Run the index step (5c) before opening the browser. |
| ctags not found during indexing | Verify path in reindex.ps1, check Defender exclusion. |
| WAR deployed but blank page | Check `tomcat\logs\catalina.out` for Java errors. Most common: wrong Java version (need 11+, prefer 21). |
| Index runs but no results | Confirm `SRC_ROOT` path is correct in reindex.ps1. Try searching a known filename. |

---

*iddoperez.ai — local tooling, always free*
