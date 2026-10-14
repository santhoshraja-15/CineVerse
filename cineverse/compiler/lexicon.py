"""Closed word tables of the request language (genres come from the registry).

Spec: CineVerse_Compiler_Frontend_Specification §3.3.
"""

from __future__ import annotations

NEG_HARD = ("no", "not", "without", "exclude", "excluding", "avoid", "never", "none")
NEG_SOFT = ("little", "less", "minimal", "not too", "not much", "not very", "light on",
            "barely any", "low on")
HEDGE = ("preferably", "ideally", "if possible", "maybe", "rather", "would prefer")
STRICT = ("only", "must be", "strictly", "just", "exclusively")
CMP = {
    "under": "<", "below": "<", "less than": "<", "fewer than": "<", "before": "<",
    "at most": "<=", "no more than": "<=", "up to": "<=",
    "over": ">", "above": ">", "more than": ">", "after": ">",
    "at least": ">=", "since": ">=", "from": ">=",
}
BETWEEN = ("between",)
TO = ("to", "through")
FIELD = {
    "released": "year", "release": "year", "year": "year", "made": "year",
    "rated": "rating", "rating": "rating", "rating of": "rating",
    "runtime": "runtime", "long": "runtime", "length": "runtime",
    "language": "language",
}
LIMIT = ("top", "show", "show me", "give me", "list", "recommend", "suggest")
ITEM = ("movie", "movies", "film", "films", "picks", "titles", "options")
DIVERSE = ("diverse", "varied", "variety", "different kinds")
SEP = (",", ";", "and", "with", "but", "that", "which", "also")
OR = ("or",)
FILLER = ("a", "an", "the", "some", "something", "anything", "i", "me", "my", "want", "like",
          "would", "please", "in", "of", "for", "watch", "see", "find")

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20,
}

# Curated moods and themes (~150). Multi-word entries are at most four words (lexer limit).
DESCRIPTORS = (
    # moods and tone
    "dark", "uplifting", "feel-good", "feel good", "thoughtful", "thought-provoking",
    "thought provoking", "tense", "slow", "slow burn", "slow-burn", "quirky", "emotional", "sad",
    "atmospheric", "violent", "gory", "gore", "bloody", "creepy", "eerie", "disturbing",
    "lighthearted", "light-hearted", "heartwarming", "heartbreaking", "hilarious", "witty",
    "satirical", "satire", "absurd", "surreal", "weird", "bizarre", "stylish", "visually stunning",
    "beautiful", "gritty", "bleak", "depressing", "melancholic", "melancholy", "nostalgic",
    "romantic", "sweet", "charming", "cozy", "wholesome", "inspiring", "inspirational",
    "motivational", "suspenseful", "gripping", "intense", "fast-paced", "fast paced",
    "action-packed", "epic", "intelligent", "smart", "clever", "mind-bending", "mind bending",
    "complex", "philosophical", "existential", "psychological", "cerebral", "deep", "moving",
    "touching", "powerful", "haunting", "chilling", "spooky", "silly", "goofy", "campy",
    "cheesy", "cult", "classic", "underrated", "quiet", "calm", "relaxing", "fun", "exciting",
    "thrilling", "mysterious", "magical", "whimsical", "adventurous", "realistic", "raw",
    # themes
    "time travel", "space", "outer space", "aliens", "alien", "robots", "robot", "heist",
    "revenge", "dystopia", "dystopian", "post-apocalyptic", "post apocalyptic", "apocalypse",
    "artificial intelligence", "twist", "twist ending", "plot twist", "true story",
    "coming of age", "coming-of-age", "friendship", "family drama", "love story", "betrayal",
    "survival", "zombies", "zombie", "vampires", "vampire", "superhero", "superheroes",
    "spy", "espionage", "detective", "serial killer", "murder", "conspiracy", "politics",
    "political", "biography", "biopic", "historical", "history", "sports", "music", "dance",
    "high school", "college", "road trip", "prison", "courtroom", "military", "nature",
    "ocean", "animals", "dogs", "cats", "dinosaurs", "magic", "dragons", "witches", "ghosts",
    "haunted house", "monsters", "cyberpunk", "virtual reality", "parallel universe",
    "alternate universe", "dreams", "memory", "mental illness", "addiction", "drugs", "crime boss",
    "mafia", "gangsters", "hacker", "hackers", "cars", "racing", "martial arts", "samurai",
    "pirates", "treasure", "island", "christmas", "holiday", "wedding", "pixar", "disney",
    "anime", "visually appealing", "nonlinear", "dialogue", "ensemble cast",
)
