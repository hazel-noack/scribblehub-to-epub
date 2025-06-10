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
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional output file name for the EPUB"
    )
    parser.add_argument(
        "--disable-author-quotes",
        action="store_true",
        help="Disable author quotes in the EPUB (default: False). I didn't want to implement this because I wanna appreciate the author and what they have to say. Sadly I did not find a way to embed quotes nicely in the epub. So only use it if you have to."
    )

    args = parser.parse_args()

    print(f"Running scribble_to_epub for URL: {args.url}")

    scribble_book = ScribbleBook(args.url, disable_author_quotes=args.disable_author_quotes, file_name=args.output)
    scribble_book.load()
    scribble_book.build()


if __name__ == "__main__":
    cli()
