import codecs
from pathlib import Path

import requests

script_path = Path(__file__).resolve()

SOURCE_URL = "https://raw.githubusercontent.com/github/gemoji/master/db/emoji.json"
OUTPUT_PATH = script_path.parent.parent.parent / "octoprint_telegram" / "emojiDict.py"

# Download emoji data
response = requests.get(SOURCE_URL)
response.raise_for_status()
emoji_data = response.json()

# Create emoji_dict
emoji_dict = {}
total_entries = 0
unique_entries = 0

for entry in emoji_data:
    total_entries += 1

    description = entry.get("description")
    emoji = entry.get("emoji")

    if description and emoji:
        if description not in emoji_dict:
            emoji_dict[description] = emoji
            unique_entries += 1
        else:
            print(f"Duplicate description: {description}")
    else:
        print(f"Missing description or emoji in entry: {entry}")

print(
    f"Processed {unique_entries} of {total_entries} emoji entries from {SOURCE_URL}.\n"
    f"Writing dictionary to {OUTPUT_PATH}..."
)

# Save emoji_dict to file
with codecs.open(OUTPUT_PATH, encoding="utf-8", mode="w") as file:
    file.write(
        "# pylint: disable=line-too-long\n"
        "# Generated with data from:\n"
        f"# {SOURCE_URL}\n"
        "# \n"
        "# Overview available here (the table descriptions on this page serve as keys in this dictionary):\n"
        "# https://www.unicode.org/emoji/charts/full-emoji-list.html\n\n"
        "telegramEmojiDict = {\n"
    )

    for description, emoji in emoji_dict.items():
        escaped_emoji = emoji.encode("unicode_escape").decode("ascii")
        file.write(f"    '{description}': u'{escaped_emoji}',\n")

    file.write("}")

print("DONE")
