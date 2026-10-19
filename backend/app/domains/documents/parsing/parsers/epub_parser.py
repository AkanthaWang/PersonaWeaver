from html.parser import HTMLParser
from pathlib import PurePosixPath, Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile


_CONTAINER_NS = {"container": "urn:oasis:names:tc:opendocument:xmlns:container"}
_OPF_NS = {"opf": "http://www.idpf.org/2007/opf"}
_BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "dd",
    "div",
    "dl",
    "dt",
    "figcaption",
    "figure",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self._parts.append(text)

    def get_text(self) -> str:
        lines = []
        for line in "".join(self._parts).splitlines():
            normalized = " ".join(line.split())
            if normalized:
                lines.append(normalized)
        return "\n".join(lines)


def _read_text_member(archive: ZipFile, member_name: str) -> str:
    raw = archive.read(member_name)
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _resolve_content_opf_path(archive: ZipFile) -> str:
    try:
        container_xml = archive.read("META-INF/container.xml")
        root = ElementTree.fromstring(container_xml)
        rootfile = root.find(".//container:rootfile", _CONTAINER_NS)
        if rootfile is not None and rootfile.get("full-path"):
            return rootfile.get("full-path") or ""
    except (KeyError, ElementTree.ParseError):
        pass

    opf_files = [name for name in archive.namelist() if name.lower().endswith(".opf")]
    if not opf_files:
        raise ValueError("Invalid EPUB file, missing package .opf file.")
    return opf_files[0]


def _spine_item_paths(archive: ZipFile, opf_path: str) -> list[str]:
    opf_xml = archive.read(opf_path)
    root = ElementTree.fromstring(opf_xml)
    manifest = {
        item.get("id"): item.get("href")
        for item in root.findall(".//opf:manifest/opf:item", _OPF_NS)
        if item.get("id") and item.get("href")
    }
    spine_ids = [
        itemref.get("idref")
        for itemref in root.findall(".//opf:spine/opf:itemref", _OPF_NS)
        if itemref.get("idref")
    ]

    if not manifest:
        manifest = {
            item.get("id"): item.get("href")
            for item in root.findall(".//{*}manifest/{*}item")
            if item.get("id") and item.get("href")
        }
    if not spine_ids:
        spine_ids = [
            itemref.get("idref")
            for itemref in root.findall(".//{*}spine/{*}itemref")
            if itemref.get("idref")
        ]

    base_dir = PurePosixPath(opf_path).parent
    paths: list[str] = []
    for item_id in spine_ids:
        href = manifest.get(item_id)
        if href:
            paths.append(str(base_dir / href))

    if paths:
        return paths

    return [
        str(base_dir / href)
        for href in manifest.values()
        if href.lower().endswith((".xhtml", ".html", ".htm"))
    ]


def _html_to_text(html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    parser.close()
    return parser.get_text()


def parse_epub(file_path: Path) -> str:
    try:
        with ZipFile(file_path) as archive:
            opf_path = _resolve_content_opf_path(archive)
            chapter_paths = _spine_item_paths(archive, opf_path)
            sections = [
                text
                for chapter_path in chapter_paths
                for text in [_html_to_text(_read_text_member(archive, chapter_path))]
                if text
            ]
    except BadZipFile as exc:
        raise ValueError(f"Invalid EPUB zip file: {file_path}") from exc
    except ElementTree.ParseError as exc:
        raise ValueError(f"Invalid EPUB package XML: {file_path}") from exc
    except KeyError as exc:
        raise ValueError(f"Invalid EPUB file, missing referenced member: {exc}") from exc

    return "\n\n".join(sections)
