from __future__ import annotations

from functools import cached_property
from bs4 import BeautifulSoup
from ebooklib import epub
import logging
import cloudscraper
import arrow
import ftfy
from typing import List, Optional, Dict
import re
import mimetypes
import math
from codecs import encode
from hashlib import sha1
from pathlib import Path
import uuid
from python_requests import Connection, set_cache_directory

from . import __name__

"""
try:
    import http.client as http_client
except ImportError:
    # Python 2
    import httplib as http_client
http_client.HTTPConnection.debuglevel = 1

# You must initialize logging, otherwise you'll not see debug output.
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True
"""

set_cache_directory(Path("/tmp", __name__))
log = logging.getLogger(__name__)


CHAPTER_MATCH = re.compile(
    r"(?P<url_root>.*)/read/(?P<story_id>\d*)-(?P<slug>.*?)/chapter/(?P<chapter_id>\d*)"
)
STORY_MATCH = re.compile(r"(?P<url_root>.*)/series/(?P<story_id>\d*)/(?P<slug>[a-z-]*)")
DATE_MATCH = re.compile("Last updated: .*")

__assets__ = str(Path(Path(__file__).parent, "assets"))




class Asset:
    """
    - `content`: the `bytes` content of the image
    - `relpath`: "static/{fname}{ext}"
        - `fname`: a SHA-1 hash of the URL
        - `ext`: a mimetypes guessed extension
    - `mimetype`: mimetype of the asset
    - `uid`: `fname`
    """
    success: bool = False
    url: str        # indexes by url
    content: bytes  # content of asset

    @cached_property
    def mimetype(self) -> str:
        mimetype, _ = mimetypes.guess_type(self.url)
        return mimetype
    
    @cached_property
    def ext(self) -> str:
        return mimetypes.guess_extension(self.mimetype)
    
    @cached_property
    def uid(self) -> str:
        """
        SHA-1 hash of the URL
        """
        return sha1(encode(self.url, "utf-8")).hexdigest()

    @cached_property
    def filename(self) -> str:
        return f"{self.uid}{self.ext}"
    
    @cached_property
    def relpath(self) -> str:
        return f"static/{self.filename}"

    def __init__(self, url: str, connection: Optional[Connection] = None):
        self.url = url
        self.connection = connection or Connection()

        resp = self.connection.get(self.url)
        self.content = resp.content
        self.success = True


class ScribbleChapter:
    parent: ScribbleBook

    index: int
    title: str
    text: str   # HTML content of chapter
    date: arrow.Arrow

    def __init__(self, parent: ScribbleBook, url: str, connection: Connection):
        self.parent = parent
        self.source_url = url

        self.connection = connection
        self.add_asset = self.parent.add_asset

    def __str__(self):
        return (
            f"ScribbleChapter(\n"
            f"  Index: {self.index}\n"
            f"  Title: {self.title}\n"
            f"  Date: {self.date.format('YYYY-MM-DD') if self.date else 'Unknown'}\n"
            f"  Url: {self.source_url}\n"
            f")"
        )
    
    def load(self):
        resp = self.connection.get(self.source_url)
        soup = BeautifulSoup(resp.text, "lxml")

        if self.parent.disable_author_quotes:
            for tag in soup.select('.wi_authornotes'):
                tag.decompose()

        for tag in soup.find_all(lambda x: x.has_attr("lang")):
            if tag["lang"] not in self.parent.languages:
                log.debug(f'Found language {tag["lang"]}')
                self.parent.languages.append(tag["lang"])

        t = soup.find(class_="chapter-title")
        self.title = t.text
        log.info(f"{self.parent.title} Chapter {self.index}: {self.title}")

        if not mimetypes.inited:
            mimetypes.init(None)

        for asset in soup.select("#chp_contents img[src]"):
            a = self.add_asset(asset["src"])
            if a is not None:
                asset["src"] = a.relpath
            
        header_tag = soup.new_tag("h2")
        header_tag.string = self.title
        chap_text = soup.find(class_="chp_raw").extract()
        chap_text.insert(0, header_tag)
        self.text = ftfy.fix_text(chap_text.prettify())
        self.fix_footnotes()

    def fix_footnotes(self):
        """
        Iterate through any footnotes and refactor them to ePub format
        """
        soup = BeautifulSoup(self.text, "lxml")
        footnotes = []
        for tag in soup.select(".modern-footnotes-footnote"):
            mfn = tag["data-mfn"].text
            log.debug(f"Found footnote {mfn}")
            anchor = tag.find_all("a")[-1]
            content_tag_element = soup.select(
                f".modern-footnotes-footnote__note[data-mfn={mfn}]"
            )
            content_tag = content_tag_element[0]
            if not anchor or not content_tag:
                return
            anchor["id"] = f"noteanchor-{mfn}"
            anchor["href"] = f"#note-{mfn}"
            anchor["epub:type"] = "noteref"

            content_tag.name = "aside"
            content_tag["id"] = f"note-{mfn}"
            content_tag["epub:type"] = "footnote"
            footnote_anchor = soup.new_tag("a", href=f"#noteanchor-{mfn}")
            footnote_anchor.string = f"{mfn}."
            content_tag_element.insert(0, footnote_anchor)
            footnotes.append(content_tag_element)
        if footnotes:
            tag = soup.find_all("p")[-1]
            footnote_header = soup.new_tag("h2", id="footnotes")
            footnote_header.string = "Footnotes"
            tag.append(footnote_header)
            tag.extend(footnotes)

        soup.smooth()
        self.text = ftfy.fix_text(soup.prettify())
    


