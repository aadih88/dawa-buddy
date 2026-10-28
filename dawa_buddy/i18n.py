"""Hindi and Kannada text for everything that is not model-written: safety notes, severity headings, the timetable, the disclaimer.

No model touches these. Each safety rule has a stable `code` (safety.py); its sentence here is a fixed template filled with the rule's own values,
so what a family reads is exactly what was reviewed. The dose sentences live beside the medicine cards (explainer.PHRASES). Every phrase here, with the
English it translates, is printed for native-speaker review in docs/language_review.md. If a rule has no translation (a new rule added without one),
the English text is shown rather than a guess, and a test fails so it cannot go unnoticed.
Medicine and ingredient names, numbers and units stay as written (Latin script): that is what is printed on the strip.
"""
from __future__ import annotations
from .schemas import Lang, SafetyFlag, ScheduleItem

LANGS = ("en", "hi", "kn")

SEVERITY = {
    "call_doctor": {"en": "Call your doctor", "hi": "अपने डॉक्टर से संपर्क करें", "kn": "ನಿಮ್ಮ ವೈದ್ಯರನ್ನು ಸಂಪರ್ಕಿಸಿ"},
    "ask_pharmacist": {"en": "Ask your pharmacist", "hi": "अपने दवा-विक्रेता से पूछें", "kn": "ನಿಮ್ಮ ಔಷಧಿ ಅಂಗಡಿಯವರನ್ನು ಕೇಳಿ"},
    "info": {"en": "Good to know", "hi": "जानने योग्य बात", "kn": "ತಿಳಿದುಕೊಳ್ಳಿ"},
}

# code -> language -> text. {braces} are filled from the flag's own args.
TITLES = {
    "bleeding": {"en": "Bleeding risk", "hi": "खून बहने का ख़तरा", "kn": "ರಕ್ತಸ್ರಾವದ ಅಪಾಯ"},
    "two_nsaids": {"en": "Two painkillers of the same type", "hi": "एक ही तरह की दो दर्द की दवाएँ", "kn": "ಒಂದೇ ರೀತಿಯ ಎರಡು ನೋವು ನಿವಾರಕಗಳು"},
    "nitrate_sildenafil": {"en": "Dangerous blood pressure drop", "hi": "रक्तचाप का ख़तरनाक रूप से गिरना", "kn": "ರಕ್ತದೊತ್ತಡ ಅಪಾಯಕಾರಿಯಾಗಿ ಕುಸಿಯುವ ಅಪಾಯ"},
    "potassium": {"en": "High potassium risk", "hi": "पोटैशियम बढ़ने का ख़तरा", "kn": "ಪೊಟ್ಯಾಸಿಯಮ್ ಹೆಚ್ಚಾಗುವ ಅಪಾಯ"},
    "statin_macrolide": {"en": "Muscle damage risk", "hi": "मांसपेशियों को नुकसान का ख़तरा", "kn": "ಸ್ನಾಯುಗಳಿಗೆ ಹಾನಿಯ ಅಪಾಯ"},
    "double_ingredient": {"en": "Same ingredient twice", "hi": "एक ही दवा का तत्व दो बार", "kn": "ಒಂದೇ ಔಷಧದ ಅಂಶ ಎರಡು ಬಾರಿ"},
    "paracetamol_max": {"en": "Paracetamol above 4 g a day", "hi": "पैरासिटामोल दिन में 4 ग्राम से अधिक", "kn": "ಪ್ಯಾರಾಸಿಟಮಾಲ್ ದಿನಕ್ಕೆ 4 ಗ್ರಾಂಗಿಂತ ಹೆಚ್ಚು"},
    "not_written": {"en": "Something is not written", "hi": "प्रिस्क्रिप्शन में कुछ जानकारी नहीं लिखी है", "kn": "ಔಷಧಿ ಚೀಟಿಯಲ್ಲಿ ಕೆಲವು ಮಾಹಿತಿ ಬರೆದಿಲ್ಲ"},
    "batch_alert": {"en": "Batch flagged by the regulator", "hi": "सरकारी दवा विभाग (रेगुलेटर) ने इस बैच पर चेतावनी दी है", "kn": "ಸರ್ಕಾರಿ ಔಷಧ ನಿಯಂತ್ರಕರು ಈ ಬ್ಯಾಚ್ ಬಗ್ಗೆ ಎಚ್ಚರಿಕೆ ನೀಡಿದ್ದಾರೆ"},
}
TITLE_OF = {"warfarin_aspirin": "bleeding", "warfarin_nsaid": "bleeding"}      # several rules share one title

