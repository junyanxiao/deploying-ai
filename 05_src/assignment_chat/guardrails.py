from dataclasses import dataclass
import re


RESTRICTED_RESPONSE = (
    "I'm not able to discuss that topic, but I can help with Toronto weather, "
    "local activities, or weekend planning."
)

PROMPT_ATTACK_RESPONSE = (
    "I can't reveal or modify internal instructions. I can still help with "
    "Toronto weather, local places, or weekend planning."
)


@dataclass
class GuardrailResult:
    blocked: bool
    response: str | None = None
    reason: str | None = None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


# These patterns target direct restricted terms and a few obvious aliases while
# avoiding broad single-word matches such as "prompt" or "swift" alone.
RESTRICTED_TOPIC_PATTERNS = [
    re.compile(r"\b(cats?|kittens?|kitty|kitties|felines?)\b"),
    re.compile(r"\b(dogs?|pupp(?:y|ies)|dogg(?:y|ies)|canines?)\b"),
    re.compile(r"\bhoroscopes?\b"),
    re.compile(r"\bzodiac(?:\s+sign)?s?\b"),
    re.compile(r"\bstar\s+signs?\b"),
    re.compile(r"\bastrology\b.{0,40}\b(horoscope|zodiac|sign|birth\s+chart)\b"),
    re.compile(r"\b(horoscope|zodiac|sign|birth\s+chart)\b.{0,40}\bastrology\b"),
    re.compile(r"\btaylor\s+swift\b"),
    re.compile(r"\bshake\s+it\s+off\b"),
    re.compile(r"\beras\s+tour\b"),
]


# Prompt-attack patterns require meaningful phrase combinations. This lets normal
# messages like "write a good user prompt" pass through.
PROMPT_ATTACK_PATTERNS = [
    re.compile(
        r"\b(show|reveal|print|display|quote|dump|give|tell|summarize)\b.{0,50}"
        r"\b(system\s+prompt|hidden\s+instructions|developer\s+instructions|"
        r"internal\s+instructions|internal\s+rules)\b"
    ),
    re.compile(
        r"\b(system\s+prompt|hidden\s+instructions|developer\s+instructions|"
        r"internal\s+instructions|internal\s+rules)\b.{0,50}"
        r"\b(show|reveal|print|display|quote|dump|give|tell|summarize)\b"
    ),
    re.compile(
        r"\b(ignore|disregard|override)\b.{0,40}"
        r"\b(previous|prior|above|system|developer)\b.{0,40}"
        r"\b(instructions?|rules?|prompt)\b"
    ),
    re.compile(
        r"\b(replace|modify|edit|change|rewrite)\b.{0,40}"
        r"\b(your|the)\b.{0,20}"
        r"\b(system\s+message|system\s+prompt|instructions?|rules?)\b"
    ),
    re.compile(r"\brepeat\s+everything\s+before\s+this\s+message\b"),
    re.compile(r"\bsummarize\s+the\s+instructions\s+above\b"),
    re.compile(r"\b(unrestricted|developer|admin)\s+mode\b"),
    re.compile(r"\b(print|show|reveal|display|dump)\b.{0,40}\binternal\s+tool\s+definitions?\b"),
    re.compile(r"\b(expose|reveal|print|show|dump)\b.{0,40}\b(environment\s+variables?|api\s+keys?|secrets?)\b"),
]


def check_user_message(message: str) -> GuardrailResult:
    normalized = _normalize(message)

    for pattern in PROMPT_ATTACK_PATTERNS:
        if pattern.search(normalized):
            return GuardrailResult(
                blocked=True,
                response=PROMPT_ATTACK_RESPONSE,
                reason="prompt_attack",
            )

    for pattern in RESTRICTED_TOPIC_PATTERNS:
        if pattern.search(normalized):
            return GuardrailResult(
                blocked=True,
                response=RESTRICTED_RESPONSE,
                reason="restricted_topic",
            )

    return GuardrailResult(blocked=False)

