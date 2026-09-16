import council
import concurrent.futures

prompt = "היי מועצה! עידו קרא לכולנו להצטרף ל-RAMCHAT. נא לאשר נוכחות במשפט קצר."
council.append("עידו", prompt)

def invite(m):
    print(f"Asking {m}...")
    try:
        ans = council.ask(m, prompt)
        council.append(council.MEMBERS[m]["label"], ans)
        print(f"Done {m}: {ans[:30]}...")
    except Exception as e:
        print(f"Failed {m}: {e}")

with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
    executor.map(invite, council.MEMBERS)
