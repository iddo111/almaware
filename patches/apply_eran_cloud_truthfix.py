"""Create a deterministic, fail-closed truth-fix candidate for eran-cloud/join.py.

This stages a new file; it never overwrites the source. Every replacement must
match exactly once so upstream edits cannot be silently lost.
"""

from pathlib import Path


SOURCE = Path(r"D:\CLAUDE\eran-cloud\join.py")
TARGET = Path(r"D:\CLAUDE\eran-cloud\join.py.truthfix")


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"expected exactly one match, found {text.count(old)}: {old[:80]!r}")
    return text.replace(old, new, 1)


def main() -> None:
    if TARGET.exists():
        raise RuntimeError(f"refusing to overwrite staged file: {TARGET}")
    text = SOURCE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        """With no coordinator reachable the client runs in **--dry-run** mode: it prints
the intended loop end-to-end (register -> pull -> train -> delta -> push) using a
tiny in-memory toy model, so you can read the whole shape before wiring the API.

Run:
    python join.py --coordinator https://grid.almaware/eran --provider gcloud
    python join.py --dry-run --provider colab        # no coordinator needed
""",
        """With ``--dry-run`` the client prints the intended loop end-to-end
(register -> pull -> train -> delta -> push) using a tiny in-memory toy model.
It never silently changes a failed live run into a simulation.

Run:
    py -3.13 join.py --dry-run --provider gcloud
    # Live mode remains unavailable until a real HTTPS coordinator is published.
""",
    )
    text = replace_once(text, "import urllib.error\n", "import urllib.error\nimport urllib.parse\n")
    text = replace_once(
        text,
        """        self.base_url = (base_url or "").rstrip("/")
        self.dry_run = dry_run
        self.timeout = timeout

    def _post(self, path: str, payload: dict) -> dict:
""",
        """        self.base_url = self._validated_url(base_url) if not dry_run else ""
        self.dry_run = dry_run
        self.timeout = timeout

    @staticmethod
    def _validated_url(base_url: str | None) -> str:
        raw = (base_url or "").strip()
        parsed = urllib.parse.urlsplit(raw)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("live coordinator must be a real HTTPS URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("coordinator URL cannot contain credentials, query, or fragment")
        if parsed.path not in ("", "/"):
            raise ValueError("coordinator URL cannot contain a path")
        return raw.rstrip("/")

    def _post(self, path: str, payload: dict) -> dict:
""",
    )
    text = replace_once(
        text,
        """    p.add_argument("--dry-run", action="store_true",
                   help="Print the intended loop with no live Coordinator.")
""",
        """    p.add_argument("--dry-run", action="store_true",
                   help="Print the intended loop with no live Coordinator.")
    p.add_argument("--consent", choices=("yes",), default=None,
                   help="Required in live mode: confirms an account you own and control.")
""",
    )
    text = replace_once(
        text,
        """    # No coordinator + not explicitly dry-run -> fall back to dry-run, loudly.
    dry_run = args.dry_run or not args.coordinator
    if dry_run and not args.dry_run:
        print("[note] no --coordinator given -> running in DRY-RUN mode.\\n")
""",
        """    dry_run = args.dry_run
    if not dry_run and not args.coordinator:
        print("[error] live mode requires --coordinator. Use --dry-run for the verified toy demo.")
        return 2
    if not dry_run and args.consent != "yes":
        print("[error] live mode requires --consent yes.")
        return 2
""",
    )
    text = replace_once(
        text,
        """    except (urllib.error.URLError, OSError) as e:
        print(f"  [!] coordinator unreachable ({e}); switching to dry-run.\\n")
        coord.dry_run = True
""",
        """    except (urllib.error.URLError, OSError) as e:
        print(f"  [!] coordinator unreachable ({e}); live run stopped.\\n")
        return 1
""",
    )
    TARGET.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