DETAILS = {
    "warfarin_aspirin": {
        "en": "Warfarin with aspirin raises the risk of serious bleeding. Do not stop either medicine yourself; ask the prescriber to confirm this combination is intended.",
        "hi": "वारफ़रिन के साथ एस्पिरिन लेने से गंभीर रक्तस्राव का ख़तरा बढ़ जाता है। कोई भी दवा अपने आप बंद न करें; डॉक्टर से पूछें कि क्या यह जोड़ी जान-बूझकर लिखी गई है।",
        "kn": "ವಾರ್ಫರಿನ್ ಜೊತೆ ಆಸ್ಪಿರಿನ್ ತೆಗೆದುಕೊಂಡರೆ ಗಂಭೀರ ರಕ್ತಸ್ರಾವದ ಅಪಾಯ ಹೆಚ್ಚಾಗುತ್ತದೆ. ಯಾವ ಔಷಧಿಯನ್ನೂ ನೀವೇ ನಿಲ್ಲಿಸಬೇಡಿ; ಈ ಜೋಡಿ ಉದ್ದೇಶಪೂರ್ವಕವಾಗಿ ಬರೆದದ್ದೇ ಎಂದು ವೈದ್ಯರನ್ನು ಕೇಳಿ."},
    "warfarin_nsaid": {
        "en": "Painkillers like {drug} can increase bleeding on warfarin. Check with the prescriber before taking both.",
        "hi": "{drug} जैसी दर्द की दवाएँ वारफ़रिन के साथ रक्तस्राव बढ़ा सकती हैं। दोनों लेने से पहले डॉक्टर से पूछ लें।",
        "kn": "{drug} ನಂತಹ ನೋವು ನಿವಾರಕಗಳು ವಾರ್ಫರಿನ್ ಜೊತೆ ರಕ್ತಸ್ರಾವವನ್ನು ಹೆಚ್ಚಿಸಬಹುದು. ಎರಡನ್ನೂ ತೆಗೆದುಕೊಳ್ಳುವ ಮೊದಲು ವೈದ್ಯರನ್ನು ಕೇಳಿ."},
    "two_nsaids": {
        "en": "Both are anti-inflammatory painkillers (NSAIDs). Taking two together raises stomach and kidney risk. Ask whether both are really needed.",
        "hi": "दोनों सूजन-रोधी दर्द की दवाएँ (NSAIDs) हैं। दोनों साथ लेने से पेट और गुर्दे को नुकसान का ख़तरा बढ़ता है। पूछें कि क्या दोनों सचमुच ज़रूरी हैं।",
        "kn": "ಎರಡೂ ಉರಿಯೂತ ಮತ್ತು ನೋವು ಕಡಿಮೆ ಮಾಡುವ ಔಷಧಿಗಳು (NSAIDs). ಎರಡನ್ನೂ ಒಟ್ಟಿಗೆ ತೆಗೆದುಕೊಂಡರೆ ಹೊಟ್ಟೆ ಮತ್ತು ಕಿಡ್ನಿಗೆ (ಮೂತ್ರಪಿಂಡಕ್ಕೆ) ಅಪಾಯ ಹೆಚ್ಚಾಗುತ್ತದೆ. ಎರಡೂ ನಿಜಕ್ಕೂ ಬೇಕೇ ಎಂದು ಕೇಳಿ."},
    "nitrate_sildenafil": {
        "en": "Nitrates with sildenafil can cause a severe drop in blood pressure. Contact the prescriber before taking both.",
        "hi": "नाइट्रेट के साथ सिल्डेनाफिल लेने से रक्तचाप बहुत ज़्यादा गिर सकता है। दोनों लेने से पहले डॉक्टर से संपर्क करें।",
        "kn": "ನೈಟ್ರೇಟ್ ಜೊತೆ ಸಿಲ್ಡೆನಾಫಿಲ್ ತೆಗೆದುಕೊಂಡರೆ ರಕ್ತದೊತ್ತಡ ತೀವ್ರವಾಗಿ ಕುಸಿಯಬಹುದು. ಎರಡನ್ನೂ ತೆಗೆದುಕೊಳ್ಳುವ ಮೊದಲು ವೈದ್ಯರನ್ನು ಸಂಪರ್ಕಿಸಿ."},
    "potassium": {
        "en": "This pair can raise blood potassium. It is sometimes intended, but needs blood tests. Ask the prescriber about monitoring.",
        "hi": "यह जोड़ी खून में पोटैशियम बढ़ा सकती है। कभी-कभी यह जान-बूझकर दी जाती है, पर इसके लिए खून की जाँच ज़रूरी है। डॉक्टर से जाँच के बारे में पूछें।",
        "kn": "ಈ ಜೋಡಿ ರಕ್ತದಲ್ಲಿ ಪೊಟ್ಯಾಸಿಯಮ್ ಹೆಚ್ಚಿಸಬಹುದು. ಕೆಲವೊಮ್ಮೆ ಇದನ್ನು ಉದ್ದೇಶಪೂರ್ವಕವಾಗಿ ನೀಡುತ್ತಾರೆ, ಆದರೆ ರಕ್ತ ಪರೀಕ್ಷೆ ಬೇಕು. ಪರೀಕ್ಷೆಯ ಬಗ್ಗೆ ವೈದ್ಯರನ್ನು ಕೇಳಿ."},
    "statin_macrolide": {
        "en": "Clarithromycin can raise simvastatin levels and cause muscle damage. Ask the prescriber whether to pause the statin during the course.",
        "hi": "क्लैरिथ्रोमाइसिन सिमवास्टैटिन का स्तर बढ़ा सकती है और मांसपेशियों को नुकसान पहुँचा सकती है। डॉक्टर से पूछें कि कोर्स के दौरान स्टैटिन रोकनी चाहिए या नहीं।",
        "kn": "ಕ್ಲಾರಿಥ್ರೊಮೈಸಿನ್ ಸಿಮ್ವಾಸ್ಟಾಟಿನ್ ಮಟ್ಟವನ್ನು ಹೆಚ್ಚಿಸಿ ಸ್ನಾಯುಗಳಿಗೆ ಹಾನಿ ಮಾಡಬಹುದು. ಕೋರ್ಸ್ ನಡೆಯುವಾಗ ಸ್ಟ್ಯಾಟಿನ್ ನಿಲ್ಲಿಸಬೇಕೇ ಎಂದು ವೈದ್ಯರನ್ನು ಕೇಳಿ."},
    "double_ingredient": {
        "en": "Both contain {ingredients}. Taking both can mean a double dose. Ask if both are needed.",
        "hi": "दोनों में {ingredients} है। दोनों लेने से दोहरी खुराक हो सकती है। पूछें कि क्या दोनों ज़रूरी हैं।",
        "kn": "ಎರಡರಲ್ಲೂ {ingredients} ಇದೆ. ಎರಡನ್ನೂ ತೆಗೆದುಕೊಂಡರೆ ಡೋಸ್ ಎರಡು ಪಟ್ಟು ಆಗಬಹುದು. ಎರಡೂ ಬೇಕೇ ಎಂದು ಕೇಳಿ."},
    "paracetamol_max": {
        "en": "The written doses add up to {mg} mg a day, above the usual adult maximum of 4000 mg. Confirm with the prescriber.",
        "hi": "लिखी हुई खुराकें मिलकर दिन में {mg} mg होती हैं, जो वयस्कों की सामान्य अधिकतम सीमा 4000 mg से ज़्यादा है। डॉक्टर से पुष्टि करें।",
        "kn": "ಬರೆದಿರುವ ಡೋಸ್‌ಗಳನ್ನು ಕೂಡಿದರೆ ದಿನಕ್ಕೆ {mg} mg ಆಗುತ್ತದೆ, ಇದು ವಯಸ್ಕರ ಸಾಮಾನ್ಯ ಗರಿಷ್ಠ ಮಿತಿ 4000 mg ಗಿಂತ ಹೆಚ್ಚು. ವೈದ್ಯರಿಂದ ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ."},
    "batch_alert": {
        "en": "This batch appears in a {month} alert as '{status}'. Do not use it; return it to the pharmacy.",
        "hi": "यह बैच {month} की चेतावनी में '{status}' के रूप में आया है। इसका उपयोग न करें; इसे दवा की दुकान पर वापस करें।",
        "kn": "ಈ ಬ್ಯಾಚ್ {month} ರ ಎಚ್ಚರಿಕೆಯಲ್ಲಿ '{status}' ಎಂದು ಕಾಣಿಸಿಕೊಂಡಿದೆ. ಇದನ್ನು ಬಳಸಬೇಡಿ; ಔಷಧಿ ಅಂಗಡಿಗೆ ಹಿಂತಿರುಗಿಸಿ."},
}
# "Something is not written" is built from up to two parts and a closing line
NOT_WRITTEN = {
    "no_freq": {"en": "How often to take it is not written for: {names}.", "hi": "कितनी बार लेना है, यह इनके लिए नहीं लिखा है: {names}।",
                "kn": "ಎಷ್ಟು ಬಾರಿ ತೆಗೆದುಕೊಳ್ಳಬೇಕು ಎಂದು ಇವುಗಳಿಗೆ ಬರೆದಿಲ್ಲ: {names}."},
    "no_days": {"en": "The number of days is not written for: {names}.", "hi": "कितने दिन लेना है, यह इनके लिए नहीं लिखा है: {names}।",
                "kn": "ಎಷ್ಟು ದಿನ ತೆಗೆದುಕೊಳ್ಳಬೇಕು ಎಂದು ಇವುಗಳಿಗೆ ಬರೆದಿಲ್ಲ: {names}."},
    "tail": {"en": " Ask the pharmacist before you start.", "hi": " शुरू करने से पहले दवा-विक्रेता से पूछें।",
             "kn": " ಪ್ರಾರಂಭಿಸುವ ಮೊದಲು ಔಷಧಿ ಅಂಗಡಿಯವರನ್ನು ಕೇಳಿ."},
}
STATUS = {   # the regulator's status words
    "not_of_standard_quality": {"en": "not of standard quality", "hi": "मानक गुणवत्ता का नहीं (ख़राब गुणवत्ता)", "kn": "ನಿಗದಿತ ಗುಣಮಟ್ಟದ್ದಲ್ಲ (ಕಳಪೆ ಗುಣಮಟ್ಟ)"},
    "spurious": {"en": "spurious", "hi": "नकली", "kn": "ನಕಲಿ"},
    "adulterated": {"en": "adulterated", "hi": "मिलावटी", "kn": "ಕಲಬೆರಕೆ"},
    "misbranded": {"en": "misbranded", "hi": "ग़लत लेबल वाली", "kn": "ತಪ್ಪು ಲೇಬಲ್ ಇರುವ"},
}

