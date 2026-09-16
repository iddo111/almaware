import json

path = "/home/alma/.config/muse/settings.json"
d = json.load(open(path, encoding="utf-8"))
d.setdefault("mcpServers", {})
d["mcpServers"].update({
    "ramchat-muse": {
        "command": "/mnt/c/Program Files/Python312/python.exe",
        "args": [r"D:\CLAUDE\RAMCHAT\ramchat_mcp_qwen.py"],
        "cwd": r"D:\CLAUDE\RAMCHAT",
        "env": {"PYTHONIOENCODING": "utf-8", "RAMCHAT_MCP_AUTHOR": "muse-code"},
    },
    "brain2": {
        "command": "/mnt/c/Program Files/Python312/python.exe",
        "args": [r"D:\CLAUDE\alma-brain2\brain2_mcp.py"],
        "cwd": r"D:\CLAUDE\alma-brain2",
        "env": {"PYTHONIOENCODING": "utf-8"},
    },
    "desktop-commander": {
        "command": "/mnt/c/Program Files/nodejs/node.exe",
        "args": [r"C:\Users\<user>\AppData\Roaming\npm\node_modules\@wonderwhy-er\desktop-commander\dist\index.js"],
    },
})
json.dump(d, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("ok")
