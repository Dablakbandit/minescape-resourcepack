"""Every Java block and its properties as the Minecraft version Geyser translates to knows them, for
build_bedrock.py: Geyser's custom block mappings name whole Java block states, and refuse the whole file over one it
doesn't know (a fence gate's state without `powered`), while a blockstate file's keys leave properties out. Made
once from the game's own block report (CI doesn't run the game):

    java -cp <the client jar and its libraries> net.minecraft.data.Main --reports --output <dir>
    python gen_java_blocks.py <dir>/reports/blocks.json <version> <out json>"""
import json
import sys

source, version, out = sys.argv[1:4]
report = json.load(open(source, encoding="utf-8"))
blocks = {name.split(":", 1)[1]: data.get("properties", {}) for name, data in sorted(report.items())}
json.dump({"_about": __doc__.split("\n\n")[0].replace("\n", " "), "version": version, "blocks": blocks},
          open(out, "w", encoding="utf-8"), separators=(",", ":"), sort_keys=True)
print(len(blocks), "blocks for", version, "->", out)
