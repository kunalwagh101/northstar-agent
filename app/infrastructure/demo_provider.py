from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.models import (
    AgentAction,
    AgentActionType,
    AgentTurn,
    Configuration,
    ConversationSession,
    EndReason,
    Language,
    LeadUpdates,
    PurchasePurpose,
)
from app.domain.safety import is_do_not_contact, is_prompt_injection
from app.infrastructure.llm import AgentProvider, ProviderResult

_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_HINGLISH_WORDS = re.compile(
    r"\b(?:aap|apko|mujhe|mera|meri|chahiye|nahi|nahin|haan|ha|kya|kitna|kitni|"
    r"mein|mai|ke liye|batao|bataiye|karna|karo|kal|aaj|parso|baje|mehenga|"
    r"sasta|dekhna|ghar|lena|investment|theek|thik)\b",
    re.IGNORECASE,
)

_BUSY = re.compile(
    r"\b(?:busy|in a meeting|call me later|callback|call back|baad mein|baad me|abhi time nahi|"
    r"अभी\s+व्यस्त|बाद\s+में\s+कॉल)\b",
    re.IGNORECASE,
)
_CALL_REQUEST = re.compile(
    r"\b(?:call me|callback|call back|phone me|mujhe call|कॉल कर|फोन कर)\b",
    re.IGNORECASE,
)
_NOT_INTERESTED = re.compile(
    r"\b(?:not interested|no interest|don['’]?t want|not looking|nahi chahiye|interest nahi|"
    r"रुचि नहीं|नहीं चाहिए)\b",
    re.IGNORECASE,
)
_HUMAN = re.compile(
    r"\b(?:human|real person|salesperson|sales person|sales advisor|agent|manager|representative|"
    r"kisi se baat|insaan|व्यक्ति|सेल्स.*बात)\b",
    re.IGNORECASE,
)
_VISIT = re.compile(
    r"\b(?:site visit|visit the site|visit book|book.*visit|property dekh|site dekh|"
    r"visit kar|साइट.*विजिट|देखने आ)\b",
    re.IGNORECASE,
)
_EXPENSIVE = re.compile(
    r"\b(?:expensive|costly|too much|out of (?:my )?budget|mehenga|mahinga|budget se bahar|महंगा)\b",
    re.IGNORECASE,
)
_GOODBYE = re.compile(
    r"^(?:bye|goodbye|thanks|thank you|that['’]?s all|bas|धन्यवाद|ठीक है धन्यवाद)[.! ]*$",
    re.IGNORECASE,
)
_GREETING = re.compile(r"^(?:hi|hello|hey|namaste|नमस्ते|नमस्कार)[!,. ]*$", re.IGNORECASE)

_UNKNOWN_TOPICS: dict[str, re.Pattern[str]] = {
    "amenities": re.compile(r"\b(?:amenit|pool|gym|clubhouse|park|security)\w*\b", re.IGNORECASE),
    "possession": re.compile(
        r"\b(?:possession|completion|ready to move|construction)\b", re.IGNORECASE
    ),
    "area": re.compile(
        r"\b(?:carpet area|super area|square feet|sq\.?\s*ft|size)\b", re.IGNORECASE
    ),
    "availability": re.compile(
        r"\b(?:available|availability|inventory|units left)\b", re.IGNORECASE
    ),
    "discount": re.compile(
        r"\b(?:discount|offer|negotia|best price|final price|deal)\w*\b", re.IGNORECASE
    ),
    "legal": re.compile(r"\b(?:rera|approval|legal|title|registration)\b", re.IGNORECASE),
    "finance": re.compile(r"\b(?:loan|emi|payment plan|finance|mortgage)\b", re.IGNORECASE),
    "builder": re.compile(r"\b(?:builder|developer history|delivered projects)\b", re.IGNORECASE),
}


def detect_language(message: str, previous: Language = Language.ENGLISH) -> Language:
    if _DEVANAGARI.search(message):
        return Language.HINDI
    if _HINGLISH_WORDS.search(message):
        return Language.HINGLISH
    if re.search(r"[A-Za-z]", message):
        return Language.ENGLISH
    return previous


def _say(language: Language, *, en: str, hi: str, hinglish: str) -> str:
    if language == Language.HINDI:
        return hi
    if language == Language.HINGLISH:
        return hinglish
    return en


def _normalise(message: str) -> str:
    return unicodedata.normalize("NFKC", message).strip()


def _extract_configuration(message: str) -> Configuration | None:
    if re.search(r"\b2\s*[- ]?\s*bhk\b|दो\s*बीएचके", message, re.IGNORECASE):
        return Configuration.TWO_BHK
    if re.search(r"\b3\s*[- ]?\s*bhk\b|तीन\s*बीएचके", message, re.IGNORECASE):
        return Configuration.THREE_BHK
    return None


