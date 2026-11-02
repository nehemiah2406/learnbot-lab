"""Write one named section of a Markdown report without touching the other sections."""

from pathlib import Path

HEADER = "# Results\n"


def replace_section(path, name, body):
    """Put body between <!-- BEGIN name --> and <!-- END name -->; add the section if new."""
    path = Path(path)
    begin, end = f"<!-- BEGIN {name} -->", f"<!-- END {name} -->"
    block = f"{begin}\n{body.strip()}\n{end}"
    text = path.read_text(encoding="utf-8") if path.is_file() else HEADER
    if begin in text and end in text:
        before, rest = text.split(begin, 1)
        after = rest.split(end, 1)[1]
        text = before + block + after
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    path.write_text(text, encoding="utf-8")
