"""Flag near duplicates inside FRAME Validation using its cached thumbnails."""

from collections import Counter
from functools import lru_cache
import json
from pathlib import Path
import sys

from PIL import Image
from ai_api.rank_similarity import features, metrics
from frame_model.audit_similarity import HashIndex


def main(folder):
    rows = [json.loads(line) for line in (folder / "validation_fingerprints.jsonl").read_text().splitlines()]
    rows = [row for row in rows if "dual128" in row]
    dual = [row["dual128"] for row in rows]
    index = HashIndex(dual, 128, 8)

    @lru_cache(maxsize=4096)
    def thumb(number):
        row = rows[number]
        with Image.open(folder / "thumbs" / f'{row["offset"]}.png') as image:
            rgb, edge, _ = features(image)
        return rgb, edge, row["width"] / row["height"]

    pairs = []
    for i, row in enumerate(rows):
        for j in index.query(dual[i]):
            if j <= i or row["pixelSHA256"] == rows[j]["pixelSHA256"]:
                continue
            hd = (row["dhash64"] ^ rows[j]["dhash64"]).bit_count()
            dd = (dual[i] ^ dual[j]).bit_count()
            if hd > 4 or dd > 8:
                continue
            measures = metrics(thumb(i), thumb(j))
            if (measures["rgbMAE64"] <= 12 and measures["relativeEdgeDifference"] <= 0.35
                    and measures["aspectDifference"] <= 0.015):
                other = rows[j]
                pairs.append(dict(first=row["imageMember"], second=other["imageMember"],
                                  firstOffset=row["offset"], secondOffset=other["offset"],
                                  firstType=row.get("defectType"), secondType=other.get("defectType"),
                                  firstQuality=row.get("quality"), secondQuality=other.get("quality"),
                                  dHashDistance=hd, dualHashDistance=dd, **measures))
    pairs.sort(key=lambda pair: pair["rankScore"])
    affected = {pair[key] for pair in pairs for key in ("firstOffset", "secondOffset")}
    summary = dict(pairs=len(pairs), affectedPhotos=len(affected),
        differentQuality=sum(pair["firstQuality"] != pair["secondQuality"] for pair in pairs),
        photosByType=dict(Counter(row.get("defectType", "unknown") for row in rows if row["offset"] in affected)),
        scope="Near-duplicate candidates inside Validation; exact RGB duplicates counted separately.")
    (folder / "internal_near_pairs.json").write_text(json.dumps(pairs, ensure_ascii=False, indent=2) + "\n")
    (folder / "internal_near_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
