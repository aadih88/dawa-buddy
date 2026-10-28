"""Fixed "what is it for" and "watch for" text, per active ingredient, in English and Kannada. No model writes any of it.

Why this exists: the Kannada AI text was unreliable (fluent-looking nonsense, see README), so for the most common ingredients the app shows
this reviewed-by-a-human table instead. An ingredient that is not here is not guessed: the reader sees the English AI line with a notice.

How a line is built (so a reviewer checks short pieces, not 110 paragraphs):
  purpose  = "This medicine is used {P}."                P: one phrase per ingredient (MEDS)
  watch    = "Some people get {side effects}." + the warning sentences that apply     (SIDE, WARN)
A combination (two or more ingredients) is composed from its parts: purposes joined, side effects and warnings merged without repeats.
Medicine names, numbers and units are not translated. Every phrase is printed for native-speaker review in docs/language_review.md.
Rules for what goes in: common, well-documented effects only; no dose advice (the dose is your prescription's); warnings say who to tell, never "stop".
"""
from __future__ import annotations
import re

PURPOSE = {"en": "This medicine is used {p}.", "kn": "ಈ ಔಷಧಿಯನ್ನು {p} ಬಳಸಲಾಗುತ್ತದೆ."}
PURPOSE_JOIN = {"en": ", and ", "kn": ", ಹಾಗೂ "}
SIDE_SENTENCE = {"en": "Some people get {x}.", "kn": "ಕೆಲವರಲ್ಲಿ {x} ಉಂಟಾಗಬಹುದು."}
LIST_JOIN = {"en": ", ", "kn": ", "}

# side effect -> (English, Kannada)
SIDE = {
    "nausea": ("nausea", "ವಾಕರಿಕೆ"),
    "stomach": ("an upset stomach", "ಹೊಟ್ಟೆ ಕೆಡುವುದು"),
    "stomach_pain": ("stomach pain", "ಹೊಟ್ಟೆ ನೋವು"),
    "heartburn": ("heartburn", "ಎದೆಯುರಿ"),
    "diarrhoea": ("loose motions", "ಭೇದಿ"),
    "constipation": ("constipation", "ಮಲಬದ್ಧತೆ"),
    "bloating": ("a bloated stomach", "ಹೊಟ್ಟೆ ಉಬ್ಬರ"),
    "headache": ("headache", "ತಲೆನೋವು"),
    "dizzy": ("dizziness", "ತಲೆತಿರುಗುವಿಕೆ"),
    "drowsy": ("sleepiness", "ನಿದ್ರೆ ಮಂಪರು"),
    "dry_mouth": ("a dry mouth", "ಬಾಯಿ ಒಣಗುವುದು"),
    "dry_cough": ("a dry cough", "ಒಣ ಕೆಮ್ಮು"),
    "ankle_swelling": ("swollen feet", "ಕಾಲು ಊದಿಕೊಳ್ಳುವುದು"),
    "flushing": ("a flushed face", "ಮುಖ ಕೆಂಪಾಗುವುದು"),
    "fast_heart": ("a fast heartbeat", "ಎದೆ ಬಡಿತ ಹೆಚ್ಚಾಗುವುದು"),
    "slow_heart": ("a slow heartbeat", "ಎದೆ ಬಡಿತ ನಿಧಾನವಾಗುವುದು"),
    "tired": ("tiredness", "ಆಯಾಸ"),
    "weak": ("weakness", "ದೌರ್ಬಲ್ಯ"),
    "muscle_pain": ("muscle pain", "ಸ್ನಾಯು ನೋವು"),
    "cramps": ("muscle cramps", "ಸ್ನಾಯು ಸೆಳೆತ"),
    "frequent_urine": ("passing urine more often", "ಹೆಚ್ಚು ಬಾರಿ ಮೂತ್ರ ಬರುವುದು"),
    "sleep_trouble": ("trouble sleeping", "ನಿದ್ರೆ ಬಾರದಿರುವುದು"),
    "tremor": ("shaky hands", "ಕೈ ನಡುಗುವುದು"),
    "weight_gain": ("weight gain", "ತೂಕ ಹೆಚ್ಚಾಗುವುದು"),
    "appetite": ("a lower appetite", "ಹಸಿವು ಕಡಿಮೆಯಾಗುವುದು"),
    "metallic": ("a metal taste in the mouth", "ಬಾಯಿಯಲ್ಲಿ ಲೋಹದ ರುಚಿ"),
    "sun": ("skin that burns easily in the sun", "ಬಿಸಿಲಿಗೆ ಚರ್ಮ ಬೇಗ ಸುಡುವುದು"),
    "blur": ("blurred vision", "ಕಣ್ಣು ಮಂಜಾಗುವುದು"),
    "skin_irritation": ("burning or redness of the skin where applied", "ಹಚ್ಚಿದ ಜಾಗದಲ್ಲಿ ಉರಿ ಅಥವಾ ಕೆಂಪಾಗುವುದು"),
    "dry_skin": ("dry skin and lips", "ಒಣ ಚರ್ಮ ಮತ್ತು ಒಣ ತುಟಿ"),
    "genital_itch": ("itching in the private parts", "ಗುಪ್ತಾಂಗದಲ್ಲಿ ತುರಿಕೆ"),
    "mood": ("mood changes", "ಮನಸ್ಥಿತಿಯಲ್ಲಿ ಬದಲಾವಣೆ"),
    "appetite_up": ("a bigger appetite", "ಹಸಿವು ಹೆಚ್ಚಾಗುವುದು"),
    "joint_pain": ("joint pain", "ಕೀಲು ನೋವು"),
    "hot_flush": ("hot flushes", "ಮೈ ಬಿಸಿಯಾಗುವುದು"),
    "mouth_ulcer": ("mouth sores", "ಬಾಯಿ ಹುಣ್ಣು"),
}

