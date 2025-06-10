import argparse

from .scribblehub import ScribbleBook


def cli():
    parser = argparse.ArgumentParser(
        description="Scribble_to_epub\n\nThis scrapes books from https://www.scribblehub.com/ and creates EPUB from them.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "url",
        type=str,
        help="URL of the ScribbleHub story to scrape and convert to EPUB"
    )

    args = parser.parse_args()

    print(f"Running scribble_to_epub for URL: {args.url}")

    scribble_book = ScribbleBook(args.url)
    scribble_book.load(limit_chapters=1)
    scribble_book.build()


if __name__ == "__main__":
    cli()
