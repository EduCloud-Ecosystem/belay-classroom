# SPDX-License-Identifier: AGPL-3.0-only
"""Explicit opt-in schema/cleanup for the synthetic classroom private store.

No scheduled work, backup, grant, model or default is enabled by this command.
"""

import argparse

from .store import configured_store, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["initialize", "cleanup"])
    args = parser.parse_args()
    store = configured_store()
    if args.action == "initialize":
        metadata.create_all(store.engine)
    else:
        store.cleanup()


if __name__ == "__main__":
    main()