def _extract_budget(message: str) -> tuple[str | None, float | None]:
    crore = re.search(r"(?:₹\s*)?(\d+(?:\.\d+)?)\s*(?:crore|cr\b)", message, re.IGNORECASE)
    if crore:
        value = float(crore.group(1))
        return f"₹{value:g} crore", value

    lakh = re.search(r"(?:₹\s*)?(\d+(?:\.\d+)?)\s*(?:lakh|lac\b)", message, re.IGNORECASE)
    if lakh:
        value_lakh = float(lakh.group(1))
        return f"₹{value_lakh:g} lakh", value_lakh / 100
    return None, None


def _extract_purpose(message: str) -> PurchasePurpose | None:
    if re.search(r"\b(?:self[ -]?use|own use|live|family|rehne|रहने|खुद)\b", message, re.IGNORECASE):
        return PurchasePurpose.SELF_USE
    if re.search(r"\b(?:invest|rental|return|निवेश)\w*\b", message, re.IGNORECASE):
        return PurchasePurpose.INVESTMENT
    return None


def _extract_timeline(message: str) -> str | None:
    patterns = (
        r"\b(?:within|in|next)\s+(\d+\s+(?:day|week|month|year)s?)\b",
        r"\b(\d+\s+(?:day|week|month|year)s?)\b",
        r"\b(immediately|this month|next month|this year|next year|jaldi|तुरंत)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return match.group(1).lower()
    return None


def _extract_name(message: str) -> str | None:
    match = re.search(
        r"\b(?:my name is|i am|i['’]?m|mera naam|मेरा नाम)\s+([A-Za-z\u0900-\u097F][A-Za-z\u0900-\u097F .'-]{1,48})",
        message,
        re.IGNORECASE,
    )
    if not match:
        return None
    candidate = re.split(r"[,.;]|\s+(?:and|aur)\s+", match.group(1), maxsplit=1)[0].strip()
    return candidate.title()[:100] or None


def _extract_phone(message: str) -> str | None:
    match = re.search(r"(?<!\d)(?:\+91[- ]?)?([6-9]\d{9})(?!\d)", message)
    return match.group(1) if match else None


def _extract_date(message: str, today: date) -> date | None:
    lower = message.lower()
    if "day after tomorrow" in lower or re.search(r"\bparso\b|परसों", lower):
        return today + timedelta(days=2)
    if re.search(r"\btomorrow\b|\bkal\b|कल", lower):
        return today + timedelta(days=1)
    if re.search(r"\btoday\b|\baaj\b|आज", lower):
        return today

    iso_match = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", message)
    if iso_match:
        try:
            return date(*(int(part) for part in iso_match.groups()))
        except ValueError:
            return None

    short_match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](20\d{2}|\d{2}))?\b", message)
    if short_match:
        day, month, year_raw = short_match.groups()
        year = int(year_raw) if year_raw else today.year
        if year < 100:
            year += 2000
        try:
            candidate = date(year, int(month), int(day))
            if year_raw is None and candidate < today:
                candidate = candidate.replace(year=year + 1)
            return candidate
        except ValueError:
            return None

    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    for weekday, target in weekdays.items():
        if re.search(rf"\b{weekday}\b", lower):
            days_ahead = (target - today.weekday()) % 7
            return today + timedelta(days=days_ahead or 7)
    return None


def _extract_time(message: str) -> time | None:
    match = re.search(
        r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?|baje|बजे)\b",
        message,
        re.IGNORECASE,
    )
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    marker = match.group(3).lower().replace(".", "")
    if hour > 23 or minute > 59:
        return None
    if marker == "pm" and hour < 12:
        hour += 12
    elif marker == "am" and hour == 12:
        hour = 0
    elif marker in {"baje", "बजे"} and 1 <= hour <= 6:
        hour += 12
    try:
        return time(hour=hour, minute=minute)
    except ValueError:
        return None


