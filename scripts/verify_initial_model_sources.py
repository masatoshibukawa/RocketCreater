"""Verify the reference extraction against a local literature checkout; never execute it."""

import argparse
import json
from pathlib import Path

from rocketwright.agent.design_projects import sha
from rocketwright.analysis.seeds import catalog


def verify(root):
    rows = []
    for key, source in catalog()["sources"].items():
        for file in source["files"]:
            path = root / file["path"]
            rows.append(
                dict(
                    source=key,
                    path=file["path"],
                    matches=path.is_file() and sha(path) == file["sha256"],
                )
            )
    return dict(files=rows, all_match=all(r["matches"] for r in rows))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("literature_checkout", type=Path)
    result = verify(p.parse_args().literature_checkout)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    raise SystemExit(0 if result["all_match"] else 1)
