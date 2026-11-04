"""Inspect the user-supplied public reference without browser credentials."""

import argparse
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


class PublicMetadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.metadata = {}
        self.sources = []
        self.jsonld = []
        self.capture_json = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            key = attrs.get("property", attrs.get("name", ""))
            if key.startswith("og:") or key in {"description", "author"}:
                self.metadata[key] = attrs.get("content")
        if tag in {"video", "source"}:
            self.sources.append(attrs)
        if tag == "script":
            self.capture_json = attrs.get("type") == "application/ld+json"

    def handle_endtag(self, tag):
        if tag == "script":
            self.capture_json = False

    def handle_data(self, data):
        if self.capture_json:
            try:
                self.jsonld.append(json.loads(data))
            except json.JSONDecodeError:
                pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://lnkd.in/p/g9TsR-i4")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = Request(args.url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=40) as response:
        content = response.read().decode("utf-8", "replace")
        parts = urlsplit(response.url)
        public_url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    metadata = PublicMetadata()
    metadata.feed(content)
    result = {
        "requested_url": args.url,
        "resolved_url_without_tracking": public_url,
        "metadata": metadata.metadata,
        "video_elements": metadata.sources,
        "jsonld": metadata.jsonld,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "public_url": public_url,
        "title": metadata.metadata.get("og:title"),
        "video_count": len(metadata.sources),
        "duration": next((item.get("duration") for item in metadata.jsonld if item.get("@type") == "VideoObject"), None),
        "local_metadata": str(args.output),
    }, ensure_ascii=True))


if __name__ == "__main__":
    main()