# warning -> (English, Kannada): a whole sentence each
WARN = {
    "allergy": ("If you get a rash, swelling of the face or lips, or trouble breathing, get medical help at once.",
                "ಚರ್ಮದ ಮೇಲೆ ದದ್ದು, ಮುಖ ಅಥವಾ ತುಟಿ ಊದಿಕೊಳ್ಳುವುದು ಅಥವಾ ಉಸಿರಾಡಲು ತೊಂದರೆ ಆದರೆ ತಕ್ಷಣ ವೈದ್ಯಕೀಯ ಸಹಾಯ ಪಡೆಯಿರಿ."),
    "bleed": ("Black stools, vomiting blood or unusual bleeding: see a doctor at once.",
              "ಕಪ್ಪು ಮಲ, ರಕ್ತ ವಾಂತಿ ಅಥವಾ ಅಸಾಮಾನ್ಯ ರಕ್ತಸ್ರಾವ ಆದರೆ ತಕ್ಷಣ ವೈದ್ಯರನ್ನು ಕಾಣಿ."),
    "low_sugar": ("Sweating, shaking or confusion can mean low blood sugar: have something sweet and tell your doctor.",
                  "ಬೆವರುವುದು, ನಡುಕ ಅಥವಾ ಗೊಂದಲ ಇದ್ದರೆ ರಕ್ತದಲ್ಲಿ ಸಕ್ಕರೆ ಕಡಿಮೆಯಾಗಿರಬಹುದು: ಸಿಹಿ ಏನಾದರೂ ತಿಂದು ವೈದ್ಯರಿಗೆ ತಿಳಿಸಿ."),
    "bad_diarrhoea": ("Severe or bloody loose motions: tell your doctor.",
                      "ತೀವ್ರ ಅಥವಾ ರಕ್ತಮಿಶ್ರಿತ ಭೇದಿ ಆದರೆ ವೈದ್ಯರಿಗೆ ತಿಳಿಸಿ."),
    "tendon": ("Pain or swelling near the heel or a joint: tell your doctor.",
               "ಹಿಮ್ಮಡಿ ಅಥವಾ ಕೀಲಿನ ಬಳಿ ನೋವು ಅಥವಾ ಊತ ಬಂದರೆ ವೈದ್ಯರಿಗೆ ತಿಳಿಸಿ."),
    "no_alcohol": ("Do not drink alcohol with this medicine.", "ಈ ಔಷಧಿ ತೆಗೆದುಕೊಳ್ಳುವಾಗ ಮದ್ಯ ಸೇವಿಸಬೇಡಿ."),
    "no_driving": ("Do not drive if you feel sleepy.", "ನಿದ್ರೆ ಮಂಪರು ಇದ್ದರೆ ವಾಹನ ಚಲಾಯಿಸಬೇಡಿ."),
    "liver": ("Yellow eyes or skin, or dark urine: tell your doctor.",
              "ಕಣ್ಣು ಅಥವಾ ಚರ್ಮ ಹಳದಿಯಾದರೆ ಅಥವಾ ಮೂತ್ರ ಗಾಢ ಬಣ್ಣವಾದರೆ ವೈದ್ಯರಿಗೆ ತಿಳಿಸಿ."),
    "muscle": ("Muscle pain or weakness with no clear reason: tell your doctor.",
               "ಕಾರಣವಿಲ್ಲದ ಸ್ನಾಯು ನೋವು ಅಥವಾ ದೌರ್ಬಲ್ಯ ಇದ್ದರೆ ವೈದ್ಯರಿಗೆ ತಿಳಿಸಿ."),
    "dont_stop": ("Do not stop it suddenly without asking your doctor.",
                  "ವೈದ್ಯರನ್ನು ಕೇಳದೆ ಇದ್ದಕ್ಕಿದ್ದಂತೆ ನಿಲ್ಲಿಸಬೇಡಿ."),
    "finish": ("Take it for the full number of days your doctor wrote.",
               "ವೈದ್ಯರು ಬರೆದಿರುವ ಪೂರ್ಣ ದಿನಗಳವರೆಗೆ ತೆಗೆದುಕೊಳ್ಳಿ."),
    "stand_slowly": ("Stand up slowly.", "ನಿಧಾನವಾಗಿ ಎದ್ದು ನಿಲ್ಲಿ."),
    "pregnancy": ("Tell your doctor if you are pregnant or planning a pregnancy.",
                  "ನೀವು ಗರ್ಭಿಣಿಯಾಗಿದ್ದರೆ ಅಥವಾ ಗರ್ಭಧಾರಣೆಗೆ ಯೋಜಿಸುತ್ತಿದ್ದರೆ ವೈದ್ಯರಿಗೆ ತಿಳಿಸಿ."),
    "no_pregnancy": ("This medicine must never be taken in pregnancy.", "ಈ ಔಷಧಿಯನ್ನು ಗರ್ಭಾವಸ್ಥೆಯಲ್ಲಿ ಎಂದಿಗೂ ತೆಗೆದುಕೊಳ್ಳಬಾರದು."),
    "no_extra_paracetamol": ("Do not take other medicines that also contain paracetamol.",
                             "ಪ್ಯಾರಾಸಿಟಮಾಲ್ ಇರುವ ಬೇರೆ ಔಷಧಿಗಳನ್ನು ಜೊತೆಗೆ ತೆಗೆದುಕೊಳ್ಳಬೇಡಿ."),
    "dependency": ("It can become a habit: do not take more than is written.",
                   "ಇದು ಅಭ್ಯಾಸವಾಗಬಹುದು: ಬರೆದಿರುವುದಕ್ಕಿಂತ ಹೆಚ್ಚು ತೆಗೆದುಕೊಳ್ಳಬೇಡಿ."),
    "self_harm": ("If your mood gets worse or you think of harming yourself, contact a doctor at once.",
                  "ಮನಸ್ಥಿತಿ ಹದಗೆಟ್ಟರೆ ಅಥವಾ ನಿಮಗೆ ನೀವೇ ಹಾನಿ ಮಾಡಿಕೊಳ್ಳುವ ಯೋಚನೆ ಬಂದರೆ ತಕ್ಷಣ ವೈದ್ಯರನ್ನು ಸಂಪರ್ಕಿಸಿ."),
    "slow_to_work": ("It can take a few weeks to show its full effect.",
                     "ಪೂರ್ಣ ಪರಿಣಾಮ ಕಾಣಲು ಕೆಲವು ವಾರಗಳು ಬೇಕಾಗಬಹುದು."),
    "heart_rhythm": ("Fainting or an uneven heartbeat: tell your doctor.",
                     "ಮೂರ್ಛೆ ಹೋದರೆ (ತಲೆ ತಿರುಗಿ ಬಿದ್ದರೆ) ಅಥವಾ ಎದೆ ಬಡಿತ ಏರುಪೇರಾದರೆ ವೈದ್ಯರಿಗೆ ತಿಳಿಸಿ."),
    "ear_kidney": ("Ringing or loss of hearing, or passing much less urine: tell your doctor.",
                   "ಕಿವಿಯಲ್ಲಿ ಸದ್ದು, ಕೇಳುವ ಶಕ್ತಿ ಕಡಿಮೆಯಾಗುವುದು ಅಥವಾ ಮೂತ್ರ ತುಂಬಾ ಕಡಿಮೆಯಾದರೆ ವೈದ್ಯರಿಗೆ ತಿಳಿಸಿ."),
    "wheeze": ("If wheezing or breathing trouble gets worse, tell your doctor.",
               "ಉಬ್ಬಸ (ದಮ್ಮು) ಅಥವಾ ಉಸಿರಾಟದ ತೊಂದರೆ ಹೆಚ್ಚಾದರೆ ವೈದ್ಯರಿಗೆ ತಿಳಿಸಿ."),
    "breath": ("Breathlessness or swollen legs: tell your doctor.",
               "ಉಸಿರು ಕಟ್ಟುವುದು ಅಥವಾ ಕಾಲು ಊದಿಕೊಂಡರೆ ವೈದ್ಯರಿಗೆ ತಿಳಿಸಿ."),
    "ask_new": ("Ask your doctor or pharmacist before taking any new medicine, including painkillers.",
                "ಯಾವುದೇ ಹೊಸ ಔಷಧಿ, ನೋವು ನಿವಾರಕ ಸೇರಿದಂತೆ, ತೆಗೆದುಕೊಳ್ಳುವ ಮೊದಲು ವೈದ್ಯರು ಅಥವಾ ಔಷಧಿ ಅಂಗಡಿಯವರನ್ನು ಕೇಳಿ."),
    "blood_test": ("Get the blood tests your doctor advises.", "ವೈದ್ಯರು ಸೂಚಿಸಿದ ರಕ್ತ ಪರೀಕ್ಷೆಗಳನ್ನು ಮಾಡಿಸಿ."),
    "nitrate": ("Never take it with medicines for the heart called nitrates.",
                "ನೈಟ್ರೇಟ್ ಎಂಬ ಹೃದಯದ ಔಷಧಿಗಳ ಜೊತೆ ಇದನ್ನು ಎಂದಿಗೂ ತೆಗೆದುಕೊಳ್ಳಬೇಡಿ."),
    "no_pde5": ("Never take it with sildenafil or tadalafil.",
                "ಸಿಲ್ಡೆನಾಫಿಲ್ ಅಥವಾ ಟಡಾಲಾಫಿಲ್ ಜೊತೆ ಇದನ್ನು ಎಂದಿಗೂ ತೆಗೆದುಕೊಳ್ಳಬೇಡಿ."),
    "sick": ("If you are vomiting or very unwell, ask your doctor whether to carry on.",
             "ವಾಂತಿ ಆಗುತ್ತಿದ್ದರೆ ಅಥವಾ ತುಂಬಾ ಅಸ್ವಸ್ಥರಾಗಿದ್ದರೆ ಮುಂದುವರಿಸಬೇಕೇ ಎಂದು ವೈದ್ಯರನ್ನು ಕೇಳಿ."),
    "water": ("Drink plenty of water.", "ಸಾಕಷ್ಟು ನೀರು ಕುಡಿಯಿರಿ."),
    "clots": ("Pain or swelling in one leg, chest pain or sudden breathlessness: get help at once.",
              "ಒಂದು ಕಾಲಿನಲ್ಲಿ ನೋವು ಅಥವಾ ಊತ, ಎದೆ ನೋವು ಅಥವಾ ಇದ್ದಕ್ಕಿದ್ದಂತೆ ಉಸಿರಾಟದ ತೊಂದರೆ ಆದರೆ ತಕ್ಷಣ ಸಹಾಯ ಪಡೆಯಿರಿ."),
    "thyroid_test": ("Get your thyroid blood test done as advised.", "ವೈದ್ಯರು ಹೇಳಿದಂತೆ ಥೈರಾಯ್ಡ್ ರಕ್ತ ಪರೀಕ್ಷೆ ಮಾಡಿಸಿ."),
    "once_weekly": ("Take it only on the day your doctor wrote; it is often once a week, never daily unless written.",
                    "ವೈದ್ಯರು ಬರೆದ ದಿನದಂದು ಮಾತ್ರ ತೆಗೆದುಕೊಳ್ಳಿ; ಇದನ್ನು ಹೆಚ್ಚಾಗಿ ವಾರಕ್ಕೊಮ್ಮೆ ಕೊಡಲಾಗುತ್ತದೆ, ಬರೆಯದ ಹೊರತು ಪ್ರತಿದಿನ ಅಲ್ಲ."),
    "infection": ("Tell your doctor about fever or signs of infection.",
                  "ಜ್ವರ ಅಥವಾ ಸೋಂಕಿನ ಲಕ್ಷಣಗಳಿದ್ದರೆ ವೈದ್ಯರಿಗೆ ತಿಳಿಸಿ."),
    "skin_only": ("Use it only on the skin and only for the days your doctor said; do not put it on the face unless told.",
                  "ಚರ್ಮದ ಮೇಲೆ ಮಾತ್ರ, ವೈದ್ಯರು ಹೇಳಿದ ದಿನಗಳವರೆಗೆ ಮಾತ್ರ ಬಳಸಿ; ಹೇಳದ ಹೊರತು ಮುಖಕ್ಕೆ ಹಚ್ಚಬೇಡಿ."),
    "supervised": ("It is given under a doctor's care: ask your doctor about side effects.",
                   "ಇದನ್ನು ವೈದ್ಯರ ನಿಗಾದಲ್ಲಿ ನೀಡಲಾಗುತ್ತದೆ: ಅಡ್ಡ ಪರಿಣಾಮಗಳ ಬಗ್ಗೆ ವೈದ್ಯರನ್ನು ಕೇಳಿ."),
    "overdose_vit": ("Do not take more than written: too much can cause nausea and weakness.",
                     "ಬರೆದಿರುವುದಕ್ಕಿಂತ ಹೆಚ್ಚು ತೆಗೆದುಕೊಳ್ಳಬೇಡಿ: ಹೆಚ್ಚಾದರೆ ವಾಕರಿಕೆ ಮತ್ತು ದೌರ್ಬಲ್ಯ ಉಂಟಾಗಬಹುದು."),
    "mood": ("Low mood or bad dreams: tell your doctor.", "ಮನಸ್ಸು ಖಿನ್ನವಾದರೆ ಅಥವಾ ಕೆಟ್ಟ ಕನಸು ಬಂದರೆ ವೈದ್ಯರಿಗೆ ತಿಳಿಸಿ."),
}

