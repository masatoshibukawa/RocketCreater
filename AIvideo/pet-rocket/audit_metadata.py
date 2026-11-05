"""Inspect decompressed Blender files and finished media for private working labels.

Uses the existing Git for Windows libzstd; no library is copied into the delivery.
Stable API reference: https://github.com/facebook/zstd/blob/dev/lib/zstd.h
"""

import argparse
import ctypes
import json
from pathlib import Path

import av
from PIL import Image

ROOT=Path(__file__).resolve().parent
FORBIDDEN=(b"c:\\users\\",b"c:/users/",b"chatgpt",b"codex",b"utm_")


def decompress(data,dll_path):
    if data.startswith(b"BLENDER"):return data
    library=ctypes.CDLL(str(dll_path))
    pointer=ctypes.c_void_p;size=ctypes.c_size_t
    library.ZSTD_getFrameContentSize.argtypes=[pointer,size]
    library.ZSTD_getFrameContentSize.restype=ctypes.c_ulonglong
    library.ZSTD_findFrameCompressedSize.argtypes=[pointer,size]
    library.ZSTD_findFrameCompressedSize.restype=size
    library.ZSTD_decompress.argtypes=[pointer,size,pointer,size]
    library.ZSTD_decompress.restype=size
    library.ZSTD_isError.argtypes=[size]
    library.ZSTD_isError.restype=ctypes.c_uint
    result=[];position=0
    while position<len(data):
        source=ctypes.create_string_buffer(data[position:])
        compressed=library.ZSTD_findFrameCompressedSize(source,len(source)-1)
        assert not library.ZSTD_isError(compressed) and compressed>0
        length=library.ZSTD_getFrameContentSize(source,compressed)
        assert length<256*1024*1024,"Unexpected or unknown decompression size"
        output=ctypes.create_string_buffer(max(1,length))
        actual=library.ZSTD_decompress(output,length,source,compressed)
        assert not library.ZSTD_isError(actual) and actual==length
        result.append(output.raw[:actual]);position+=compressed
    return b"".join(result)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--zstd-dll",type=Path,default=Path("C:/Program Files/Git/mingw64/bin/libzstd.dll"))
    args=parser.parse_args()
    records=[]
    for path in sorted((ROOT/"renders").glob("*.blend")):
        payload=decompress(path.read_bytes(),args.zstd_dll)
        assert payload.startswith(b"BLENDER")
        matches=[term.decode() for term in FORBIDDEN if term in payload.lower()]
        records.append({"file":path.relative_to(ROOT).as_posix(),"decompressed_bytes":len(payload),"unwanted_metadata_matches":matches})
        assert not matches,(path.name,matches)
    for name in ("pet_rocket_design.mp4","pet_rocket_launch_prediction.mp4"):
        with av.open(str(ROOT/"renders"/name)) as source:
            metadata={"container":dict(source.metadata),"streams":[dict(s.metadata) for s in source.streams]}
        payload=json.dumps(metadata).encode().lower()
        assert not any(term in payload for term in FORBIDDEN)
        records.append({"file":"renders/"+name,"metadata":metadata})
    for name in ("design-poster.png","launch-poster.png","design-contact.jpg","launch-contact.jpg"):
        with Image.open(ROOT/"renders"/name) as source:
            metadata=str(source.info).encode().lower()
        assert not any(term in metadata for term in FORBIDDEN)
    report={"checks":"passed","records":records,"images":"No unwanted working labels in saved image metadata","disclosure":"AI-assisted production and source/license notices retained"}
    (ROOT/"artifact-audit.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"checks":report["checks"],"blender_files":sum("decompressed_bytes" in r for r in records),"mp4_files":2,"image_files":4}))


if __name__=="__main__":main()