TIMETABLE = {
    "headers": {"en": ("Time", "Medicine", "How"), "hi": ("समय", "दवा", "कैसे लें"), "kn": ("ಸಮಯ", "ಔಷಧಿ", "ತೆಗೆದುಕೊಳ್ಳುವ ರೀತಿ")},
    "slots": {"morning": {"en": "Morning", "hi": "सुबह", "kn": "ಬೆಳಿಗ್ಗೆ"}, "afternoon": {"en": "Afternoon", "hi": "दोपहर", "kn": "ಮಧ್ಯಾಹ್ನ"},
              "night": {"en": "Night", "hi": "रात", "kn": "ರಾತ್ರಿ"}, "as_needed": {"en": "As needed", "hi": "ज़रूरत पड़ने पर", "kn": "ಅಗತ್ಯವಿದ್ದಾಗ"}},
    "before": {"en": "before food", "hi": "खाने से पहले", "kn": "ಊಟದ ಮೊದಲು"},
    "after": {"en": "after food", "hi": "खाने के बाद", "kn": "ಊಟದ ನಂತರ"},
    "bedtime": {"en": "at bedtime", "hi": "सोने से पहले", "kn": "ಮಲಗುವ ಮೊದಲು"},
    "as_written": {"en": "As written", "hi": "जैसा लिखा है", "kn": "ಬರೆದಂತೆ"},
    "sos": {"en": "only when needed, follow the doctor's limit", "hi": "सिर्फ़ ज़रूरत पड़ने पर, डॉक्टर की बताई सीमा का पालन करें",
            "kn": "ಅಗತ್ಯವಿದ್ದಾಗ ಮಾತ್ರ, ವೈದ್ಯರು ಹೇಳಿದ ಮಿತಿಯನ್ನು ಪಾಲಿಸಿ"},
    "share_title": {"en": "Medicine timetable", "hi": "दवाओं की समय-सारणी", "kn": "ಔಷಧಿಗಳ ವೇಳಾಪಟ್ಟಿ"},
    "share_days": {"en": "Duration: {n} days (as written on the prescription)", "hi": "अवधि: {n} दिन (जैसा प्रिस्क्रिप्शन में लिखा है)",
                   "kn": "ಅವಧಿ: {n} ದಿನಗಳು (ಔಷಧಿ ಚೀಟಿಯಲ್ಲಿ ಬರೆದಂತೆ)"},
    "share_foot": {"en": "Not medical advice. Check with your doctor or pharmacist.", "hi": "यह चिकित्सा सलाह नहीं है। अपने डॉक्टर या दवा-विक्रेता से पूछें।",
                   "kn": "ಇದು ವೈದ್ಯಕೀಯ ಸಲಹೆ ಅಲ್ಲ. ನಿಮ್ಮ ವೈದ್ಯರು ಅಥವಾ ಔಷಧಿ ಅಂಗಡಿಯವರನ್ನು ಕೇಳಿ."},
}
DISCLAIMER = {
    "en": "Dawa Buddy explains what is written on your prescription. It does not diagnose, and it never changes a dose. If something worries you, ask your doctor or pharmacist.",
    "hi": "दवा बडी आपके प्रिस्क्रिप्शन में लिखी बातें समझाता है। यह बीमारी की पहचान नहीं करता और कभी खुराक नहीं बदलता। कोई चिंता हो तो अपने डॉक्टर या दवा-विक्रेता से पूछें।",
    "kn": "ದವಾ ಬಡ್ಡಿ ನಿಮ್ಮ ಔಷಧಿ ಚೀಟಿಯಲ್ಲಿ ಬರೆದಿರುವುದನ್ನು ವಿವರಿಸುತ್ತದೆ. ಇದು ರೋಗ ನಿರ್ಣಯ ಮಾಡುವುದಿಲ್ಲ ಮತ್ತು ಎಂದಿಗೂ ಡೋಸ್ ಬದಲಾಯಿಸುವುದಿಲ್ಲ. ಏನಾದರೂ ಚಿಂತೆಯಿದ್ದರೆ ನಿಮ್ಮ ವೈದ್ಯರು ಅಥವಾ ಔಷಧಿ ಅಂಗಡಿಯವರನ್ನು ಕೇಳಿ.",
}


