"""
Bekannte Marken für den Brand-Resolver.
Mehrwörtige Marken sind explizit aufgelistet — sie haben Vorrang vor
kürzeren Präfixen ("Jules Mumm" schlägt "Jules").

Sortierung: wird vom Resolver nach Länge absteigend geordnet.
"""
from __future__ import annotations

# Vollständige Liste bekannter Marken (case-insensitive Prefix-Matching)
KNOWN_BRANDS: list[str] = [
    # ── Multi-Wort-Marken (kritisch: müssen EXPLIZIT hier stehen) ──
    "Jules Mumm",
    "Don Simon",
    "Thomas Henry",
    "Three Sixty Vodka",
    "Three Sixty",
    "The Real Cola",
    "HB München",
    "Chivas Regal",
    "König Pilsener",
    "Fürst von Metternich",
    "Wodka Gorbatschow",
    "Captain Morgan",
    "Jack Daniel's",
    "Jim Beam",
    "Havana Club",
    "Johnnie Walker",
    "Red Bull",
    "Club-Mate",
    "Fritz-Kola",
    "Moritz Fiege",
    "San Pellegrino",
    "Acqua Panna",
    "Nestlé Pure Life",
    "Maker's Mark",
    "Southern Comfort",
    "Monkey Shoulder",
    "Bombay Sapphire",
    "Hendrick's",
    "Hacker-Pschorr",
    "9 Mile",

    # ── Einzel-Wort-Marken ──
    # Bier
    "Bitburger", "Krombacher", "Veltins", "Warsteiner",
    "Beck's", "Paulaner", "Augustiner", "Erdinger", "Franziskaner",
    "Weihenstephan", "Spaten", "Löwenbräu", "Radeberger",
    "DAB", "Flensburger", "Gösser", "Herforder", "Einbecker",
    "Diebels", "Reissdorf", "Pfungstädter", "Schöfferhofer",
    "Clausthaler", "Jever", "Holsten", "Astra", "Licher",
    "Brinkhoff's", "König",
    "Benediktiner", "Arcobräu", "Oberbräu", "Oberdorfer",
    "Staropramen", "Peroni", "Desperados", "Faxe",
    "Karlsberg", "Kulmbacher", "Lech", "Hövels",
    "Reissdorf", "Rut",
    "Leffe", "Corona", "Heineken", "Amstel",

    # Softdrinks / Energy
    "Coca-Cola", "Pepsi", "Fanta", "Sprite", "Mezzo Mix",
    "Mountain Dew", "Monster", "Rockstar", "Bionade",
    "Almdudler", "Rivella", "Lift", "Sinalco",
    "Elephant", "Proviant", "Leonie", "Teinacher", "More",
    "Afri-Cola",

    # Wasser
    "Volvic", "Evian", "Gerolsteiner", "Apollinaris", "Vittel",
    "Lauretana", "Adelholzener", "Altmühltaler", "Perrier",
    "Brohler", "Rosbacher", "Ahrtal", "Eifel", "Steinsieker",
    "Schloss",

    # Spirituosen
    "Bacardi", "Absolut", "Smirnoff", "Jägermeister",
    "Baileys", "Malibu", "Disaronno", "Martini", "Campari",
    "Aperol", "Glenfiddich", "Ballantine's", "Jameson",
    "Beefeater", "Gordons", "Tanqueray", "Lillet",
    "Sambuca", "Grappa", "Kuemmerling", "Berentzen",
    "Salmari", "Nonino", "Boente",

    # Wein / Sekt
    "Freixenet", "Mionetto", "Rotkäppchen", "Geldermann",
    "Henkell", "Kupferberg",

    # Sonstiges Trinkgut-spezifisch
    "Schneider", "Haribo", "Lay's", "Boente's",
]

# Namens-Overrides: welche kanonische Marke für einen Treffer verwendet wird.
# Schlüssel: exakter KNOWN_BRANDS-Eintrag (case-sensitive!)
# Wert: der gespeicherte Markenname (wird noch UPPERCASE-normalisiert)
BRAND_NAME_OVERRIDES: dict[str, str] = {
    "Wodka Gorbatschow":   "Gorbatschow",
    "Three Sixty Vodka":   "Three Sixty",
    "Three Sixty":         "Three Sixty",
    "The Real Cola":       "The Real Cola",
    "Don Simon":           "Don Simon",
    "Jules Mumm":          "Jules Mumm",
    "HB München":          "HB München",
    "Chivas Regal":        "Chivas Regal",
    "Thomas Henry":        "Thomas Henry",
    "Captain Morgan":      "Captain Morgan",
    "Jack Daniel's":       "Jack Daniel's",
    "Jim Beam":            "Jim Beam",
    "Havana Club":         "Havana Club",
    "Johnnie Walker":      "Johnnie Walker",
    "Red Bull":            "Red Bull",
    "Club-Mate":           "Club-Mate",
    "Fritz-Kola":          "Fritz-Kola",
    "König Pilsener":      "König Pilsener",
    "9 Mile":              "9 Mile",
    "Hacker-Pschorr":      "Hacker-Pschorr",
    "Hendrick's":          "Hendrick's",
    "Brinkhoff's":         "Brinkhoff's",
    "Boente's":            "Boente's",
    "Maker's Mark":        "Maker's Mark",
    "Bombay Sapphire":     "Bombay Sapphire",
    "Ballantine's":        "Ballantine's",
}
