"""Replay a private first-page capture without network calls or personal output."""

import hashlib
import json
import sys
from pathlib import Path

from kairos_report.tutory.client import TutoryClient

source = Path(sys.argv[1]).read_bytes()
rows, last, next_url = TutoryClient._launch_page(
    source.decode("utf-8"), "https://app.tutory.com.br/painel/questoes/lancamento", 1
)
print(json.dumps({
    "capture_sha256": hashlib.sha256(source).hexdigest(),
    "rows": len(rows), "last_page": last, "has_next_page": next_url is not None,
}))