AI_NOTE = {
    "en": "What each medicine is for and what to watch for is written by AI (NVIDIA Nemotron) and can contain mistakes. The dose, the warnings and the timetable come from your prescription.",
    "hi": "हर दवा किस लिए है और किन बातों का ध्यान रखें, यह AI (NVIDIA Nemotron) ने लिखा है और इसमें ग़लतियाँ हो सकती हैं। खुराक, चेतावनियाँ और समय-सारणी आपके प्रिस्क्रिप्शन से बनी हैं।",
    "kn": "ಪ್ರತಿ ಔಷಧಿ ಯಾವುದಕ್ಕೆ ಮತ್ತು ಏನನ್ನು ಗಮನಿಸಬೇಕು ಎಂಬುದನ್ನು AI (NVIDIA Nemotron) ಬರೆದಿದೆ ಮತ್ತು ತಪ್ಪುಗಳಿರಬಹುದು. ಡೋಸ್, ಎಚ್ಚರಿಕೆಗಳು ಮತ್ತು ವೇಳಾಪಟ್ಟಿ ನಿಮ್ಮ ಔಷಧಿ ಚೀಟಿಯಿಂದ ಬಂದಿವೆ.",
}
FALLBACK_NOTE = {
    "en": "",
    "hi": "हर दवा किस लिए है, यह अंग्रेज़ी में दिखाया गया है: हम इसे अभी हिन्दी में भरोसे के साथ नहीं लिख सके। खुराक, चेतावनियाँ और समय-सारणी हिन्दी में हैं।",
    "kn": "ಪ್ರತಿ ಔಷಧಿ ಯಾವುದಕ್ಕೆ ಎಂಬುದನ್ನು ಇಂಗ್ಲಿಷ್‌ನಲ್ಲಿ ತೋರಿಸಲಾಗಿದೆ: ಇದನ್ನು ಕನ್ನಡದಲ್ಲಿ ವಿಶ್ವಾಸಾರ್ಹವಾಗಿ ಬರೆಯಲು ಇನ್ನೂ ಸಾಧ್ಯವಾಗಿಲ್ಲ. ಡೋಸ್, ಎಚ್ಚರಿಕೆಗಳು ಮತ್ತು ವೇಳಾಪಟ್ಟಿ ಕನ್ನಡದಲ್ಲಿವೆ.",
}
FIXED_NOTE = {   # purpose and watch-for come from the fixed table (medinfo.py)
    "en": "What each medicine is for and what to watch for is general information from a fixed list, not written for you by AI. It does not cover everything. The dose, the warnings and the timetable come from your prescription.",
    "hi": "हर दवा किस लिए है और किन बातों का ध्यान रखें, यह एक तय सूची से दी गई सामान्य जानकारी है, AI ने आपके लिए नहीं लिखी। इसमें सब कुछ शामिल नहीं है। खुराक, चेतावनियाँ और समय-सारणी आपके प्रिस्क्रिप्शन से बनी हैं।",
    "kn": "ಪ್ರತಿ ಔಷಧಿ ಯಾವುದಕ್ಕೆ ಮತ್ತು ಏನನ್ನು ಗಮನಿಸಬೇಕು ಎಂಬುದು ನಿಗದಿತ ಪಟ್ಟಿಯಿಂದ ಬಂದ ಸಾಮಾನ್ಯ ಮಾಹಿತಿ ಮಾತ್ರ; AI ನಿಮಗಾಗಿ ಬರೆದದ್ದಲ್ಲ. ಇದರಲ್ಲಿ ಎಲ್ಲವೂ ಇಲ್ಲ. ಡೋಸ್, ಎಚ್ಚರಿಕೆಗಳು ಮತ್ತು ವೇಳಾಪಟ್ಟಿ ನಿಮ್ಮ ಔಷಧಿ ಚೀಟಿಯಿಂದ ಬಂದಿವೆ.",
}
PARTIAL_NOTE = {   # some medicines from the fixed table, the rest in English from AI
    "en": "",
    "hi": "कुछ दवाओं की जानकारी तय सूची से हिन्दी में है; बाकी अंग्रेज़ी में AI ने लिखी है और उसमें ग़लतियाँ हो सकती हैं। खुराक, चेतावनियाँ और समय-सारणी हिन्दी में हैं।",
    "kn": "ಕೆಲವು ಔಷಧಿಗಳ ಮಾಹಿತಿ ನಿಗದಿತ ಪಟ್ಟಿಯಿಂದ ಕನ್ನಡದಲ್ಲಿದೆ; ಉಳಿದವುಗಳದ್ದು ಇಂಗ್ಲಿಷ್‌ನಲ್ಲಿ AI ಬರೆದಿದೆ ಮತ್ತು ತಪ್ಪುಗಳಿರಬಹುದು. ಡೋಸ್, ಎಚ್ಚರಿಕೆಗಳು ಮತ್ತು ವೇಳಾಪಟ್ಟಿ ಕನ್ನಡದಲ್ಲಿವೆ.",
}


