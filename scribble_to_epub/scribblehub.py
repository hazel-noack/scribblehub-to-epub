from functools import cached_property
from bs4 import BeautifulSoup
from ebooklib import epub
import logging
import cloudscraper
import arrow
import ftfy
from typing import Iterable
import re

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



class ScribbleBook:
    def __init__(self, url: str):
        self.metadata = BookMetadata()
        
        self.source_url = url

        print(f"scraping {url})")

        self.chapters = []
        self.languages = []
        self.genres = []
        self.tags = []

        self.session = cloudscraper.create_scraper()
        self.load_metadata()
        print(str(self.metadata))

    def load_metadata(self) -> None:
        """
        Load the metadata for this object
        will make web requests
        """

        # parse info from the source url
        _parts = [p for p in self.source_url.split("/") if len(p.strip())]
        self.metadata.slug = _parts[-1]
        self.metadata.identifier = _parts[-2]

        html = self.session.get(self.source_url)
        print(html)

        html = self.session.get(self.source_url)
        soup = BeautifulSoup(html.text, "lxml")

        for tag in soup.find_all(lambda x: x.has_attr("lang")):
            log.debug(f'Found language {tag["lang"]}')
            self.languages.append(tag["lang"])

        url = soup.find(property="og:url")["content"]
        if self.source_url != url:
            log.warning(f"Metadata URL mismatch!\n\t{self.source_url}\n\t{url}")

        self.metadata.title = soup.find(property="og:title")["content"]
        print(f"Book Title: {self.metadata.title}")

        self.metadata.cover_url = soup.find(property="og:image")["content"] or ""
        self.metadata.date = arrow.get(
            soup.find("span", title=DATE_MATCH)["title"][14:], "MMM D, YYYY hh:mm A"
        )
        description = soup.find(class_="wi_fic_desc")
        self.metadata.intro = ftfy.fix_text(description.prettify())
        self.metadata.description = ftfy.fix_text(description.text)
        self.metadata.author = soup.find(attrs={"name": "twitter:creator"})["content"]
        self.metadata.publisher = soup.find(property="og:site_name")["content"]
        
        self.metadata.genres = [a.string for a in soup.find_all(class_="fic_genre")]
        self.metadata.tags = [a.string for a in soup.find_all(class_="stag")]

        imgs = soup.find(class_="sb_content copyright").find_all("img")
        for img in imgs:
            if "copy" not in img["class"]:
                continue
            self.metadata.rights = ftfy.fix_text(img.next.string)
