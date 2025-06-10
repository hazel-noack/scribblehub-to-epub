from functools import cached_property

from .connection import get_session


class ScribbleBook:
    def __init__(self, url: str):
        self.session = get_session()

        self.source_url = url
        _parts = [p for p in self.source_url.split("/") if len(p.strip())]
        self.slug = _parts[-1]
        self.identifier = _parts[-2]

        print(f"scraping {self.slug} ({self.identifier})")

        self.chapters = []
        self.languages = []
        self.genres = []
        self.tags = []

        self.load()

    def load(self) -> None:
        """
        Load the metadata for this object
        """
        html = self.session.get(self.source_url)
        print(html)
