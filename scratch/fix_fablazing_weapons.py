import sqlite3
import random
import json

conn = sqlite3.connect("C:\\Users\\Joseph\\Desktop\\FAB_Sim\\data\\fablazing_meta.db")
cursor = conn.cursor()

with open("C:\\Users\\Joseph\\Desktop\\FAB_Sim\\card_data\\slug_index.json", 'r', encoding="utf-8") as f:
    card_db = json.load(f)

weapon_slugs = {}
metadb = conn.execute("SELECT card_slug, card_type FROM card_stats WHERE card_type = 'equipment'").fetchall()
for row in metadb:
    if row[0].endswith("_r") or row[0].endswith("_l"):
        slug = row[0][:-2]
    elif row[0].endswith('hook'):
        continue
    elif row[0].endswith('faced'):
        continue
    else:
        slug = row[0]
    if "Weapon" in card_db["by_slug"][slug]["types"]:
        if '2H' in card_db["by_slug"][slug]["types"]:
            weapon_slugs[row[0]] = "weapon_2h"
        if '1H' in card_db["by_slug"][slug]["types"]:
            weapon_slugs[row[0]] = "weapon_1h"

for slug, wtype in weapon_slugs.items():
    cursor.execute("UPDATE card_stats SET card_type = ? WHERE card_slug = ?", (wtype, slug))
conn.commit()
conn.close()