"""Built-in wildcard pool: Spotify genre names spanning eras, regions and scenes.

Wildcard picks skip genres already prominent in your profile and anything you've avoided, and lean toward
families close to what you play (see `wildcard.adjacency`).
Add your own via `wildcard.genres` in config.yaml or the ECLECTOLOG_WILDCARD_GENRES variable.
"""

GENRE_FAMILIES: dict[str, list[str]] = {
    "Africa & diaspora": [
        "afrobeat", "highlife", "afropop", "ethio-jazz", "desert blues", "soukous", "mbalax", "gnawa", "rai",
        "amapiano", "gqom", "kwaito", "bongo flava", "benga", "makossa", "afro-funk", "palm wine",
    ],
    "Latin America & Caribbean": [
        "bossa nova", "tropicalia", "mpb", "samba", "choro", "forro", "baile funk", "cumbia", "chicha",
        "son cubano", "salsa", "boogaloo", "mambo", "bolero", "nueva cancion", "tango", "ranchera", "norteno",
        "calypso", "soca", "kompa", "zouk", "roots reggae", "dub", "lovers rock", "rocksteady", "ska",
        "dancehall",
    ],
    "Asia & Middle East": [
        "city pop", "shibuya-kei", "japanese jazz", "enka", "k-indie", "cantopop", "thai indie", "luk thung",
        "indonesian indie", "gamelan", "qawwali", "hindustani classical", "carnatic", "filmi", "dabke",
        "arabic jazz", "turkish psych", "anatolian rock", "persian traditional", "tuvan throat singing",
    ],
    "Europe": [
        "krautrock", "kosmische", "neue deutsche welle", "italo disco", "chanson", "ye-ye", "fado", "flamenco",
        "rebetiko", "balkan brass", "klezmer", "celtic", "nordic folk", "french jazz", "canterbury scene",
        "zeuhl",
    ],
    "North American roots": [
        "delta blues", "piedmont blues", "chicago blues", "bluegrass", "old-time", "cajun", "zydeco",
        "western swing", "honky tonk", "outlaw country", "gospel", "sacred harp", "doo-wop", "americana",
    ],
    "Soul, funk, jazz": [
        "northern soul", "deep funk", "p-funk", "boogie", "quiet storm", "neo soul", "jazz funk",
        "spiritual jazz", "free jazz", "hard bop", "cool jazz", "vocal jazz", "latin jazz", "jazz fusion",
        "exotica", "lounge", "space age pop", "library music",
    ],
    "Electronic": [
        "ambient", "dark ambient", "drone", "new age", "fourth world", "idm", "glitch", "microhouse",
        "minimal techno", "detroit techno", "acid house", "deep house", "uk garage", "jungle", "drum and bass",
        "footwork", "dubstep", "grime", "trip hop", "synthpop", "minimal wave", "coldwave", "darkwave", "ebm",
        "vaporwave", "hypnagogic pop", "chillwave", "balearic",
    ],
    "Rock & indie": [
        "shoegaze", "dream pop", "slowcore", "post-rock", "math rock", "midwest emo", "post-punk", "no wave",
        "garage rock", "psychedelic rock", "stoner rock", "doom metal", "progressive rock", "art rock",
        "glam rock", "power pop", "jangle pop", "c86", "twee pop", "britpop", "madchester", "noise rock",
        "industrial", "freak folk", "psychedelic folk", "british folk", "singer-songwriter", "bedroom pop",
    ],
    "Hip hop": [
        "jazz rap", "abstract hip hop", "boom bap", "g-funk", "memphis rap", "turntablism", "plunderphonics",
    ],
    "Classical & experimental": [
        "minimalism", "contemporary classical", "baroque", "early music", "gregorian chant", "musique concrete",
        "classical guitar", "fingerstyle", "a cappella", "barbershop", "soundtrack",
    ],
}

# Substrings that tie one of your (free-form) Spotify genres to a family, e.g. "chilean shoegaze" -> Rock & indie.
FAMILY_HINTS: dict[str, list[str]] = {
    "Africa & diaspora": ["afro", "african", "nigerian", "ghana", "congo", "senegal", "mali", "ethio", "amapiano"],
    "Latin America & Caribbean": ["latin", "brazil", "mpb", "bossa", "samba", "cumbia", "salsa", "mexic", "reggae", "dub", "ska", "dancehall", "tropical", "colombia", "cuba", "puerto ric"],
    "Asia & Middle East": ["japan", "j-pop", "j-rock", "k-pop", "k-indie", "k-rap", "korean", "chinese", "mandopop", "canto", "indian", "bollywood", "desi", "arab", "turkish", "persian", "iran", "thai", "indonesia", "filipino", "vietnam"],
    "Europe": ["german", "french", "italian", "spanish", "greek", "balkan", "nordic", "swedish", "celtic", "irish", "kraut", "chanson", "flamenco", "fado"],
    "North American roots": ["country", "blues", "bluegrass", "americana", "gospel", "honky", "appalachian", "cajun", "roots"],
    "Soul, funk, jazz": ["soul", "funk", "jazz", "r&b", "disco", "lounge", "motown", "swing", "bebop"],
    "Electronic": ["electro", "house", "techno", "ambient", "edm", "garage", "bass", "wave", "trance", "dubstep", "drum and bass", "idm", "synth", "downtempo", "breakbeat"],
    "Rock & indie": ["rock", "indie", "punk", "emo", "metal", "gaze", "grunge", "alternative", "folk", "lo-fi", "slowcore", "post-"],
    "Hip hop": ["hip hop", "rap", "trap", "drill", "boom bap", "grime"],
    "Classical & experimental": ["classical", "orchestra", "choral", "chamber", "opera", "soundtrack", "score", "piano", "experimental", "avant"],
}

BUILTIN_GENRES = [g for genres in GENRE_FAMILIES.values() for g in genres]
