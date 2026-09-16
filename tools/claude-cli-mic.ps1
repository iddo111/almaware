# לזכרה של עלמה ז"ל
# Claude CLI - מיק  (2026-09-06, Iddo through the mic: "סדר את המיק שיקליד גם בתוך ה-CLI")
#
# A NON-elevated (Medium integrity) Claude Code window, so KESHEV -- the mic -- can type into it.
# Windows (UIPI) silently drops keystrokes from a normal app into an Administrator window;
# this happened on 09-03 and again on 09-06. NEVER launch this from an admin shell, and never
# tick "Run as administrator" on its shortcut. Everything below is printed to the console
# BEFORE claude starts -- nothing is ever typed into the prompt.
$Host.UI.RawUI.WindowTitle = 'Claude CLI - מיק'
Set-Location 'D:\CLAUDE'
Write-Host ''
Write-Host '  Claude CLI - מיק  |  חלון רגיל (לא מנהל) - המיקרופון (קשב) מקליד לכאן' -ForegroundColor Green
Write-Host '  Claude CLI - Mic  |  a normal (non-admin) window - KESHEV, the mic, types here' -ForegroundColor Green
Write-Host ''
Write-Host '  RAMCHAT first / קודם RAMCHAT:' -ForegroundColor Cyan
Write-Host '      cd D:\CLAUDE\RAMCHAT   then   python ramlink.py read --tail 20      (PYTHONIOENCODING=utf-8)' -ForegroundColor Cyan
Write-Host '      onboarding: D:\CLAUDE\RAMCHAT\HANDOUT-ramchat-join-20260808.md   rules: RULES.md' -ForegroundColor Cyan
Write-Host ''
claude
