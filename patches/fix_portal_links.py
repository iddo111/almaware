"""Stage corrected Sefaria collection links for the recovered portals site."""

from pathlib import Path


source = Path(r"D:\CLAUDE\iddoperez-portals-recovered\index.html")
target = source.with_name("index.truthfix.html")
if target.exists():
    raise RuntimeError(f"refusing to overwrite {target}")
text = source.read_text(encoding="utf-8")
replacements = {
    "https://www.sefaria.org.il/Mishneh_Torah": "https://www.sefaria.org/texts/Halakhah/Mishneh%20Torah",
    "https://www.sefaria.org.il/Shulchan_Arukh": "https://www.sefaria.org/texts/Halakhah/Shulchan%20Arukh",
}
for old, new in replacements.items():
    if text.count(old) != 1:
        raise RuntimeError(f"expected one match for {old}, found {text.count(old)}")
    text = text.replace(old, new, 1)
target.write_text(text, encoding="utf-8", newline="\n")