# purpose phrases (English, Kannada); each completes "This medicine is used ..." / "ಈ ಔಷಧಿಯನ್ನು ... ಬಳಸಲಾಗುತ್ತದೆ."
_P = {
    "fever_pain": ("to bring down fever and ease mild pain", "ಜ್ವರ ಮತ್ತು ಸಾಧಾರಣ ನೋವನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "pain_swell_fever": ("to ease pain, swelling and fever", "ನೋವು, ಊತ ಮತ್ತು ಜ್ವರವನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "pain_swell": ("to ease pain and swelling", "ನೋವು ಮತ್ತು ಊತವನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "pain_fever": ("to ease pain and fever", "ನೋವು ಮತ್ತು ಜ್ವರವನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "pain": ("to ease pain", "ನೋವನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "strong_pain": ("to ease strong pain", "ತೀವ್ರ ನೋವನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "acid": ("to lower stomach acid and ease heartburn and ulcers", "ಹೊಟ್ಟೆಯಲ್ಲಿ ಆಮ್ಲ ಕಡಿಮೆ ಮಾಡಿ ಎದೆಯುರಿ ಮತ್ತು ಹುಣ್ಣಿನಿಂದ ಆರಾಮ ನೀಡಲು"),
    "vomit": ("to ease nausea and vomiting", "ವಾಕರಿಕೆ ಮತ್ತು ವಾಂತಿಯನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "ulcer": ("to heal ulcers in the stomach or gut", "ಹೊಟ್ಟೆ ಅಥವಾ ಕರುಳಿನ ಹುಣ್ಣನ್ನು ಗುಣಪಡಿಸಲು"),
    "constipation": ("to ease constipation", "ಮಲಬದ್ಧತೆಯನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "cramp_pain": ("to ease cramping stomach pain", "ಹೊಟ್ಟೆಯ ಸೆಳೆತ ನೋವನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "liver_gall": ("to treat some liver and gallbladder problems", "ಲಿವರ್ (ಯಕೃತ್ತು) ಮತ್ತು ಪಿತ್ತಕೋಶದ ಕೆಲವು ತೊಂದರೆಗಳಿಗೆ ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "gut_infection": ("to treat some gut infections and liver-related problems", "ಕರುಳಿನ ಕೆಲವು ಸೋಂಕು ಮತ್ತು ಲಿವರ್‌ಗೆ (ಯಕೃತ್ತಿಗೆ) ಸಂಬಂಧಿಸಿದ ತೊಂದರೆಗಳಿಗೆ ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "nausea_digest": ("to ease nausea and poor digestion", "ವಾಕರಿಕೆ ಮತ್ತು ಜೀರ್ಣಕ್ರಿಯೆಯ ತೊಂದರೆಯನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "bacteria": ("to treat infections caused by bacteria", "ಬ್ಯಾಕ್ಟೀರಿಯಾದಿಂದ ಬಂದ ಸೋಂಕಿಗೆ ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "serious_bacteria": ("to treat serious infections caused by bacteria", "ಬ್ಯಾಕ್ಟೀರಿಯಾದಿಂದ ಬಂದ ಗಂಭೀರ ಸೋಂಕಿಗೆ ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "antibiotic_help": ("to help the antibiotic work better", "ಆಂಟಿಬಯೋಟಿಕ್ (ಪ್ರತಿಜೀವಕ) ಔಷಧಿ ಇನ್ನಷ್ಟು ಚೆನ್ನಾಗಿ ಕೆಲಸ ಮಾಡಲು"),
    "protozoa": ("to treat gut and other infections", "ಕರುಳಿನ ಮತ್ತು ಇತರ ಸೋಂಕುಗಳಿಗೆ ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "fungus": ("to treat fungal infections", "ಶಿಲೀಂಧ್ರ (ಫಂಗಸ್) ಸೋಂಕಿಗೆ ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "worms": ("to treat worm infections", "ಹುಳುಗಳ ಸೋಂಕಿಗೆ ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "ivermectin": ("to treat worm infections and scabies", "ಹುಳುಗಳ ಸೋಂಕು ಮತ್ತು ತುರಿಕೆ ಹುಳು (ಸ್ಕೇಬೀಸ್) ಸೋಂಕಿಗೆ ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "herpes": ("to treat herpes virus infections", "ಹರ್ಪಿಸ್ ವೈರಸ್ ಸೋಂಕಿಗೆ ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "malaria": ("to treat malaria", "ಮಲೇರಿಯಾಕ್ಕೆ ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "scabies": ("to treat scabies and lice", "ತುರಿಕೆ ಹುಳು (ಸ್ಕೇಬೀಸ್) ಮತ್ತು ಹೇನಿಗೆ ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "skin_bacteria": ("to treat bacterial skin infections", "ಚರ್ಮದ ಬ್ಯಾಕ್ಟೀರಿಯಾ ಸೋಂಕಿಗೆ ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "allergy": ("to ease allergy symptoms such as sneezing, a runny nose and itching", "ಅಲರ್ಜಿಯ ಲಕ್ಷಣಗಳಾದ ಸೀನು, ಮೂಗು ಸೋರುವುದು ಮತ್ತು ತುರಿಕೆಯನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "cold": ("to ease cold and allergy symptoms", "ಶೀತ ಮತ್ತು ಅಲರ್ಜಿಯ ಲಕ್ಷಣಗಳನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "blocked_nose": ("to ease a blocked nose", "ಮೂಗು ಕಟ್ಟಿರುವುದನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "asthma_allergy": ("to control asthma and allergy", "ಅಸ್ತಮಾ ಮತ್ತು ಅಲರ್ಜಿಯನ್ನು ನಿಯಂತ್ರಿಸಲು"),
    "phlegm": ("to ease cough with phlegm and breathing trouble", "ಕಫ ಸಹಿತ ಕೆಮ್ಮು ಮತ್ತು ಉಸಿರಾಟದ ತೊಂದರೆಯನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "thin_phlegm": ("to thin the phlegm and ease cough", "ಕಫವನ್ನು ತಿಳಿಗೊಳಿಸಿ ಕೆಮ್ಮನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "breathing": ("to ease breathing trouble from asthma", "ಅಸ್ತಮಾದಿಂದ ಬರುವ ಉಸಿರಾಟದ ತೊಂದರೆಯನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "bp": ("to lower blood pressure", "ರಕ್ತದೊತ್ತಡವನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "bp_heart": ("to control blood pressure and some heart problems", "ರಕ್ತದೊತ್ತಡ ಮತ್ತು ಹೃದಯದ ಕೆಲವು ತೊಂದರೆಗಳನ್ನು ನಿಯಂತ್ರಿಸಲು"),
    "water": ("to remove extra water from the body through urine", "ದೇಹದಲ್ಲಿರುವ ಹೆಚ್ಚುವರಿ ನೀರನ್ನು ಮೂತ್ರದ ಮೂಲಕ ಹೊರಹಾಕಲು"),
    "cholesterol": ("to lower cholesterol", "ಕೊಲೆಸ್ಟ್ರಾಲ್ ಕಡಿಮೆ ಮಾಡಲು"),
    "clots": ("to prevent blood clots", "ರಕ್ತ ಹೆಪ್ಪುಗಟ್ಟುವುದನ್ನು ತಡೆಯಲು"),
    "chest_pain": ("to ease chest pain from the heart", "ಹೃದಯದಿಂದ ಬರುವ ಎದೆನೋವನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "erection": ("to treat erection problems", "ಪುರುಷರಲ್ಲಿ ನಿಮಿರುವಿಕೆಯ ತೊಂದರೆಗೆ ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "erection_prostate": ("to treat erection problems or an enlarged prostate", "ಪುರುಷರಲ್ಲಿ ನಿಮಿರುವಿಕೆಯ ತೊಂದರೆ ಅಥವಾ ಪ್ರಾಸ್ಟೇಟ್ ಗ್ರಂಥಿಯ ಹಿಗ್ಗುವಿಕೆಗೆ ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "prostate": ("to help urine flow in an enlarged prostate", "ಪ್ರಾಸ್ಟೇಟ್ ಹಿಗ್ಗಿದಾಗ ಮೂತ್ರ ಸರಾಗವಾಗಿ ಹೋಗಲು ಸಹಾಯ ಮಾಡಲು"),
    "blood_flow": ("to improve blood flow", "ರಕ್ತ ಸಂಚಾರವನ್ನು ಸುಧಾರಿಸಲು"),
    "sugar": ("to control blood sugar in diabetes", "ಮಧುಮೇಹದಲ್ಲಿ (ಶುಗರ್ ಕಾಯಿಲೆಯಲ್ಲಿ) ರಕ್ತದ ಸಕ್ಕರೆ ಪ್ರಮಾಣವನ್ನು ನಿಯಂತ್ರಿಸಲು"),
    "thyroid": ("to replace thyroid hormone when the thyroid is underactive", "ಥೈರಾಯ್ಡ್ ಕಡಿಮೆ ಕೆಲಸ ಮಾಡುವಾಗ ಥೈರಾಯ್ಡ್ ಹಾರ್ಮೋನ್ ಕೊರತೆಯನ್ನು ಸರಿಪಡಿಸಲು"),
    "anxiety_fits": ("to treat anxiety or fits", "ಆತಂಕ ಅಥವಾ ಅಪಸ್ಮಾರಕ್ಕೆ (ಫಿಟ್ಸ್) ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "anxiety_sleep": ("to treat anxiety or trouble sleeping", "ಆತಂಕ ಅಥವಾ ನಿದ್ರೆಯ ತೊಂದರೆಗೆ ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "sleep": ("to treat trouble sleeping", "ನಿದ್ರೆಯ ತೊಂದರೆಗೆ ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "depression": ("to treat low mood and anxiety", "ಖಿನ್ನತೆ ಮತ್ತು ಆತಂಕಕ್ಕೆ ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "depression_nerve": ("to treat low mood or nerve pain", "ಖಿನ್ನತೆ ಅಥವಾ ನರ ನೋವಿಗೆ ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "psych": ("to treat mental health conditions", "ಮಾನಸಿಕ ಆರೋಗ್ಯದ ತೊಂದರೆಗಳಿಗೆ ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "fits": ("to control fits (seizures)", "ಅಪಸ್ಮಾರವನ್ನು (ಫಿಟ್ಸ್) ನಿಯಂತ್ರಿಸಲು"),
    "fits_migraine": ("to control fits or prevent migraine", "ಅಪಸ್ಮಾರವನ್ನು ನಿಯಂತ್ರಿಸಲು ಅಥವಾ ಮೈಗ್ರೇನ್ ತಡೆಯಲು"),
    "nerve_pain": ("to ease nerve pain", "ನರ ನೋವನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "brain": ("to support brain function", "ಮೆದುಳಿನ ಕಾರ್ಯವನ್ನು ಬೆಂಬಲಿಸಲು"),
    "vertigo": ("to ease dizziness and spinning (vertigo)", "ತಲೆತಿರುಗುವಿಕೆಯನ್ನು (ವರ್ಟಿಗೋ) ಕಡಿಮೆ ಮಾಡಲು"),
    "vertigo_migraine": ("to ease dizziness and prevent migraine headaches", "ತಲೆತಿರುಗುವಿಕೆಯನ್ನು ಕಡಿಮೆ ಮಾಡಲು ಮತ್ತು ಮೈಗ್ರೇನ್ ತಲೆನೋವನ್ನು ತಡೆಯಲು"),
    "muscle_spasm": ("to ease muscle stiffness and spasm", "ಸ್ನಾಯು ಬಿಗಿತ ಮತ್ತು ಸೆಳೆತವನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "muscle_pain": ("to ease muscle spasm and pain", "ಸ್ನಾಯು ಸೆಳೆತ ಮತ್ತು ನೋವನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "b12": ("to correct vitamin B12 lack and support the nerves", "ವಿಟಮಿನ್ ಬಿ12 ಕೊರತೆಯನ್ನು ಸರಿಪಡಿಸಲು ಮತ್ತು ನರಗಳನ್ನು ಬಲಪಡಿಸಲು"),
    "steroid": ("to reduce inflammation and allergy", "ಉರಿಯೂತ ಮತ್ತು ಅಲರ್ಜಿಯನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "skin_steroid": ("to reduce skin inflammation and itching", "ಚರ್ಮದ ಉರಿಯೂತ ಮತ್ತು ತುರಿಕೆಯನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "progesterone": ("to give the hormone progesterone for period problems or to support a pregnancy",
                     "ಮುಟ್ಟಿನ ತೊಂದರೆಗಳಿಗೆ ಅಥವಾ ಗರ್ಭಧಾರಣೆಯ ಬೆಂಬಲಕ್ಕೆ ಪ್ರೊಜೆಸ್ಟರಾನ್ ಹಾರ್ಮೋನ್ ನೀಡಲು"),
    "periods": ("to treat period problems", "ಮುಟ್ಟಿನ ತೊಂದರೆಗಳಿಗೆ ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "letrozole": ("to treat some breast cancers or help with fertility", "ಕೆಲವು ರೀತಿಯ ಸ್ತನ ಕ್ಯಾನ್ಸರ್ ಚಿಕಿತ್ಸೆಗೆ ಅಥವಾ ಗರ್ಭಧಾರಣೆಗೆ (ಫಲವತ್ತತೆಗೆ) ಸಹಾಯ ಮಾಡಲು"),
    "ovulation": ("to help the body release an egg (ovulation)", "ಅಂಡಾಣು ಬಿಡುಗಡೆಗೆ (ಅಂಡೋತ್ಪತ್ತಿಗೆ) ಸಹಾಯ ಮಾಡಲು"),
    "heavy_bleed": ("to reduce heavy bleeding", "ಹೆಚ್ಚಿನ ರಕ್ತಸ್ರಾವವನ್ನು ಕಡಿಮೆ ಮಾಡಲು"),
    "methotrexate": ("to treat joint inflammation, some skin conditions or cancer", "ಕೀಲುಗಳ ಉರಿಯೂತ (ಊತ), ಕೆಲವು ಚರ್ಮರೋಗ ಅಥವಾ ಕ್ಯಾನ್ಸರ್ ಚಿಕಿತ್ಸೆಗಾಗಿ"),
    "anaemia": ("to treat anaemia (low iron)", "ರಕ್ತಹೀನತೆಗೆ (ಕಬ್ಬಿಣದ ಕೊರತೆ) ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "anaemia_kidney": ("to treat anaemia (low blood count)", "ರಕ್ತಹೀನತೆಗೆ (ಹಿಮೋಗ್ಲೋಬಿನ್ / ಕೆಂಪು ರಕ್ತಕಣಗಳ ಕೊರತೆಗೆ) ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
    "vit_d": ("to strengthen the bones and correct low vitamin D", "ಮೂಳೆಗಳನ್ನು ಬಲಪಡಿಸಲು ಮತ್ತು ವಿಟಮಿನ್ ಡಿ ಕೊರತೆಯನ್ನು ಸರಿಪಡಿಸಲು"),
    "gout": ("to lower uric acid in the blood and prevent gout", "ರಕ್ತದಲ್ಲಿ ಯೂರಿಕ್ ಆಸಿಡ್ (ಯೂರಿಕ್ ಆಮ್ಲ) ಕಡಿಮೆ ಮಾಡಿ ಗೌಟ್ (ಕೀಲು ನೋವು) ತಡೆಯಲು"),
    "acne": ("to treat severe acne", "ತೀವ್ರ ಮೊಡವೆಗೆ ಚಿಕಿತ್ಸೆ ನೀಡಲು"),
}

_ANTIBIOTIC = ("bacteria", ["diarrhoea", "nausea", "stomach_pain"], ["finish", "allergy"])
_CEPH = ("bacteria", ["diarrhoea", "nausea", "stomach_pain"], ["finish", "bad_diarrhoea", "allergy"])
_CEPH_INJ = ("serious_bacteria", ["diarrhoea", "nausea", "stomach_pain"], ["bad_diarrhoea", "allergy"])
_FLUOROQ = ("bacteria", ["nausea", "diarrhoea", "dizzy", "headache"], ["finish", "tendon", "allergy"])
_NSAID = ("pain_swell", ["stomach_pain", "heartburn", "nausea", "dizzy"], ["bleed", "allergy"])
_PPI = ("acid", ["headache", "nausea", "diarrhoea", "stomach_pain"], [])
_ARB = ("bp", ["dizzy", "tired"], ["stand_slowly", "pregnancy", "dont_stop"])
_BETA = ("bp_heart", ["tired", "dizzy", "slow_heart"], ["wheeze", "dont_stop"])
_STATIN = ("cholesterol", ["muscle_pain", "stomach", "headache"], ["muscle", "liver", "pregnancy"])
_ANTIHIST = ("allergy", ["drowsy", "dry_mouth", "headache"], ["no_driving"])
_NONSEDATING = ("allergy", ["headache", "dry_mouth", "tired"], [])
_ANTIFUNGAL_ORAL = ("fungus", ["nausea", "stomach_pain", "headache"], ["liver", "allergy"])
_ANTIFUNGAL_SKIN = ("fungus", ["skin_irritation"], [])
_SSRI = ("depression", ["nausea", "sleep_trouble", "headache", "dry_mouth"], ["slow_to_work", "self_harm", "dont_stop"])
_BENZO = ("anxiety_sleep", ["drowsy", "dizzy", "weak"], ["no_alcohol", "no_driving", "dependency", "dont_stop"])
_ANTIPSYCH = ("psych", ["drowsy", "weight_gain", "dizzy", "dry_mouth"], ["dont_stop", "blood_test"])
_ANTIEPI = ("fits", ["drowsy", "dizzy", "nausea", "blur"], ["dont_stop", "allergy"])
_STEROID = ("steroid", ["stomach", "appetite_up", "sleep_trouble", "mood"], ["dont_stop", "infection"])
_SKIN_STEROID = ("skin_steroid", ["skin_irritation"], ["skin_only"])
_SUGAR_SU = ("sugar", ["weight_gain", "nausea"], ["low_sugar"])

# key: the ingredient name as the brand table spells it -> (purpose key, side-effect keys, warning keys)
MEDS: dict[str, tuple[str, list[str], list[str]]] = {
    "paracetamol": ("fever_pain", [], ["no_extra_paracetamol", "liver"]),
    "ibuprofen": ("pain_swell_fever", ["stomach_pain", "heartburn", "nausea"], ["bleed"]),
    "diclofenac": _NSAID, "aceclofenac": _NSAID, "piroxicam": _NSAID, "lornoxicam": _NSAID,
    "etoricoxib": ("pain_swell", ["heartburn", "stomach_pain", "dizzy", "ankle_swelling"], ["bleed", "allergy"]),
    "nimesulide": ("pain_fever", ["stomach_pain", "nausea"], ["liver", "allergy"]),
    "mefenamic acid": ("pain", ["stomach_pain", "nausea", "diarrhoea"], ["bleed", "allergy"]),
    "tramadol": ("strong_pain", ["nausea", "dizzy", "drowsy", "constipation"], ["no_alcohol", "no_driving", "dependency"]),
    "tapentadol": ("strong_pain", ["nausea", "dizzy", "drowsy", "constipation"], ["no_alcohol", "no_driving", "dependency"]),
    "serratiopeptidase": ("pain_swell", ["stomach"], ["allergy"]),
    "thiocolchicoside": ("muscle_pain", ["drowsy", "stomach_pain", "diarrhoea"], []),
    "chlorzoxazone": ("muscle_pain", ["drowsy", "dizzy", "stomach"], ["liver"]),
    "pantoprazole": _PPI, "omeprazole": _PPI, "esomeprazole": _PPI, "rabeprazole": _PPI, "lansoprazole": _PPI, "ranitidine": _PPI,
    "domperidone": ("vomit", ["dry_mouth", "stomach_pain", "headache"], ["heart_rhythm"]),
    "ondansetron": ("vomit", ["headache", "constipation", "dizzy", "tired"], ["heart_rhythm"]),
    "sucralfate": ("ulcer", ["constipation", "nausea"], []),
    "lactulose": ("constipation", ["bloating", "diarrhoea"], []),
    "drotaverine": ("cramp_pain", ["dizzy", "nausea", "fast_heart"], []),
    "ursodeoxycholic acid": ("liver_gall", ["diarrhoea", "stomach_pain"], []),
    "rifaximin": ("gut_infection", ["nausea", "headache", "stomach_pain"], []),
    "levosulpiride": ("nausea_digest", ["drowsy", "dizzy"], ["no_driving"]),
    "amoxicillin": _ANTIBIOTIC, "ampicillin": _ANTIBIOTIC,
    "clavulanic acid": ("antibiotic_help", ["diarrhoea", "nausea"], ["bad_diarrhoea"]),
    "sulbactam": ("antibiotic_help", ["diarrhoea", "nausea"], ["bad_diarrhoea"]),
    "azithromycin": ("bacteria", ["nausea", "diarrhoea", "stomach_pain"], ["finish", "allergy", "heart_rhythm"]),
    "clarithromycin": ("bacteria", ["nausea", "diarrhoea", "metallic"], ["finish", "allergy", "heart_rhythm"]),
    "roxithromycin": _ANTIBIOTIC,
    "cefixime": _CEPH, "cefpodoxime": _CEPH, "cefuroxime": _CEPH, "cefalexin": _CEPH, "cefadroxil": _CEPH,
    "ceftriaxone": _CEPH_INJ, "cefotaxime": _CEPH_INJ, "cefepime": _CEPH_INJ, "ceftazidime": _CEPH_INJ,
    "ofloxacin": _FLUOROQ, "levofloxacin": _FLUOROQ, "ciprofloxacin": _FLUOROQ,
    "doxycycline": ("bacteria", ["nausea", "stomach", "sun"], ["finish", "allergy"]),
    "linezolid": ("serious_bacteria", ["diarrhoea", "nausea", "headache"], ["finish", "bad_diarrhoea"]),
    "clindamycin": ("bacteria", ["nausea", "stomach_pain"], ["finish", "bad_diarrhoea", "allergy"]),
    "metronidazole": ("protozoa", ["metallic", "nausea", "headache"], ["no_alcohol"]),
    "ornidazole": ("protozoa", ["metallic", "nausea", "headache", "dizzy"], ["no_alcohol"]),
    "tinidazole": ("protozoa", ["metallic", "nausea", "headache"], ["no_alcohol"]),
    "amikacin": ("serious_bacteria", [], ["ear_kidney", "allergy"]),
    "meropenem": ("serious_bacteria", ["diarrhoea", "nausea", "headache"], ["bad_diarrhoea", "allergy"]),
    "fluconazole": _ANTIFUNGAL_ORAL, "itraconazole": _ANTIFUNGAL_ORAL, "terbinafine": _ANTIFUNGAL_ORAL, "ketoconazole": _ANTIFUNGAL_ORAL,
    "luliconazole": _ANTIFUNGAL_SKIN, "clotrimazole": _ANTIFUNGAL_SKIN,
    "albendazole": ("worms", ["stomach_pain", "nausea", "headache"], []),
    "ivermectin": ("ivermectin", ["dizzy", "nausea"], ["allergy"]),
    "acyclovir": ("herpes", ["nausea", "headache"], ["water"]),
    "artesunate": ("malaria", ["dizzy", "nausea"], ["finish"]),
    "quinine": ("malaria", ["nausea", "dizzy", "headache"], ["finish", "low_sugar"]),
    "permethrin": ("scabies", ["skin_irritation"], []),
    "mupirocin": ("skin_bacteria", ["skin_irritation"], []),
    "cetirizine": _ANTIHIST, "levocetirizine": _ANTIHIST, "hydroxyzine": _ANTIHIST,
    "cyproheptadine": ("allergy", ["drowsy", "dry_mouth", "appetite_up"], ["no_driving"]),
    "fexofenadine": _NONSEDATING, "loratadine": _NONSEDATING,
    "chlorpheniramine": ("cold", ["drowsy", "dry_mouth"], ["no_driving"]),
    "phenylephrine": ("blocked_nose", ["headache", "fast_heart", "sleep_trouble"], []),
    "montelukast": ("asthma_allergy", ["headache", "stomach_pain"], ["mood"]),
    "acebrophylline": ("phlegm", ["nausea", "stomach"], []),
    "doxofylline": ("breathing", ["nausea", "headache", "fast_heart", "sleep_trouble"], []),
    "ambroxol": ("thin_phlegm", ["nausea", "stomach"], ["allergy"]),
    "guaifenesin": ("thin_phlegm", ["nausea", "stomach"], []),
    "levosalbutamol": ("breathing", ["tremor", "fast_heart", "headache"], []),
    "amlodipine": ("bp", ["ankle_swelling", "flushing", "headache", "dizzy", "tired"], ["dont_stop"]),
    "cilnidipine": ("bp", ["ankle_swelling", "flushing", "headache", "dizzy"], ["dont_stop"]),
    "telmisartan": _ARB, "losartan": _ARB, "olmesartan": _ARB,
    "ramipril": ("bp", ["dry_cough", "dizzy", "tired"], ["stand_slowly", "pregnancy", "allergy", "dont_stop"]),
    "enalapril": ("bp", ["dry_cough", "dizzy", "tired"], ["stand_slowly", "pregnancy", "allergy", "dont_stop"]),
    "metoprolol": _BETA, "atenolol": _BETA, "propranolol": _BETA, "nebivolol": _BETA, "carvedilol": _BETA, "bisoprolol": _BETA,
    "diltiazem": ("bp_heart", ["headache", "dizzy", "ankle_swelling", "slow_heart"], ["dont_stop"]),
    "torasemide": ("water", ["frequent_urine", "dizzy", "cramps"], []),
    "atorvastatin": _STATIN, "rosuvastatin": _STATIN,
    "clopidogrel": ("clots", ["stomach_pain", "heartburn"], ["bleed", "dont_stop", "ask_new"]),
    "aspirin": ("clots", ["heartburn", "stomach"], ["bleed", "ask_new"]),
    "warfarin": ("clots", [], ["bleed", "blood_test", "ask_new", "dont_stop"]),
    "rivaroxaban": ("clots", [], ["bleed", "dont_stop", "ask_new"]),
    "enoxaparin": ("clots", [], ["bleed"]),
    "nitroglycerin": ("chest_pain", ["headache", "dizzy", "flushing"], ["stand_slowly", "no_pde5"]),
    "sildenafil": ("erection", ["headache", "flushing", "heartburn", "dizzy"], ["nitrate"]),
    "tadalafil": ("erection_prostate", ["headache", "flushing", "heartburn", "muscle_pain"], ["nitrate"]),
    "tamsulosin": ("prostate", ["dizzy"], ["stand_slowly"]),
    "isoxsuprine": ("blood_flow", ["dizzy", "fast_heart", "nausea"], []),
    "metformin": ("sugar", ["nausea", "diarrhoea", "stomach_pain", "metallic", "appetite"], ["sick"]),
    "glimepiride": _SUGAR_SU, "gliclazide": _SUGAR_SU,
    "voglibose": ("sugar", ["bloating", "diarrhoea"], []),
    "teneligliptin": ("sugar", ["headache", "nausea", "stomach_pain"], []),
    "vildagliptin": ("sugar", ["headache", "dizzy", "nausea"], ["liver"]),
    "dapagliflozin": ("sugar", ["frequent_urine", "genital_itch"], ["sick", "water"]),
    "pioglitazone": ("sugar", ["weight_gain", "ankle_swelling"], ["breath"]),
    "thyroxine": ("thyroid", ["fast_heart", "tremor", "sleep_trouble"], ["dont_stop", "thyroid_test"]),
    "clonazepam": ("anxiety_fits", ["drowsy", "dizzy", "weak"], ["no_alcohol", "no_driving", "dependency", "dont_stop"]),
    "clobazam": ("anxiety_fits", ["drowsy", "dizzy", "weak"], ["no_alcohol", "no_driving", "dependency", "dont_stop"]),
    "alprazolam": _BENZO, "lorazepam": _BENZO, "etizolam": _BENZO,
    "zolpidem": ("sleep", ["drowsy", "dizzy", "headache"], ["no_alcohol", "no_driving", "dependency"]),
    "escitalopram": _SSRI, "sertraline": _SSRI, "paroxetine": _SSRI, "fluoxetine": _SSRI, "mirtazapine": ("depression", ["drowsy", "appetite_up", "weight_gain", "dry_mouth"], ["slow_to_work", "self_harm", "dont_stop"]),
    "amitriptyline": ("depression_nerve", ["drowsy", "dry_mouth", "constipation", "dizzy"], ["slow_to_work", "self_harm", "dont_stop"]),
    "dosulepin": ("depression", ["drowsy", "dry_mouth", "constipation", "dizzy"], ["slow_to_work", "self_harm", "dont_stop"]),
    "duloxetine": ("depression_nerve", ["nausea", "dry_mouth", "drowsy", "headache"], ["slow_to_work", "self_harm", "dont_stop"]),
    "olanzapine": _ANTIPSYCH, "quetiapine": _ANTIPSYCH, "risperidone": _ANTIPSYCH, "aripiprazole": _ANTIPSYCH,
    "clozapine": _ANTIPSYCH, "amisulpride": _ANTIPSYCH,
    "haloperidol": ("psych", ["drowsy", "dry_mouth", "tremor"], ["dont_stop", "heart_rhythm"]),
    "levetiracetam": _ANTIEPI, "carbamazepine": _ANTIEPI, "oxcarbazepine": _ANTIEPI, "lamotrigine": _ANTIEPI,
    "valproate": ("fits", ["nausea", "drowsy", "weight_gain", "tremor"], ["dont_stop", "liver", "no_pregnancy"]),
    "divalproex": ("fits", ["nausea", "drowsy", "weight_gain", "tremor"], ["dont_stop", "liver", "no_pregnancy"]),
    "topiramate": ("fits_migraine", ["drowsy", "dizzy", "appetite", "nausea"], ["dont_stop", "water"]),
    "gabapentin": ("nerve_pain", ["drowsy", "dizzy", "weight_gain", "ankle_swelling"], ["no_driving", "dont_stop"]),
    "pregabalin": ("nerve_pain", ["drowsy", "dizzy", "weight_gain", "ankle_swelling"], ["no_driving", "dont_stop"]),
    "piracetam": ("brain", ["headache", "nausea", "sleep_trouble"], []),
    "citicoline": ("brain", ["headache", "nausea", "sleep_trouble"], []),
    "betahistine": ("vertigo", ["nausea", "headache", "stomach"], []),
    "flunarizine": ("vertigo_migraine", ["drowsy", "weight_gain", "tired"], ["mood", "no_driving"]),
    "cinnarizine": ("vertigo_migraine", ["drowsy", "weight_gain", "dry_mouth"], ["no_driving"]),
    "baclofen": ("muscle_spasm", ["drowsy", "dizzy", "weak"], ["no_driving", "dont_stop"]),
    "methylcobalamin": ("b12", ["nausea", "diarrhoea"], []),
    "prednisolone": _STEROID, "methylprednisolone": _STEROID, "deflazacort": _STEROID,
    "hydrocortisone": _SKIN_STEROID, "clobetasol": _SKIN_STEROID, "mometasone": _SKIN_STEROID,
    "progesterone": ("progesterone", ["drowsy", "dizzy", "nausea", "headache"], ["clots"]),
    "progesterone natural micronized": ("progesterone", ["drowsy", "dizzy", "nausea", "headache"], ["clots"]),
    "hydroxyprogesterone": ("progesterone", ["nausea", "headache"], ["clots"]),
    "norethisterone": ("periods", ["nausea", "headache", "weight_gain"], ["clots"]),
    "letrozole": ("letrozole", ["hot_flush", "joint_pain", "tired", "headache"], ["pregnancy"]),
    "clomiphene": ("ovulation", ["hot_flush", "headache", "stomach_pain", "blur"], ["pregnancy"]),
    "tranexamic acid": ("heavy_bleed", ["nausea", "diarrhoea", "headache"], ["clots"]),
    "ethamsylate": ("heavy_bleed", ["nausea", "headache", "stomach"], []),
    "methotrexate": ("methotrexate", ["nausea", "mouth_ulcer", "tired"], ["once_weekly", "liver", "no_pregnancy", "infection"]),
    "iron sucrose": ("anaemia", [], ["supervised", "allergy"]),
    "recombinant human erythropoietin alfa": ("anaemia_kidney", ["headache"], ["supervised"]),
    "vitamin d": ("vit_d", [], ["overdose_vit"]),
    "allopurinol": ("gout", ["nausea", "stomach"], ["allergy", "water"]),
    "febuxostat": ("gout", ["nausea", "joint_pain"], ["liver", "allergy"]),
    "isotretinoin": ("acne", ["dry_skin", "headache", "joint_pain"], ["no_pregnancy", "mood", "liver"]),
}

# Added after the 28 Oct 2026 second-opinion review of this table by an LLM (NOT a clinician or a native speaker): every addition reuses a warning that is already
# in WARN and already translated, so no new Kannada text was introduced. Clinical judgement applied on top: no 'never in pregnancy' for statins (guidance relaxed),
# letrozole or clomiphene (used to conceive); no 'low sugar' for teneligliptin (rarely causes it alone). A pharmacist or doctor still needs to check the whole table.
REVIEW_ADDITIONS = {
    "acebrophylline": ['heart_rhythm'],
    "aceclofenac": ['pregnancy'],
    "albendazole": ['liver', 'pregnancy'],
    "allopurinol": ['liver'],
    "alprazolam": ['pregnancy'],
    "amikacin": ['pregnancy', 'supervised'],
    "amisulpride": ['no_driving', 'heart_rhythm'],
    "amitriptyline": ['no_alcohol', 'no_driving', 'heart_rhythm'],
    "amlodipine": ['stand_slowly'],
    "aripiprazole": ['no_driving'],
    "artesunate": ['liver'],
    "aspirin": ['dont_stop'],
    "atenolol": ['heart_rhythm'],
    "baclofen": ['no_alcohol'],
    "bisoprolol": ['heart_rhythm'],
    "carbamazepine": ['no_driving', 'pregnancy', 'infection'],
    "carvedilol": ['stand_slowly'],
    "cefepime": ['supervised'],
    "cefotaxime": ['supervised'],
    "ceftazidime": ['supervised'],
    "ceftriaxone": ['finish', 'supervised'],
    "chlorzoxazone": ['no_alcohol', 'no_driving'],
    "cilnidipine": ['stand_slowly'],
    "ciprofloxacin": ['bad_diarrhoea'],
    "clavulanic acid": ['allergy', 'liver'],
    "clobazam": ['pregnancy'],
    "clonazepam": ['pregnancy'],
    "clozapine": ['no_driving', 'heart_rhythm', 'breath', 'infection'],
    "deflazacort": ['bleed'],
    "diclofenac": ['pregnancy'],
    "diltiazem": ['heart_rhythm', 'breath'],
    "divalproex": ['no_driving'],
    "dosulepin": ['no_alcohol', 'no_driving', 'heart_rhythm'],
    "doxofylline": ['heart_rhythm'],
    "doxycycline": ['pregnancy', 'water'],
    "duloxetine": ['no_driving', 'liver'],
    "enalapril": ['no_pregnancy'],
    "enoxaparin": ['supervised'],
    "etizolam": ['pregnancy'],
    "etoricoxib": ['pregnancy'],
    "fluconazole": ['pregnancy'],
    "gabapentin": ['no_alcohol', 'self_harm'],
    "haloperidol": ['no_alcohol', 'no_driving'],
    "ibuprofen": ['allergy', 'pregnancy'],
    "isoxsuprine": ['stand_slowly'],
    "itraconazole": ['pregnancy', 'breath'],
    "lamotrigine": ['no_driving'],
    "levetiracetam": ['no_driving', 'self_harm', 'mood'],
    "levofloxacin": ['bad_diarrhoea'],
    "levosalbutamol": ['wheeze'],
    "levosulpiride": ['heart_rhythm'],
    "lorazepam": ['pregnancy'],
    "lornoxicam": ['pregnancy'],
    "losartan": ['no_pregnancy'],
    "mefenamic acid": ['pregnancy'],
    "meropenem": ['supervised'],
    "metformin": ['no_alcohol'],
    "methotrexate": ['bleed', 'no_alcohol', 'breath'],
    "methylprednisolone": ['bleed'],
    "metoprolol": ['heart_rhythm'],
    "metronidazole": ['finish'],
    "mirtazapine": ['no_alcohol', 'no_driving'],
    "nebivolol": ['heart_rhythm'],
    "nimesulide": ['bleed'],
    "ofloxacin": ['bad_diarrhoea'],
    "olanzapine": ['no_alcohol', 'no_driving', 'stand_slowly'],
    "olmesartan": ['no_pregnancy'],
    "ornidazole": ['finish'],
    "oxcarbazepine": ['no_driving', 'pregnancy'],
    "pantoprazole": ['bad_diarrhoea'],
    "pioglitazone": ['liver'],
    "piroxicam": ['pregnancy'],
    "prednisolone": ['bleed'],
    "pregabalin": ['no_alcohol', 'dependency'],
    "progesterone": ['no_driving'],
    "progesterone natural micronized": ['no_driving'],
    "quetiapine": ['no_alcohol', 'no_driving', 'stand_slowly'],
    "quinine": ['heart_rhythm', 'ear_kidney'],
    "ramipril": ['no_pregnancy'],
    "recombinant human erythropoietin alfa": ['clots'],
    "risperidone": ['no_alcohol', 'no_driving', 'stand_slowly'],
    "rivaroxaban": ['pregnancy'],
    "sildenafil": ['stand_slowly'],
    "sulbactam": ['allergy'],
    "telmisartan": ['no_pregnancy'],
    "thiocolchicoside": ['no_driving', 'no_pregnancy'],
    "thyroxine": ['heart_rhythm'],
    "tinidazole": ['finish'],
    "topiramate": ['no_driving', 'pregnancy'],
    "torasemide": ['stand_slowly', 'blood_test'],
    "ursodeoxycholic acid": ['liver'],
    "valproate": ['no_driving'],
    "warfarin": ['no_pregnancy'],
}
SOFT_PREGNANCY_REPLACED = ['enalapril', 'losartan', 'olmesartan', 'ramipril', 'telmisartan']      # these already said 'tell your doctor if pregnant'; the stronger sentence replaces it
for _name, _extra in REVIEW_ADDITIONS.items():
    _pk, _se, _wn = MEDS[_name]
    _wn = [w for w in _wn if not (w == "pregnancy" and _name in SOFT_PREGNANCY_REPLACED)]
    MEDS[_name] = (_pk, _se, _wn + [w for w in _extra if w not in _wn])

# A third pass: a stronger model reviewed the 54 entries two other models had flagged and suggested sentences a patient could act on. Only the ones that
# reuse an existing (already translated) warning are applied here; the rest would be new unreviewed text. LLM review only, no clinician.
SECOND_OPINION_ADDITIONS = {
    **{n: ['allergy'] for n in ("acebrophylline", "aspirin", "gabapentin", "pregabalin")},
    **{n: ['no_alcohol'] for n in ("amisulpride", "aripiprazole", "carbamazepine", "cinnarizine", "clozapine", "cyproheptadine", "ketoconazole",
                                    "levosulpiride", "nimesulide")},
    "amlodipine": ['pregnancy'], "norethisterone": ['no_pregnancy'], "enalapril": ['blood_test'], "ramipril": ['blood_test'], "pregabalin": ['allergy', 'self_harm'],
}
for _name, _extra in SECOND_OPINION_ADDITIONS.items():
    _pk, _se, _wn = MEDS[_name]
    MEDS[_name] = (_pk, _se, _wn + [w for w in _extra if w not in _wn])

# spellings a prescription or brand table may use for the same ingredient
ALIASES = {"levothyroxine": "thyroxine", "thyroxine sodium": "thyroxine", "cholecalciferol": "vitamin d", "acetaminophen": "paracetamol",
           "amoxycillin": "amoxicillin", "cephalexin": "cefalexin", "clavulanate": "clavulanic acid", "potassium clavulanate": "clavulanic acid",
           "amoxicillin clavulanate": "amoxicillin+clavulanic acid", "rabeprazole sodium": "rabeprazole", "pantoprazole sodium": "pantoprazole",
           "sodium valproate": "valproate", "levosalbutamol sulphate": "levosalbutamol", "glimepride": "glimepiride"}

# combinations whose two purposes say the same thing: one purpose phrase instead of two
COMBO_PURPOSE = {frozenset(k): v for k, v in {
    ("ibuprofen", "paracetamol"): "pain_swell_fever", ("aceclofenac", "paracetamol"): "pain_fever", ("diclofenac", "paracetamol"): "pain_fever",
    ("nimesulide", "paracetamol"): "pain_fever", ("mefenamic acid", "paracetamol"): "pain_fever", ("chlorpheniramine", "paracetamol"): "cold",
    ("aceclofenac", "thiocolchicoside"): "muscle_pain", ("chlorzoxazone", "diclofenac"): "muscle_pain",
    ("ambroxol", "guaifenesin"): "thin_phlegm", ("ambroxol", "levosalbutamol"): "phlegm",
}.items()}

ORDER = ["allergy", "bleed", "self_harm", "clots", "no_pde5", "nitrate", "no_pregnancy", "once_weekly", "ear_kidney", "heart_rhythm", "low_sugar",
         "liver", "tendon", "bad_diarrhoea", "wheeze", "breath", "muscle", "infection", "mood", "sick", "pregnancy", "blood_test", "thyroid_test",
         "supervised", "no_alcohol", "no_driving", "dependency", "no_extra_paracetamol", "ask_new", "skin_only", "stand_slowly", "water",
         "overdose_vit", "slow_to_work", "finish", "dont_stop"]


def _clean(token: str) -> str:
    token = re.sub(r"\d[\d.,]*\s*(mg|mcg|g|gm|ml|iu|%)?", "", token.lower())
    token = re.sub(r"\b(tablets?|tab|capsules?|cap|injection|inj|syrup|ip|bp|usp)\b", "", token)
    token = re.sub(r"[^a-z ]", " ", token)
    return re.sub(r"\s+", " ", token).strip()


def parts_of(generic: str | None) -> list[str]:
    """'Ibuprofen + Paracetamol' / 'amoxicillin:500mg;clavulanic acid:125mg' -> ['ibuprofen', 'paracetamol'] with spelling variants folded in."""
    if not generic:
        return []
    whole = ALIASES.get(_clean(generic))
    if whole:
        generic = whole
    out = []
    for piece in re.split(r"[+;,/&]| and | with ", generic.lower()):
        piece = _clean(piece.split(":")[0])
        if piece:
            out.append(ALIASES.get(piece, piece))
    return out


def printed_actives(raw: str | None) -> int:
    """How many strengths the prescription line prints for one product: '75MG/75MG/10MG' is three, '5MG/40' two, '500MG' one."""
    best = 0
    for m in re.finditer(r"\d+(?:\.\d+)?\s*(?:mg|mcg|g|iu)?(?:\s*/\s*\d+(?:\.\d+)?\s*(?:mg|mcg|g|iu)?)*", raw or "", re.I):
        best = max(best, len(re.findall(r"\d+(?:\.\d+)?", m.group(0))) if "/" in m.group(0) else 0)
    return best


def _parts_for(med) -> list[str]:
    parts = parts_of(getattr(med, "generic", None))
    if parts and all(p in MEDS for p in parts):
        return parts
    try:                                   # the brand table knows the ingredients of a brand the reader did not resolve
        from . import brand_table
        forms = ["liquid"] if re.search(r"\b(syp|syrup|susp|suspension)\b", str(med.name).lower()) else ["tablet", "capsule"]   # a prescription says TAB even for a capsule
        strength = re.search(r"\d+(?:\.\d+)?", str(getattr(med, "strength", "") or ""))
        names = [med.name] + ([f"{med.name} {strength.group(0)}"] if strength else [])        # the table keys some brands with their strength: 'veltam 0.4'
        for form, name in ((f, n) for f in forms for n in names):
            hit = brand_table.lookup(name, form)
            found = parts_of(hit.salts) if hit else []
            if found and printed_actives(getattr(med, "raw", "")) > len(found):
                return []                  # the line prints more strengths than the table has ingredients: the table dropped one, so describe nothing rather than part of a product
            if found and all(p in MEDS for p in found):
                return found
    except Exception:
        pass
    return []


def info(med, lang: str) -> tuple[str, str] | None:
    """(purpose, watch-for) in `lang` ('en' or 'kn') for a prescribed medicine, or None when any ingredient is not in the table."""
    parts = _parts_for(med)
    if not parts or lang not in ("en", "kn"):
        return None
    i = 0 if lang == "en" else 1
    purposes, sides, warns = [], [], []
    for p in dict.fromkeys(parts):
        pk, se, wn = MEDS[p]
        if pk not in purposes:
            purposes.append(pk)
        sides += [s for s in se if s not in sides]
        warns += [w for w in wn if w not in warns]
    combo = COMBO_PURPOSE.get(frozenset(parts))
    if combo:
        purposes = [combo]
    purpose = PURPOSE[lang].format(p=PURPOSE_JOIN[lang].join(_P[k][i] for k in purposes))
    watch = []
    if sides:
        watch.append(SIDE_SENTENCE[lang].format(x=LIST_JOIN[lang].join(SIDE[s][i] for s in sides)))
    watch += [WARN[w][i] for w in sorted(warns, key=ORDER.index)]
    return purpose, " ".join(watch) or WARN["ask_new"][i]
