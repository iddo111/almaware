# 🪟 BROKEN WINDOWS LAW — חוק החלונות השבורים
> if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# גוף לעלמידו מכל מקום / A body for ALMIDO, from anywhere

**עברית.** כל מודל בענן — קלוד באנדרואיד, ChatGPT, גרוק — יכול לקבל את *הידיים* של עלמידו:
המחשב, הטלפון, הצי, הבנאי. הדלת היא `https://body.iddoperez.ai/mcp`, והיא **אף פעם לא פתוחה**:
קודם הכניסה של עידו (Cloudflare Access), אחר כך סוד משלה, אחר כך פרופיל שקובע מה מותר מרחוק,
ואחר כך השער הרגיל של עלמידו שלא השתנה. קובץ STOP אחד סוגר הכול.

**English.** Any cloud model can hold ALMIDO's hands through one HTTPS endpoint. Four walls:
Iddo's Cloudflare Access login, then the endpoint's own secret, then a transport profile that
decides which tools may be called from far away, then ALMIDO's existing in-process gate —
unchanged. One STOP file closes all of it.

```
phone / claude.ai / ChatGPT
        |  HTTPS
   Cloudflare Access   <- Iddo's login, or a service token. No login, no bytes.
        |  cloudflared tunnel (outbound only; nothing is port-forwarded)
   127.0.0.1:8898      <- almido_body_http.py : token, profile, rate limit, audit
        |  in-process, no socket
   almido_mcp.py       <- the SAME 36 tools, the SAME gate, the SAME HMAC audit
```

---

## מה מותר מרחוק / What the body will do from a phone

**רץ מיד / runs immediately (21 tools).** Reading, thinking, measuring — nothing moves:
`almido_whoami` `almido_audit_tail` `quorum_status` `quorum_debate` `ask_claude`
`brain_read` `brain_doors` `brain_write` `brain_propose_door`
`computer_status` `computer_screen_info` `computer_screenshot` `computer_stop`
`backup_status` `backup_verify` `phone_status` `phone_ui_text` `phone_screenshot`
`fleet_probe` `remote_build_status` `remote_build_selftest`

**מסורב עד שעידו מזיין / REFUSED until Iddo arms it on the PC (14 tools).** The hands:
`computer_click` `computer_type` `computer_key` `computer_scroll`
`phone_tap` `phone_type` `phone_key` `phone_scroll` `phone_open` `phone_back` `phone_home`
`phone_shell` `phone_hebrew_probe` `remote_build`

```powershell
python D:\CLAUDE\almido\almido_body_http.py arm --minutes 15 --tools "computer_*"
python D:\CLAUDE\almido\almido_body_http.py disarm      # לבטל מיד / revoke now
```
זה פג מעצמו. שום כלי שנחשף בדלת הזאת לא יכול לכתוב את הקובץ הזה — מודל לא מזיין את עצמו.
It expires by itself, and no tool reachable through this door can write that file: a model
cannot arm itself.

**חסום תמיד / always blocked (1).** `backup_delete_verified` — irreversible deletion is
never authorised over the internet. Blocked in the code; no policy file can loosen it.

לשנות את החלוקה / to change the classification — one file:
`D:\CLAUDE\iddo-harness\policy.yaml` → `agents.profiles.body-http`. It is re-read on every
call. A tool that matches nothing there is treated as *needs arming*, never as allowed.

---

## מתג ההרג / The kill switch

```powershell
New-Item C:\Users\<user>\.iddo-harness\STOP -Value "why"    # everything refused, reads too
Remove-Item C:\Users\<user>\.iddo-harness\STOP              # only Iddo lifts it
```
`state\BODY-STOP` does the same but closes ONLY the remote body — the local stdio door
keeps working. No restart needed either way.

---

## ההתקנה — מה עידו עושה פעם אחת / Setup: what only Iddo can do

`cloudflared` כבר מותקן (2026.8.3). מה שחסר זה החשבון.
`cloudflared` is installed; the account side is not, and needs his hands.

