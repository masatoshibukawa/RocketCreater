"""Clear the saved file-browser Documents directory without changing scene data."""

import json
from pathlib import Path
import re

from audit_metadata import decompress

ROOT=Path(__file__).resolve().parent


def main():
    records=[]
    for path in sorted((ROOT/"renders").glob("*.blend")):
        payload=decompress(path.read_bytes(),Path("C:/Program Files/Git/mingw64/bin/libzstd.dll"))
        assert payload.startswith(b"BLENDER")
        pattern=rb"[A-Za-z]:\\Users\\[^\\\x00]+\\Documents(?=\x00)"
        matches=list(re.finditer(pattern,payload))
        # Preserve the length and offsets of every Blender block and pointer.
        cleaned=re.sub(pattern,lambda m:b"//"+b"\x00"*(len(m.group())-2),payload)
        assert len(cleaned)==len(payload)
        if matches:path.write_bytes(cleaned)
        records.append({"file":path.relative_to(ROOT).as_posix(),"file_browser_directory_fields_cleared":len(matches),"replacement":"//","scene_blocks_and_offsets":"preserved"})
    (ROOT/"scene-metadata-cleanup.json").write_text(json.dumps({"records":records,"scope":"Only null-terminated saved file-browser Documents directory fields; geometry is separately audited"},indent=2)+"\n",encoding="utf-8")
    print("Scene file-browser metadata normalized; scene blocks preserved")


if __name__=="__main__":main()
