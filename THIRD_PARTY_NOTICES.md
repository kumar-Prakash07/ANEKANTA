# Third-party notices

## darkdump — MIT

`anekanta/collect/discovery.py` adapts the dark-web search-engine endpoints and
the Ahmia-blacklist filtering approach from **darkdump** by Josh Schiavone.

- Source: https://github.com/josh0xA/darkdump
- Licence: MIT — Copyright (c) Josh Schiavone

What was taken: the set of search engines and their query endpoints, and the
decision to check every result against Ahmia's blacklist.

What was changed, and why, is documented in the module docstring: all traffic
is routed through Tor including the clearnet endpoints, the blacklist fails
closed rather than degrading silently, and a second local content gate runs
over titles, snippets and fetched pages.

## Ahmia blacklist

The abuse blacklist is fetched at runtime from `https://ahmia.fi/blacklist/banned/`
and is not redistributed with this project. Ahmia is operated by Juha Nurmi.

## Python dependencies

See `requirements.txt`. Each is used under its own licence; none is vendored
into this repository.
