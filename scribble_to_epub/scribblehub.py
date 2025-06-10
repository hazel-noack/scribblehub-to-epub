from __future__ import annotations

from functools import cached_property
from bs4 import BeautifulSoup
from ebooklib import epub
import logging
import cloudscraper
import arrow
import ftfy
from typing import Iterable, List
import re
import math

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



log = logging.getLogger(__name__)

headers = {"User-Agent": "node"}

CHAPTER_MATCH = re.compile(
    r"(?P<url_root>.*)/read/(?P<story_id>\d*)-(?P<slug>.*?)/chapter/(?P<chapter_id>\d*)"
)
STORY_MATCH = re.compile(r"(?P<url_root>.*)/series/(?P<story_id>\d*)/(?P<slug>[a-z-]*)")
DATE_MATCH = re.compile("Last updated: .*")


class BookMetadata:
    """
    Represents the metadata for the book
    """

    slug: str
    title: str
    languages: Iterable[str]    # Dublin-core language codes
    cover_url: str
    date: arrow.Arrow
    description: str
    author: str
    publisher: str
    identifier: str # unique identifier (e.g. UUID, hosting site book ID, ISBN, etc.)
    genres: Iterable[str]
    tags: Iterable[str]
    
    @cached_property
    def rights(self) -> str:
        return f"© {self.date.year} {self.author}"

    def __init__(self):
        self.languages = []
        self.genres = []
        self.tags = []

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


class ScribbleChapter:
    parent: ScribbleBook

    index: int
    title: str
    text: str   # HTML content of chapter
    date: arrow.Arrow

    def __init__(self, parent: ScribbleBook, url: str):
        self.parent = parent
        self.source_url = url

    def __str__(self):
        return (
            f"ScribbleChapter(\n"
            f"  Index: {self.index}\n"
            f"  Title: {self.title}\n"
            f"  Date: {self.date.format('YYYY-MM-DD') if self.date else 'Unknown'}\n"
            f"  Url: {self.source_url}\n"
            f")"
        )
    


class ScribbleBook:
    slug: str
    title: str
    languages: List[str]    # Dublin-core language codes
    cover_url: str
    date: arrow.Arrow
    description: str
    author: str
    publisher: str
    identifier: str # unique identifier (e.g. UUID, hosting site book ID, ISBN, etc.)
    genres: List[str]
    tags: List[str]

    chapter_count: int
    
    @cached_property
    def rights(self) -> str:
        return f"© {self.date.year} {self.author}"

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

    def __init__(self, url: str):
        self.source_url = url
        
        self.languages = []
        self.genres = []
        self.tags = []

        self.chapters: List[ScribbleChapter] = []

        # fetching metadata
        self.session = cloudscraper.create_scraper()
        self.load_metadata()
        print(str(self))

        self.get_chapters()

    def load_metadata(self) -> None:
        """
        Load the metadata for this object
        will make web requests
        """

        # parse info from the source url
        _parts = [p for p in self.source_url.split("/") if len(p.strip())]
        self.slug = _parts[-1]
        self.identifier = _parts[-2]

        html = self.session.get(self.source_url, headers=headers)
        print(html)

        html = self.session.get(self.source_url)
        soup = BeautifulSoup(html.text, "lxml")

        for tag in soup.find_all(lambda x: x.has_attr("lang")):
            log.debug(f'Found language {tag["lang"]}')
            self.languages.append(tag["lang"])

        url = soup.find(property="og:url")["content"]
        if self.source_url != url:
            log.warning(f"Metadata URL mismatch!\n\t{self.source_url}\n\t{url}")

        self.title = soup.find(property="og:title")["content"]
        print(f"Book Title: {self.title}")

        self.cover_url = soup.find(property="og:image")["content"] or ""
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
        for img in imgs:
            if "copy" not in img["class"]:
                continue
            self.rights = ftfy.fix_text(img.next.string)

    def get_chapters(self) -> None:
        """
        Fetch the chapters for the work, based on the TOC API
        """
        page_count = math.ceil(self.chapter_count / 15)
        log.debug(
            f"Expecting {self.chapter_count} chapters, page_count={page_count}"
        )

        for page in range(1, page_count + 1):
            chapter_resp = self.session.post(
                "https://www.scribblehub.com/wp-admin/admin-ajax.php",
                {
                    "action": "wi_getreleases_pagination",
                    "pagenum": page,
                    "mypostid": self.identifier,
                },
                headers=headers,
            )

            chapter_soup = BeautifulSoup(chapter_resp.text, "lxml")
            for chapter_tag in chapter_soup.find_all(class_="toc_w"):
                chapter = ScribbleChapter(self, chapter_tag.a["href"])
                chapter.index = int(chapter_tag["order"])
                chapter.title = chapter_tag.a.text
                chapter.date = arrow.get(
                    chapter_tag.span["title"], "MMM D, YYYY hh:mm A"
                )
                self.chapters.append(chapter)

        self.chapters.sort(key=lambda x: x.index)

        for c in self.chapters:
            print(str(c))
