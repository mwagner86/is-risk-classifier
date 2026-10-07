#!/usr/bin/env python
"""Write the English translations from tools/translations_en.py into the gettext catalogue.

Run after `make messages` (which extracts new msgids). Fails if a msgid has no translation, so
nothing untranslated slips into the English UI.

Usage: python tools/fill_po.py [--check]
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.translations_en import EN

PO = Path(__file__).resolve().parent.parent / "src" / "locale" / "en" / "LC_MESSAGES" / "django.po"
STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')


def unquote(block: str) -> str:
    return (
        "".join(STRING.findall(block))
        .encode()
        .decode("unicode_escape")
        .encode("latin-1")
        .decode("utf-8")
    )


def quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="only report missing translations")
    args = parser.parse_args()
    entries = PO.read_text(encoding="utf-8").split("\n\n")
    missing, out = [], []
    for entry in entries:
        msgid = re.search(r'^msgid ((?:".*"\n?)+)', entry, re.M)
        if not msgid or not unquote(msgid.group(1)):
            out.append(entry)  # header
            continue
        source = unquote(msgid.group(1))
        translation = EN.get(source)
        if translation is None:
            missing.append(source)
            out.append(entry)
            continue
        head = re.split(r"^msgstr", entry, maxsplit=1, flags=re.M)[0].rstrip("\n")
        head = "\n".join(line for line in head.split("\n") if line != "#, fuzzy")
        if isinstance(translation, tuple):
            out.append(
                f"{head}\nmsgstr[0] {quote(translation[0])}\nmsgstr[1] {quote(translation[1])}"
            )
        else:
            out.append(f"{head}\nmsgstr {quote(translation)}")
    if missing:
        print("missing English translations:", *missing, sep="\n  ", file=sys.stderr)
    if not args.check:
        PO.write_text("\n\n".join(out).rstrip("\n") + "\n", encoding="utf-8")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
