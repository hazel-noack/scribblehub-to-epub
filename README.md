# Scribble to EPUB

A command-line tool to convert ScribbleHub stories into EPUB format.

## Description

This tool scrapes books from [ScribbleHub](https://www.scribblehub.com/) and converts them into EPUB files for offline reading. It preserves chapter structure and includes author information and other metadata.

## Features

- Converts ScribbleHub stories to EPUB format
- Preserves chapter structure and titles
- Includes author information and notes (by default)
- Customizable output filename

## Installation

```bash
pip install scribble-to-epub
```

## Usage

```bash
scribble-to-epub [OPTIONS] URL
```

### Options

| Option | Description |
|--------|-------------|
| `--output OUTPUT` | Optional output file name for the EPUB |
| `--disable-author-quotes` | Disable author quotes in the EPUB (default: False) |

### Example

```bash
scribble-to-epub https://www.scribblehub.com/series/123456/story-title/
```

## Credits

This project uses significant code from [agmlego/py-scribblehub-to-epub](https://github.com/agmlego/py-scribblehub-to-epub). Many thanks to the original author for their work.

## License

This project is licensed under the **Opinionated Queer License v1.2**. So use is strictly prohibited for cops, military and everyone who doesn't like human rights.

## Notes

The default behavior includes author quotes in the EPUB to show appreciation for the author's work. While there's an option to disable this (`--disable-author-quotes`), it's recommended to keep them enabled to support the authors.

If you encounter any issues with the EPUB formatting of author notes, please consider reporting them as issues rather than immediately disabling the quotes.