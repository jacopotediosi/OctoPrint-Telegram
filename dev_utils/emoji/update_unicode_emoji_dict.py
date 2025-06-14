import codecs
from pathlib import Path

import requests

script_path = Path(__file__).resolve()

# Get latest release tag
response = requests.get(
    "https://api.github.com/repos/muan/unicode-emoji-json/releases/latest"
)
response.raise_for_status()
latest_release = response.json()
tag_name = latest_release["tag_name"]
print(f"Latest release tag: {tag_name}")

# Calculate SOURCE_URL and OUTPUT_PATH
SOURCE_URL = f"https://raw.githubusercontent.com/muan/unicode-emoji-json/{tag_name}/data-by-emoji.json"
OUTPUT_PATH = (
    script_path.parent.parent.parent
    / "octoprint_telegram"
    / "emoji"
    / "unicode_emoji_dict.py"
)

# Download emoji data
print(f"Downloading emoji data from: {SOURCE_URL}")
response = requests.get(SOURCE_URL)
response.raise_for_status()
emoji_data = response.json()

# Create emoji_dict
emoji_dict = {}
total_entries = 0
unique_entries = 0

for emoji_char, data in emoji_data.items():
    total_entries += 1

    # muan/unicode-emoji-json currently strips colons from the 'name' field.
    # We replicate that behavior explicitly to ensure backward compatibility
    # in case this changes in the future.
    # Additionally, we treat names as case-insensitive for more robust matching.
    name = data.get("name").replace(":", "").lower()

    if name and emoji_char:
        if name not in emoji_dict:
            emoji_dict[name] = emoji_char
            unique_entries += 1
        else:
            print(f"Duplicate name: {name}")
    else:
        print(f"Missing name or emoji in entry: {emoji_char} -> {data}")

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
        "# Overview available here ('CLDR Short Name' column values on this page serve as keys in this dictionary):\n"
        "# https://www.unicode.org/emoji/charts/full-emoji-list.html\n\n"
        "unicode_emoji_dict = {\n"
    )

    for name, emoji in emoji_dict.items():
        escaped_emoji = emoji.encode("unicode_escape").decode("ascii")
        file.write(f"    '{name}': u'{escaped_emoji}',\n")

    file.write("}")

print("DONE")