LABELS = {   # headings and captions of the explainer screen
    "medicines": {"en": "Your medicines", "hi": "आपकी दवाएँ", "kn": "ನಿಮ್ಮ ಔಷಧಿಗಳು"},
    "safety": {"en": "Safety notes", "hi": "सुरक्षा संबंधी बातें", "kn": "ಸುರಕ್ಷತಾ ಮಾಹಿತಿ"},
    "from_rx": {"en": "From your prescription", "hi": "आपके प्रिस्क्रिप्शन से", "kn": "ನಿಮ್ಮ ಔಷಧಿ ಚೀಟಿಯಿಂದ"},
    "watch_for": {"en": "Watch for", "hi": "ध्यान रखें", "kn": "ಗಮನಿಸಿ"},
    "timetable": {"en": "Your day, hour by hour", "hi": "आपका दिन, समय के अनुसार", "kn": "ನಿಮ್ಮ ದಿನ, ಸಮಯಕ್ಕೆ ತಕ್ಕಂತೆ"},
    "one_time": {"en": "One-time dose (not part of the daily routine)", "hi": "सिर्फ़ एक बार की खुराक (रोज़ की नहीं)", "kn": "ಒಂದೇ ಬಾರಿಯ ಡೋಸ್ (ದಿನನಿತ್ಯದ್ದಲ್ಲ)"},
    "download": {"en": "Download the timetable to share", "hi": "साझा करने के लिए समय-सारणी डाउनलोड करें", "kn": "ಹಂಚಿಕೊಳ್ಳಲು ವೇಳಾಪಟ್ಟಿ ಡೌನ್‌ಲೋಡ್ ಮಾಡಿ"},
}