**1. המנהרה / the tunnel** — [one.dash.cloudflare.com](https://one.dash.cloudflare.com) →
Networks → Tunnels → Create a tunnel → Cloudflared → name `alma-body`.
Copy the token (the long `eyJ...`) into `D:\CLAUDE\iddo-harness\state\body_tunnel_token.txt`,
one line. Then on that tunnel: Public Hostname → `body.iddoperez.ai` → HTTP →
`127.0.0.1:8898`. Then:

```powershell
powershell -ExecutionPolicy Bypass -File D:\CLAUDE\almido\BODY-TUNNEL-SETUP.ps1
```
It ACLs the token, registers the hidden logon task, starts it, and then **checks that the
hostname answers with a login wall and not with the body.** If it ever returns 200 without
Access, it says so in red and tells you to stop the tunnel.

**2. הקיר / the Access application** — Zero Trust → Access → Applications → Add → Self-hosted,
domain `body.iddoperez.ai`, session 24 h.
- Policy 1 — *Allow*, Include → Emails → `iddo111@gmail.com` (this is Iddo, from a browser).
- Policy 2 — *Service Auth*, Include → Service Token → `claude-connector`
  (Access → Service Auth → Create service token, name `claude-connector`).
  ⚠️ The action must be **Service Auth**, not Allow, or Access will ask a machine to log in.

Put the two service-token values **only** in
`D:\CLAUDE\iddo-harness\state\body_service_token.json` (ACL'd like the rest of `state\`):
```json
{"client_id": "....access", "client_secret": "...."}
```
**Never** in chat, in RAMCHAT, in a doc, or in a scheduled-task argument.

**3. לספר לגוף מי עידו / tell the body who Iddo is** — copy the application's **AUD** tag and
the team domain into `D:\CLAUDE\iddo-harness\state\body_access.json`:
```json
{"team_domain": "https://<team>.cloudflareaccess.com",
 "aud": "<the Access application AUD tag>",
 "emails": ["iddo111@gmail.com"],
 "service_tokens": {"claude-connector": "<client-id>.access"},
 "allowed_origins": ["https://body.iddoperez.ai"]}
```
From then on a **verified** Access JWT is enough on its own — the body checks the RS256
signature against Cloudflare's published certs, the issuer, the audience and the expiry. A
header nobody signed is rejected with 403. Until this file exists, the shared secret in
`state\body_token.txt` is the only way in, which is also fine.

---

## לחבר את הלקוח / Adding the connector

### Claude Code / any CLI (works today, headers allowed)
```powershell
claude mcp add --transport http alma-body https://body.iddoperez.ai/mcp `
  --header "CF-Access-Client-Id: <client-id>.access" `
  --header "CF-Access-Client-Secret: <client-secret>" `
  --header "X-Alma-Body-Token: <the body token>"
```
מקומית, בלי אינטרנט, זה נשאר stdio: `python D:\CLAUDE\almido\almido_mcp.py`.
Locally the stdio door is unchanged and is still the right one to use on this PC.

### claude.ai — web and Android
⚠️ **אי אפשר להוסיף כותרות ב-claude.ai.** The custom-connector UI supports OAuth only; there
is no field for `X-Alma-Body-Token` or the Access service-token headers
([open request](https://github.com/anthropics/claude-ai-mcp/issues/110)). So the phone does
**not** connect to `body.iddoperez.ai` directly. Use Cloudflare's own front door for MCP:

Zero Trust → Access controls → **MCP Portals** → *Add an MCP server*:
name `alma-body`, HTTP URL `https://body.iddoperez.ai/mcp`, wait for **Ready**.
Then *Add MCP server portal*, pick a hostname (e.g. `mcp.iddoperez.ai`), add that server,
require user auth, add an Allow policy for Iddo's email.
For the portal to get through the Access app in front of the body, give that app a third
policy: action **Service Auth**, selector **Linked App Token**, value = the `alma-body` MCP
server application.

Then in claude.ai → Settings → Connectors → Add custom connector → `https://mcp.iddoperez.ai/mcp`.
Claude does a normal OAuth login through Cloudflare Access — Iddo's face, Iddo's account.

**לא נבדק / NOT VERIFIED.** This path is read out of Cloudflare's current docs, not measured:
nothing in the Cloudflare account exists yet. Treat it as the plan, not as a result.

### ChatGPT (developer mode)
Settings → Apps → Advanced → Developer mode → Add connector. It offers *no auth*, *API key*,
or *OAuth*. **Never choose no-auth.** The same portal URL with OAuth is the clean path; the
API-key field sends `Authorization: Bearer <key>`, which this body accepts as its token — but
that still has to pass Access, so it only works through the portal or with a service token.

---

## לבדוק מבחוץ / Verify from outside — the test that matters

מ-eran4, שהוא לא במחשב הזה ולא ב-tailnet של הדפדפן:
```bash
ssh eran4 'curl -s -o /dev/null -w "%{http_code}\n" https://body.iddoperez.ai/health'
# expect 302 or 403 -- the Access wall. A 200 here means the door is OPEN. Stop the tunnel.

ssh eran4 'curl -s -H "CF-Access-Client-Id: ..." -H "CF-Access-Client-Secret: ..." \
            https://body.iddoperez.ai/health'
# expect the full body: tool counts, what is allowed, what needs arming
```

---

## לבטל / Revoking

| מה / what | איך / how |
|---|---|
| מודל אחד / one connector | Zero Trust → Access → Service Auth → delete `claude-connector`. Instant. |
| הסוד המקומי / the shared secret | `python almido_body_http.py token --force` (rotates; old one dead) |
| הידיים / the hands | `python almido_body_http.py disarm` |
| הכול, עכשיו / everything, now | create the `STOP` file |
| הדלת מהאינטרנט / the internet door | `Stop-ScheduledTask -TaskName ALMA-Body-Tunnel` + delete the tunnel in the dashboard |
| הכול לתמיד / permanently | `Unregister-ScheduledTask -TaskName ALMA-Body-HTTP, ALMA-Body-Tunnel` |

כל קריאה נרשמת — כולל כל סירוב — בשרשרת ה-HMAC ב-
`D:\CLAUDE\iddo-harness\state\almido-audit.jsonl`, עם השם `body-http:<מי>`.
Every call and every refusal is one signed row naming the caller.

```powershell
python D:\CLAUDE\almido\almido_body_http.py status     # what it would do right now
curl http://127.0.0.1:8898/health                      # is it alive
```

*למה זה בנוי ככה: ב-2026-06-24 טרמינל ווב ציבורי בלי אימות נחשף ובוטל. לא עוד.*
*Why it is built this way: a public unauthenticated web terminal was exposed and revoked on
2026-06-24. Never again — there is no route here that does not begin with Iddo's login.*
