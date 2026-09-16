#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ALMA-MAIL MCP  --  a mail organ for the council.  Stdlib only, no pip.

Tools:
  mail_whoami          who am I, and is the credential loaded
  mail_list            list recent messages (IMAP)
  mail_read            read one message by uid
  mail_send            send a message, with attachments

Credential file (Claude never reads or echoes it):
  D:\\CLAUDE\\_secrets\\alma-mail.json
  {"address": "you@gmail.com", "app_password": "xxxxxxxxxxxxxxxx"}
Optional overrides: smtp_host, smtp_port, imap_host, imap_port (Gmail by default).

DRY RUN: mail_send without confirm=true builds the message and reports exactly
what WOULD be sent (recipients, subject, byte size, attachment names) and sends
nothing.  That is the default.
"""
import sys, os, json, ssl, smtplib, imaplib, email, mimetypes, traceback
from email.message import EmailMessage
from email.header import decode_header, make_header

CRED_PATH = os.environ.get("ALMA_MAIL_CRED", r"D:\CLAUDE\_secrets\alma-mail.json")
MAX_ATTACH_BYTES = 20 * 1024 * 1024


def load_cred():
    if not os.path.exists(CRED_PATH):
        raise RuntimeError(
            "No credential file at " + CRED_PATH + ". Create it with your address "
            "and a Google APP PASSWORD (not the account password): "
            '{"address": "...", "app_password": "..."}')
    with open(CRED_PATH, "r", encoding="utf-8") as fh:
        c = json.load(fh)
    for k in ("address", "app_password"):
        if not c.get(k):
            raise RuntimeError("credential file is missing '" + k + "'")
    c.setdefault("smtp_host", "smtp.gmail.com")
    c.setdefault("smtp_port", 465)
    c.setdefault("imap_host", "imap.gmail.com")
    c.setdefault("imap_port", 993)
    return c


def _dec(raw):
    if raw is None:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return str(raw)


# ---------------------------------------------------------------- tools

def t_mail_whoami(_a):
    try:
        c = load_cred()
    except Exception as e:
        return "NOT CONFIGURED. " + str(e)
    return ("configured: %s  (smtp %s:%s, imap %s:%s)  credential file present, "
            "password not shown" % (c["address"], c["smtp_host"], c["smtp_port"],
                                    c["imap_host"], c["imap_port"]))


def t_mail_list(a):
    c = load_cred()
    limit = int(a.get("limit", 10))
    mailbox = a.get("mailbox", "INBOX")
    query = a.get("query", "ALL")
    M = imaplib.IMAP4_SSL(c["imap_host"], int(c["imap_port"]))
    try:
        M.login(c["address"], c["app_password"])
        M.select(mailbox, readonly=True)
        typ, data = M.search(None, query)
        uids = data[0].split()[-limit:]
        rows = []
        for uid in reversed(uids):
            typ, d = M.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            msg = email.message_from_bytes(d[0][1])
            rows.append("%s | %s | %s | %s" % (
                uid.decode(), _dec(msg.get("Date")),
                _dec(msg.get("From")), _dec(msg.get("Subject"))))
        return "\n".join(rows) if rows else "(no messages matched)"
    finally:
        try:
            M.logout()
        except Exception:
            pass


def t_mail_read(a):
    c = load_cred()
    uid = str(a["uid"])
    mailbox = a.get("mailbox", "INBOX")
    M = imaplib.IMAP4_SSL(c["imap_host"], int(c["imap_port"]))
    try:
        M.login(c["address"], c["app_password"])
        M.select(mailbox, readonly=True)
        typ, d = M.fetch(uid.encode(), "(RFC822)")
        msg = email.message_from_bytes(d[0][1])
        head = "FROM: %s\nTO: %s\nDATE: %s\nSUBJECT: %s\n\n" % (
            _dec(msg.get("From")), _dec(msg.get("To")),
            _dec(msg.get("Date")), _dec(msg.get("Subject")))
        body, atts = "", []
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            fn = part.get_filename()
            if fn:
                atts.append(_dec(fn))
            elif part.get_content_type() == "text/plain" and not body:
                body = part.get_payload(decode=True).decode(
                    part.get_content_charset() or "utf-8", "replace")
        if atts:
            head += "ATTACHMENTS: " + ", ".join(atts) + "\n\n"
        return head + body[:20000]
    finally:
        try:
            M.logout()
        except Exception:
            pass


def _build(c, a):
    m = EmailMessage()
    to = a["to"] if isinstance(a["to"], list) else [a["to"]]
    m["From"] = c["address"]
    m["To"] = ", ".join(to)
    rcpts = list(to)
    if a.get("cc"):
        cc = a["cc"] if isinstance(a["cc"], list) else [a["cc"]]
        m["Cc"] = ", ".join(cc)
        rcpts += cc
    m["Subject"] = a.get("subject", "")
    m.set_content(a.get("body", ""))
    names = []
    total = 0
    for p in a.get("attachments", []) or []:
        if not os.path.exists(p):
            raise RuntimeError("attachment not found: " + p)
        total += os.path.getsize(p)
        if total > MAX_ATTACH_BYTES:
            raise RuntimeError("attachments exceed %d MB" % (MAX_ATTACH_BYTES // 2 ** 20))
        ctype, enc = mimetypes.guess_type(p)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        with open(p, "rb") as fh:
            m.add_attachment(fh.read(), maintype=maintype, subtype=subtype,
                             filename=os.path.basename(p))
        names.append("%s (%.1f KB)" % (os.path.basename(p), os.path.getsize(p) / 1024.0))
    return m, rcpts, names


def t_mail_send(a):
    c = load_cred()
    m, rcpts, names = _build(c, a)
    raw = m.as_bytes()
    plan = ("TO: %s\nSUBJECT: %s\nATTACHMENTS: %s\nSIZE: %.1f KB\n\n--- BODY ---\n%s"
            % (", ".join(rcpts), m["Subject"],
               ", ".join(names) if names else "(none)",
               len(raw) / 1024.0, a.get("body", "")[:4000]))
    if not a.get("confirm"):
        return ("DRY RUN -- NOTHING WAS SENT. Pass confirm=true to actually send.\n\n"
                + plan)
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(c["smtp_host"], int(c["smtp_port"]), context=ctx) as s:
        s.login(c["address"], c["app_password"])
        s.send_message(m, from_addr=c["address"], to_addrs=rcpts)
    return "SENT.\n\n" + plan


TOOLS = [
    {"name": "mail_whoami",
     "description": "Report which mail address this server is configured for and whether "
                    "the credential file is present. Never reveals the password.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "mail_list",
     "description": "List recent messages over IMAP. Returns 'uid | date | from | subject' lines.",
     "inputSchema": {"type": "object", "properties": {
         "limit": {"type": "integer", "description": "how many, default 10"},
         "mailbox": {"type": "string", "description": "default INBOX"},
         "query": {"type": "string",
                   "description": "IMAP search, e.g. UNSEEN or FROM \"x@y\". Default ALL"}}}},
    {"name": "mail_read",
     "description": "Read one message by its IMAP uid (from mail_list).",
     "inputSchema": {"type": "object",
                     "properties": {"uid": {"type": "string"},
                                    "mailbox": {"type": "string"}},
                     "required": ["uid"]}},
    {"name": "mail_send",
     "description": "Send a message with optional file attachments. WITHOUT confirm=true it is "
                    "a DRY RUN that sends nothing and reports exactly what would go out.",
     "inputSchema": {"type": "object", "properties": {
         "to": {"type": ["string", "array"], "items": {"type": "string"}},
         "cc": {"type": ["string", "array"], "items": {"type": "string"}},
         "subject": {"type": "string"},
         "body": {"type": "string"},
         "attachments": {"type": "array", "items": {"type": "string"},
                         "description": "absolute local file paths"},
         "confirm": {"type": "boolean",
                     "description": "must be true to actually send; otherwise dry run"}},
         "required": ["to", "subject", "body"]}},
]
HANDLERS = {"mail_whoami": t_mail_whoami, "mail_list": t_mail_list,
            "mail_read": t_mail_read, "mail_send": t_mail_send}


# ---------------------------------------------------------------- MCP loop

def reply(rid, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": rid}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        method, rid = req.get("method"), req.get("id")
        if method == "initialize":
            reply(rid, {"protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "alma-mail", "version": "1.0.0"}})
        elif method is not None and method.startswith("notifications/"):
            continue
        elif method == "tools/list":
            reply(rid, {"tools": TOOLS})
        elif method == "tools/call":
            name = req["params"]["name"]
            args = req["params"].get("arguments") or {}
            try:
                text = HANDLERS[name](args)
                reply(rid, {"content": [{"type": "text", "text": text}]})
            except Exception as e:
                reply(rid, {"content": [{"type": "text",
                                         "text": "ERROR: " + str(e) + "\n"
                                                 + traceback.format_exc()[-800:]}],
                            "isError": True})
        elif rid is not None:
            reply(rid, error={"code": -32601, "message": "no such method: " + str(method)})


if __name__ == "__main__":
    main()