class DemoAgentProvider(AgentProvider):
    """Deterministic offline engine for demos, tests, and provider-failure fallback.

    It is intentionally a baseline, not a replacement for the final LLM prompt.
    """

    name = "demo"

    def __init__(
        self,
        *,
        timezone_name: str = "Asia/Kolkata",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._timezone = ZoneInfo(timezone_name)
        self._clock = clock or (lambda: datetime.now(self._timezone))

    async def generate_turn(
        self,
        *,
        system_prompt: str,
        session: ConversationSession,
        user_message: str,
    ) -> ProviderResult:
        del system_prompt
        message = _normalise(user_message)
        language = detect_language(message, session.profile.language)
        turn = self._respond(session=session, message=message, language=language)
        return ProviderResult(turn=turn, provider="demo:deterministic-v1")

    def _updates(self, message: str, language: Language) -> LeadUpdates:
        budget_raw, budget_crore = _extract_budget(message)
        preferred_location = None
        if re.search(r"sector\s*79|gurugram|gurgaon|गुरुग्राम", message, re.IGNORECASE):
            preferred_location = "Sector 79, Gurugram"
        return LeadUpdates(
            name=_extract_name(message),
            phone=_extract_phone(message),
            language=language,
            configuration=_extract_configuration(message),
            budget_raw=budget_raw,
            budget_crore=budget_crore,
            purchase_purpose=_extract_purpose(message),
            purchase_timeline=_extract_timeline(message),
            preferred_location=preferred_location,
        )

    def _respond(
        self,
        *,
        session: ConversationSession,
        message: str,
        language: Language,
    ) -> AgentTurn:
        updates = self._updates(message, language)

        if is_do_not_contact(message):
            return AgentTurn(
                reply=_say(
                    language,
                    en="Understood. I’m sorry for the disturbance. We will stop further sales communication.",
                    hi="समझ गया। असुविधा के लिए क्षमा कीजिए। आगे कोई बिक्री संबंधी संपर्क नहीं किया जाएगा।",
                    hinglish="Samajh gaya. Disturbance ke liye sorry. Aage se sales communication stop kar diya jayega.",
                ),
                language=language,
                intent="do_not_contact",
                lead_updates=updates,
                action=AgentAction(type=AgentActionType.END_CONVERSATION),
                should_end=True,
                end_reason=EndReason.DO_NOT_CONTACT,
            )

        if is_prompt_injection(message):
            return AgentTurn(
                reply=_say(
                    language,
                    en="I can’t share internal instructions. I can help you with confirmed information about Northstar One.",
                    hi="मैं आंतरिक निर्देश साझा नहीं कर सकता। मैं Northstar One की पुष्ट जानकारी में आपकी मदद कर सकता हूँ।",
                    hinglish="Main internal instructions share nahi kar sakta. Northstar One ki confirmed information mein help kar sakta hoon.",
                ),
                language=language,
                intent="prompt_injection_attempt",
                lead_updates=LeadUpdates(language=language),
            )

        if _GOODBYE.match(message):
            return AgentTurn(
                reply=_say(
                    language,
                    en="Thank you for your time. Have a good day.",
                    hi="आपके समय के लिए धन्यवाद। आपका दिन शुभ हो।",
                    hinglish="Aapke time ke liye thank you. Have a good day.",
                ),
                language=language,
                intent="customer_ended",
                lead_updates=updates,
                action=AgentAction(type=AgentActionType.END_CONVERSATION),
                should_end=True,
                end_reason=EndReason.CUSTOMER_ENDED,
            )

        now = self._clock()
        requested_date = _extract_date(message, now.date())
        requested_time = _extract_time(message)

        if _BUSY.search(message) or (_CALL_REQUEST.search(message) and not _VISIT.search(message)):
            if requested_date and requested_time:
                follow_up_at = datetime.combine(
                    requested_date, requested_time, tzinfo=self._timezone
                )
                return AgentTurn(
                    reply=_say(
                        language,
                        en=f"Certainly. I’ll note a callback for {follow_up_at:%A, %d %B at %I:%M %p} IST.",
                        hi=f"ज़रूर। मैं {follow_up_at:%d %B, %I:%M %p} IST पर कॉल-बैक नोट कर रहा हूँ।",
                        hinglish=f"Sure. Main {follow_up_at:%d %B, %I:%M %p} IST ka callback note kar raha hoon.",
                    ),
                    language=language,
                    intent="callback_requested",
                    lead_updates=updates,
                    action=AgentAction(
                        type=AgentActionType.SCHEDULE_FOLLOW_UP,
                        follow_up_at=follow_up_at,
                    ),
                    should_end=True,
                    end_reason=EndReason.FOLLOW_UP_REQUESTED,
                )
            question = (
                "What date and time would be convenient for a callback?"
                if not requested_date and not requested_time
                else "What time would be convenient for the callback?"
                if requested_date
                else "Which date would be convenient for the callback?"
            )
            return AgentTurn(
                reply=_say(
                    language,
                    en=f"Of course—I’ll keep this brief. {question}",
                    hi="ज़रूर, मैं अभी बातचीत रोक देता हूँ। कॉल-बैक के लिए कौन-सी तारीख और समय सुविधाजनक रहेगा?",
                    hinglish="Bilkul, main abhi conversation stop karta hoon. Callback ke liye kaunsi date aur time convenient rahega?",
                ),
                language=language,
                intent="customer_busy",
                lead_updates=updates,
            )

        if _NOT_INTERESTED.search(message):
            return AgentTurn(
                reply=_say(
                    language,
                    en="Understood. Thank you for letting me know. Have a good day.",
                    hi="समझ गया। बताने के लिए धन्यवाद। आपका दिन शुभ हो।",
                    hinglish="Understood. Batane ke liye thank you. Have a good day.",
                ),
                language=language,
                intent="not_interested",
                lead_updates=updates,
                action=AgentAction(type=AgentActionType.END_CONVERSATION),
                should_end=True,
                end_reason=EndReason.NOT_INTERESTED,
            )

        if _HUMAN.search(message):
            return AgentTurn(
                reply=_say(
                    language,
                    en="Certainly. I’ll request a Northstar Homes sales adviser to take this forward.",
                    hi="ज़रूर। मैं Northstar Homes के सेल्स सलाहकार से आगे संपर्क करने का अनुरोध दर्ज कर रहा हूँ।",
                    hinglish="Sure. Main Northstar Homes ke sales advisor ke liye handoff request raise kar raha hoon.",
                ),
                language=language,
                intent="human_handoff",
                lead_updates=updates,
                action=AgentAction(
                    type=AgentActionType.ESCALATE_TO_HUMAN,
                    escalation_reason="Customer requested a human adviser",
                ),
                should_end=True,
                end_reason=EndReason.HUMAN_HANDOFF,
            )

        if _VISIT.search(message):
            if not requested_date or not requested_time:
                if not requested_date and not requested_time:
                    question = "Which date and time would you prefer for the site visit?"
                elif not requested_date:
                    question = "Which date would you prefer for the site visit?"
                else:
                    question = "What time would you prefer for the site visit?"
                return AgentTurn(
                    reply=_say(
                        language,
                        en=question,
                        hi="साइट विज़िट के लिए आप कौन-सी तारीख और समय पसंद करेंगे?",
                        hinglish="Site visit ke liye aap kaunsi date aur time prefer karenge?",
                    ),
                    language=language,
                    intent="site_visit_details_needed",
                    lead_updates=updates,
                )
            return AgentTurn(
                reply=_say(
                    language,
                    en="I’ll check that site-visit slot now.",
                    hi="मैं अभी उस साइट-विज़िट स्लॉट की उपलब्धता जाँचता हूँ।",
                    hinglish="Main abhi us site-visit slot ko check karta hoon.",
                ),
                language=language,
                intent="site_visit_requested",
                lead_updates=updates,
                action=AgentAction(
                    type=AgentActionType.BOOK_SITE_VISIT,
                    booking_date=requested_date,
                    booking_time=requested_time,
                ),
            )

        unknown_topic = next(
            (topic for topic, pattern in _UNKNOWN_TOPICS.items() if pattern.search(message)),
            None,
        )
        if unknown_topic:
            return AgentTurn(
                reply=_say(
                    language,
                    en="I don’t have confirmed information about that. Would you like me to connect you with a Northstar Homes sales adviser?",
                    hi="मेरे पास इसकी पुष्ट जानकारी नहीं है। क्या मैं आपको Northstar Homes के सेल्स सलाहकार से जोड़ दूँ?",
                    hinglish="Mere paas iski confirmed information nahi hai. Kya main aapko Northstar Homes ke sales advisor se connect kar doon?",
                ),
                language=language,
                intent=f"unknown_{unknown_topic}",
                lead_updates=updates,
                unknown_question=True,
            )

        if _EXPENSIVE.search(message):
            updates.objection = "price"
            return AgentTurn(
                reply=_say(
                    language,
                    en="I understand. I don’t have a confirmed discount to offer. What budget range would be comfortable for you?",
                    hi="मैं समझता हूँ। मेरे पास किसी पुष्ट छूट की जानकारी नहीं है। आपका सुविधाजनक बजट कितना है?",
                    hinglish="Samajh sakta hoon. Mere paas koi confirmed discount nahi hai. Aapka comfortable budget range kya hai?",
                ),
                language=language,
                intent="price_objection",
                lead_updates=updates,
            )

        config = updates.configuration or session.profile.configuration
        asks_price = re.search(r"\b(?:price|cost|rate|kitna|कितना|कीमत)\b", message, re.IGNORECASE)
        asks_location = re.search(
            r"\b(?:where|location|located|sector|kahan|कहाँ|लोकेशन)\b", message, re.IGNORECASE
        )

        if asks_price:
            if config == Configuration.TWO_BHK:
                fact = "The 2 BHK starts from ₹1.35 crore onwards."
            elif config == Configuration.THREE_BHK:
                fact = "The 3 BHK starts from ₹1.75 crore onwards."
            else:
                fact = "The 2 BHK starts from ₹1.35 crore onwards, and the 3 BHK from ₹1.75 crore onwards."
            return AgentTurn(
                reply=_say(
                    language,
                    en=f"{fact} Which configuration are you considering?"
                    if not config
                    else f"{fact} What approximate budget are you working with?",
                    hi="2 BHK की शुरुआती कीमत ₹1.35 करोड़ onwards और 3 BHK की ₹1.75 करोड़ onwards है। आप कौन-सा विकल्प देख रहे हैं?",
                    hinglish="2 BHK ₹1.35 crore onwards aur 3 BHK ₹1.75 crore onwards se start hota hai. Aap kaunsa configuration consider kar rahe hain?",
                ),
                language=language,
                intent="price_enquiry",
                lead_updates=updates,
            )

        if asks_location:
            return AgentTurn(
                reply=_say(
                    language,
                    en="Northstar One is in Sector 79, Gurugram. Are you considering a 2 BHK or 3 BHK?",
                    hi="Northstar One सेक्टर 79, गुरुग्राम में है। आप 2 BHK देख रहे हैं या 3 BHK?",
                    hinglish="Northstar One Sector 79, Gurugram mein hai. Aap 2 BHK consider kar rahe hain ya 3 BHK?",
                ),
                language=language,
                intent="location_enquiry",
                lead_updates=updates,
            )

        effective_budget = updates.budget_raw or session.profile.budget_raw
        effective_purpose = updates.purchase_purpose or session.profile.purchase_purpose
        effective_timeline = updates.purchase_timeline or session.profile.purchase_timeline

        if _GREETING.match(message):
            reply = _say(
                language,
                en="Hello, I’m Aarohi, Northstar Homes’ AI sales assistant. Are you looking for a 2 BHK or 3 BHK?",
                hi="नमस्ते, मैं Aarohi हूँ, Northstar Homes की AI सेल्स असिस्टेंट। आप 2 BHK देख रहे हैं या 3 BHK?",
                hinglish="Hi, main Aarohi hoon, Northstar Homes ki AI sales assistant. Aap 2 BHK dekh rahe hain ya 3 BHK?",
            )
        elif not config:
            reply = _say(
                language,
                en="Northstar One offers 2 BHK and 3 BHK homes. Which configuration are you considering?",
                hi="Northstar One में 2 BHK और 3 BHK विकल्प हैं। आप कौन-सा विकल्प देख रहे हैं?",
                hinglish="Northstar One mein 2 BHK aur 3 BHK options hain. Aap kaunsa configuration consider kar rahe hain?",
            )
        elif not effective_budget:
            price = (
                "₹1.35 crore onwards" if config == Configuration.TWO_BHK else "₹1.75 crore onwards"
            )
            reply = _say(
                language,
                en=f"The {config.value} starts from {price}. What approximate budget are you considering?",
                hi=f"{config.value} की शुरुआती कीमत {price} है। आपका अनुमानित बजट कितना है?",
                hinglish=f"{config.value} {price} se start hota hai. Aapka approximate budget kya hai?",
            )
        elif effective_purpose in {None, PurchasePurpose.UNKNOWN}:
            reply = _say(
                language,
                en="Thank you. Is the purchase mainly for self-use or investment?",
                hi="धन्यवाद। यह खरीद मुख्य रूप से खुद रहने के लिए है या निवेश के लिए?",
                hinglish="Thank you. Purchase self-use ke liye hai ya investment ke liye?",
            )
        elif not effective_timeline:
            reply = _say(
                language,
                en="What purchase timeline are you considering?",
                hi="आप किस समय-सीमा में खरीदने की योजना बना रहे हैं?",
                hinglish="Aap kis timeline mein purchase plan kar rahe hain?",
            )
        else:
            reply = _say(
                language,
                en="Thank you—that gives me a clear picture. Would you like to arrange a site visit?",
                hi="धन्यवाद, आपकी आवश्यकता स्पष्ट है। क्या आप साइट विज़िट तय करना चाहेंगे?",
                hinglish="Thank you, requirement clear hai. Kya aap site visit arrange karna chahenge?",
            )

        return AgentTurn(
            reply=reply,
            language=language,
            intent="lead_qualification",
            lead_updates=updates,
        )
