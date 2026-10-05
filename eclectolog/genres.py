"""Built-in wildcard pool: Spotify genre names spanning eras, regions and scenes.

Wildcard picks skip genres already prominent in your profile and anything you've avoided.
Add your own via `wildcard.genres` in config.yaml or the ECLECTOLOG_WILDCARD_GENRES variable.
"""

BUILTIN_GENRES = [
    # Africa & diaspora
    "afrobeat", "highlife", "afropop", "ethio-jazz", "desert blues", "soukous", "mbalax", "gnawa", "rai",
    "amapiano", "gqom", "kwaito", "bongo flava", "benga", "makossa", "afro-funk", "palm wine",
    # Latin America & Caribbean
    "bossa nova", "tropicalia", "mpb", "samba", "choro", "forro", "baile funk", "cumbia", "chicha",
    "son cubano", "salsa", "boogaloo", "mambo", "bolero", "nueva cancion", "tango", "ranchera", "norteno",
    "calypso", "soca", "kompa", "zouk", "roots reggae", "dub", "lovers rock", "rocksteady", "ska", "dancehall",
    # Asia & Middle East
    "city pop", "shibuya-kei", "japanese jazz", "enka", "k-indie", "cantopop", "thai indie", "luk thung",
    "indonesian indie", "gamelan", "qawwali", "hindustani classical", "carnatic", "filmi", "dabke",
    "arabic jazz", "turkish psych", "anatolian rock", "persian traditional", "tuvan throat singing",
    # Europe
    "krautrock", "kosmische", "neue deutsche welle", "italo disco", "chanson", "ye-ye", "fado", "flamenco",
    "rebetiko", "balkan brass", "klezmer", "celtic", "nordic folk", "french jazz", "canterbury scene", "zeuhl",
    # North American roots
    "delta blues", "piedmont blues", "chicago blues", "bluegrass", "old-time", "cajun", "zydeco",
    "western swing", "honky tonk", "outlaw country", "gospel", "sacred harp", "doo-wop", "americana",
    # Soul, funk, jazz
    "northern soul", "deep funk", "p-funk", "boogie", "quiet storm", "neo soul", "jazz funk",
    "spiritual jazz", "free jazz", "hard bop", "cool jazz", "vocal jazz", "latin jazz", "jazz fusion",
    "exotica", "lounge", "space age pop", "library music",
    # Electronic
    "ambient", "dark ambient", "drone", "new age", "fourth world", "idm", "glitch", "microhouse",
    "minimal techno", "detroit techno", "acid house", "deep house", "uk garage", "jungle", "drum and bass",
    "footwork", "dubstep", "grime", "trip hop", "synthpop", "minimal wave", "coldwave", "darkwave", "ebm",
    "vaporwave", "hypnagogic pop", "chillwave", "balearic",
    # Rock & indie
    "shoegaze", "dream pop", "slowcore", "post-rock", "math rock", "midwest emo", "post-punk", "no wave",
    "garage rock", "psychedelic rock", "stoner rock", "doom metal", "progressive rock", "art rock",
    "glam rock", "power pop", "jangle pop", "c86", "twee pop", "britpop", "madchester", "noise rock",
    "industrial", "freak folk", "psychedelic folk", "british folk", "singer-songwriter", "bedroom pop",
    # Hip hop
    "jazz rap", "abstract hip hop", "boom bap", "g-funk", "memphis rap", "turntablism", "plunderphonics",
    # Classical & experimental
    "minimalism", "contemporary classical", "baroque", "early music", "gregorian chant", "musique concrete",
    "classical guitar", "fingerstyle", "a cappella", "barbershop", "soundtrack",
]