class ScribbleBook:
    slug: str
    title: str
    languages: List[str]    # Dublin-core language codes
    cover_url: str
    date: arrow.Arrow
    intro: str
    description: str
    author: str
    publisher: str
    identifier: str # unique identifier (e.g. UUID, hosting site book ID, ISBN, etc.)
    genres: List[str]
    tags: List[str]
    rights: str

    chapter_count: int
    
    def __str__(self):
        return (
            f"BookMetadata(\n"
            f"  Title: {self.title}\n"
            f"  Author: {self.author}\n"
            f"  Identifier: {self.identifier}\n"
            f"  Languages: {', '.join(self.languages)}\n"
            f"  Published: {self.date.format('YYYY-MM-DD') if self.date else 'Unknown'}\n"
            f"  Publisher: {self.publisher}\n"
            f"  Genres: {', '.join(self.genres)}\n"
            f"  Tags: {', '.join(self.tags)}\n"
            f"  Rights: {self.rights}\n"
            f"  Cover URL: {self.cover_url}\n"
            f"  Description: {self.description[:75]}{'...' if len(self.description) > 75 else ''}\n"
            f")"
        )

    @cached_property
    def file_name(self) -> str:
        return f"{self.author} - {self.title}.epub"

    def __init__(self, url: str, file_name: Optional[str] = None, disable_author_quotes: bool = False):
        self.source_url = url
        self.assets: Dict[str, Asset] = {}

        self.disable_author_quotes = disable_author_quotes
        
        self.languages = []
        self.genres = []
        self.tags = []

        self.chapters: List[ScribbleChapter] = []

        self.connection = Connection(
            session=cloudscraper.create_scraper(),
            request_delay=3,
            additional_delay_per_try=1,
            max_retries=10,
        )

        if file_name is not None:
            self.file_name = file_name

    def add_asset(self, url: str) -> Optional[Asset]:
        if url is None:
            return
        if url.strip() == "":
            return
        
        a = Asset(url, self.connection)
        if a.success:
            self.assets[a.url] = a
            return a
        else:
            log.warning(f"couldn't fetch asset {url}")

    def load(self, limit_chapters: Optional[int] = None):
        self.load_metadata()
        print(f"{self.title} by {self.author} with {self.chapter_count} chapters:")

        self.fetch_chapters(limit=limit_chapters)
        if limit_chapters is not None:
            self.chapters = self.chapters[:limit_chapters]

        for i, chapter in enumerate(self.chapters):
            print(f"- {i+1}: {chapter.title}")
            chapter.load()

    def load_metadata(self) -> None:
        """
        Load the metadata for this object
        will make web requests
        """

        # parse info from the source url
        _parts = [p for p in self.source_url.split("/") if len(p.strip())]
        self.slug = _parts[-1]
        self.identifier = _parts[-2]

        resp = self.connection.get(self.source_url)
        soup = BeautifulSoup(resp.text, "lxml")

        for tag in soup.find_all(lambda x: x.has_attr("lang")):
            log.debug(f'Found language {tag["lang"]}')
            self.languages.append(tag["lang"])

        url = soup.find(property="og:url")["content"]
        if self.source_url != url:
            log.warning(f"Metadata URL mismatch!\n\t{self.source_url}\n\t{url}")

        self.title = soup.find(property="og:title")["content"]

        self.cover_url = soup.find(property="og:image")["content"] or ""
        self.add_asset(self.cover_url)

        self.date = arrow.get(
            soup.find("span", title=DATE_MATCH)["title"][14:], "MMM D, YYYY hh:mm A"
        )
        description = soup.find(class_="wi_fic_desc")
        self.intro = ftfy.fix_text(description.prettify())
        self.description = ftfy.fix_text(description.text)
        self.author = soup.find(attrs={"name": "twitter:creator"})["content"]
        self.publisher = soup.find(property="og:site_name")["content"]
        
        self.genres = [a.string for a in soup.find_all(class_="fic_genre")]
        self.tags = [a.string for a in soup.find_all(class_="stag")]
        self.chapter_count = int(soup.find(class_="cnt_toc").text)


        imgs = soup.find(class_="sb_content copyright").find_all("img")
        self.rights = ""
        for img in imgs:
            if "copy" not in img["class"]:
                continue
            self.rights = ftfy.fix_text(img.next.string)

    def fetch_chapters(self, limit: Optional[int] = None) -> None:
        """
        Fetch the chapters for the work, based on the TOC API
        """
        page_count = math.ceil(self.chapter_count / 15)
        log.debug(
            f"Expecting {self.chapter_count} chapters, page_count={page_count}"
        )

        if limit is not None:
            page_count = min(page_count, limit)

        for page in range(1, page_count + 1):
            chapter_resp = self.connection.post(
                "https://www.scribblehub.com/wp-admin/admin-ajax.php",
                {
                    "action": "wi_getreleases_pagination",
                    "pagenum": page,
                    "mypostid": self.identifier,
                },
                cache_identifier=f"pagenum{page}mypostid{self.identifier}",
            )

            chapter_soup = BeautifulSoup(chapter_resp.text, "lxml")
            for chapter_tag in chapter_soup.find_all(class_="toc_w"):
                chapter = ScribbleChapter(self, chapter_tag.a["href"], self.connection)
                chapter.index = int(chapter_tag["order"])
                chapter.title = chapter_tag.a.text
                chapter.date = arrow.get(
                    chapter_tag.span["title"], "MMM D, YYYY hh:mm A"
                )
                self.chapters.append(chapter)

        self.chapters.sort(key=lambda x: x.index)

    def build(self): 
        book = epub.EpubBook()
        
        # set up metadata
        book.add_metadata("DC", "identifier", f"uuid:{uuid.uuid4()}", {"id": "BookId"})
        book.add_metadata(
            "DC", "identifier", f"url:{self.source_url}", {"id": "Source"}
        )
        book.add_metadata("DC", "subject", ",".join(self.tags), {"id": "tags"})
        book.add_metadata(
            "DC", "subject", ",".join(self.genres), {"id": "genre"}
        )
        book.set_title(self.title)

        book.add_metadata("DC", "date", self.date.isoformat())
        book.add_author(self.author)
        book.add_metadata("DC", "publisher", self.publisher)
        book.add_metadata(
            "DC",
            "rights",
            f"Copyright © {self.date.year} {self.author} {self.rights}",
        )
        book.add_metadata("DC", "description", self.description)

        # set languages; assume the first one is the "main" language
        main_lang = self.languages[0]
        book.set_language(main_lang)
        if len(self.languages) > 1:
            langs = set(self.languages[1:])
            langs.remove(main_lang)
            for lang in langs:
                book.add_metadata("DC", "language", lang)

        # add cover image
        if self.cover_url is not None and self.cover_url in self.assets:
            cover = self.assets[self.cover_url]
            book.set_cover(f"cover{cover.ext}", cover.content)

        # add style
        style_path = Path(__assets__, "scribblehub.css")
        if style_path.exists():
            styles = style_path.read_text("utf-8")
            nav_css = epub.EpubItem(
                uid="style_nav",
                file_name="style/nav.css",
                media_type="text/css",
                content=styles,
            )
            book.add_item(nav_css)
        else:
            log.warning("couldn't find styles in %s", str(style_path))

        # add assets from the web
        for asset in self.assets.values():
            book.add_item(
                epub.EpubImage(
                    uid=asset.uid,
                    file_name=asset.relpath,
                    media_type=asset.mimetype,
                    content=asset.content,
                )
            )

        # add chapters
        toc_chap_list = []
        intro = epub.EpubHtml(
            title="Introduction", file_name="intro.xhtml", content=self.intro
        )
        intro.add_item(nav_css)
        book.add_item(intro)

        for chapter in self.chapters:
            c = epub.EpubHtml(
                title=chapter.title,
                file_name=f"chapter{chapter.index}.xhtml",
                content=chapter.text,
            )
            c.add_item(nav_css)
            book.add_item(c)
            toc_chap_list.append(c)

        # set up toc
        book.toc = [
            epub.Link("intro.xhtml", "Introduction", "intro"),
        ]
        book.toc.extend(toc_chap_list)
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        # create spine, add cover page as first page
        book.spine = ["cover", "intro", "nav"]
        book.spine.extend(toc_chap_list)

        # create epub file
        epub.write_epub(self.file_name, book, {})