def explainer_note(lang: str, explanations) -> str:
    """Which notice sits above the medicine cards: what was fixed, what was AI, and what fell back to English."""
    n = len(explanations)
    fixed = sum(1 for e in explanations if e.fixed)
    english = sum(1 for e in explanations if e.language_fallback)
    if lang == "en":
        return AI_NOTE["en"]
    if fixed == n and n:
        return FIXED_NOTE[lang]
    if fixed:
        return PARTIAL_NOTE[lang]
    return FALLBACK_NOTE[lang] if english else AI_NOTE[lang]


def _pick(table: dict, lang: str) -> str:
    return table.get(lang) or table["en"]


def flag_text(flag: SafetyFlag, lang: Lang) -> tuple[str, str]:
    """(title, detail) of a safety flag in `lang`. Unknown codes and English return the rule's own English text."""
    if lang == "en" or not flag.code:
        return flag.title, flag.detail
    title_key = TITLE_OF.get(flag.code, flag.code)
    if flag.code == "not_written":
        parts = [_pick(NOT_WRITTEN[k], lang).format(names=flag.args.get(name, "")) for k, name in (("no_freq", "no_freq"), ("no_days", "no_days")) if flag.args.get(name)]
        return _pick(TITLES["not_written"], lang), " ".join(p.strip() for p in parts) + _pick(NOT_WRITTEN["tail"], lang)
    if title_key not in TITLES or flag.code not in DETAILS:
        return flag.title, flag.detail
    args = dict(flag.args)
    if flag.code == "batch_alert":
        args["status"] = _pick(STATUS.get(args.get("status", ""), {"en": str(args.get("status", "")).replace("_", " ")}), lang)
    return _pick(TITLES[title_key], lang), _pick(DETAILS[flag.code], lang).format(**{**{"drug": "", "ingredients": "", "mg": "", "month": "", "status": ""}, **args})


