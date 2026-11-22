"""What the event endpoint accepts as an event's name, country and platform (owner, 2026-10-26).

The app key ships inside every copy of an app, so anyone can send events with it, and whatever
they write is later read by the app's owner, in the dashboard, in exports and in every report
made from them. So these three fields carry no free text:

- an event name starts with a letter and uses only letters, digits and `_ . : -`, at most 100
  characters (the SDKs' own limit), so it cannot be a sentence, an address or a command;
- a country is an ISO 3166 code, and anything else is treated as no country (the server then
  works it out from the address, as when none is sent);
- a platform is one of a fixed list, and anything else is "other". The Kotlin SDK sends "kotlin",
  which is Android.
"""

import re

EVENT_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,99}")
EVENT_NAME_RULE = (
    "event_name must start with a letter and use only letters, digits and the characters "
    "_ . : - with at most 100 characters in all."
)

# ISO 3166-1 alpha-2, all 249 codes, and XK (Kosovo), which address databases use.
COUNTRIES = frozenset(
    """
    AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ
    BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM
    DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS
    GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN
    KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ
    MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM
    PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV
    SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI
    VN VU WF WS YE YT ZA ZM ZW XK
    """.split()
)

# The platforms the SDKs send, by their lowercase spelling, as the dashboard shows them.
PLATFORMS = {
    "ios": "iOS",
    "android": "Android",
    "kotlin": "Android",
    "macos": "macOS",
    "watchos": "watchOS",
    "tvos": "tvOS",
    "visionos": "visionOS",
    "web": "Web",
    "linux": "Linux",
    "windows": "Windows",
}
OTHER_PLATFORM = "other"


def valid_event_name(value: str) -> bool:
    return bool(EVENT_NAME.fullmatch(value))


def country_code(value) -> str | None:
    """The ISO code `value` names, upper case, or None for anything that is not one."""
    if not isinstance(value, str):
        return None
    code = value.strip().upper()
    return code if code in COUNTRIES else None


def platform_name(value) -> str | None:
    """The platform as the dashboard names it; "other" for anything unknown, None for nothing."""
    if not isinstance(value, str) or not value.strip():
        return None
    return PLATFORMS.get(value.strip().lower(), OTHER_PLATFORM)