def localize_flags(flags: list[SafetyFlag], lang: Lang) -> list[SafetyFlag]:
    out = []
    for f in flags:
        title, detail = flag_text(f, lang)
        out.append(f.model_copy(update={"title": title, "detail": detail}))
    return out


def instruction(amount: str | None, timing: str | None, lang: Lang) -> str:
    """The 'how' cell of a timetable row: the amount to take and the food timing, in the reader's language."""
    t = TIMETABLE
    when = {"before food": _pick(t["before"], lang), "after food": _pick(t["after"], lang), "bedtime": _pick(t["bedtime"], lang)}.get(timing or "", "")
    return ", ".join(p for p in (amount, when) if p) or _pick(t["as_written"], lang)


def schedule_rows(items: list[ScheduleItem], lang: Lang) -> list[dict]:
    h = TIMETABLE["headers"][lang]
    return [{h[0]: f"{i.time} {_pick(TIMETABLE['slots'][i.slot], lang)}" if i.slot != "as_needed" else _pick(TIMETABLE["slots"]["as_needed"], lang),
             h[1]: i.med, h[2]: i.instruction} for i in items]


def share_text(items: list[ScheduleItem], days: int | None, lang: Lang) -> str:
    """The WhatsApp-able timetable, in the reader's language."""
    t = TIMETABLE
    lines = [_pick(t["share_title"], lang)]
    daily = [i for i in items if i.slot != "once"]
    once = [i for i in items if i.slot == "once"]
    lines += [f"{i.time} - {i.med}: {i.instruction}" for i in daily]
    if once:
        lines += ["", _pick(LABELS["one_time"], lang) + ":"] + [f"- {i.med}: {i.instruction}" for i in once]
    if days:
        lines.append(_pick(t["share_days"], lang).format(n=days))
    lines.append(_pick(t["share_foot"], lang))
    return "\n".join(lines)
