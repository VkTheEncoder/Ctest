import re
from langdetect import detect_langs
from langdetect.lang_detect_exception import LangDetectException

def clean_subtitle_text(text):
    text = re.sub(r'[|\\/{}<>*_~]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    lines = text.split('\n')
    return ' '.join(
        line.strip() for line in lines
        if len(line.strip()) > 1 and not re.match(r'^[\d:,. \-]+$', line)
    )

def detect_language_with_confidence(text):
    result = {'primary_lang': 'unknown', 'confidence': 0.0, 'all_langs': {}}
    try:
        langs = detect_langs(text)
        if langs:
            primary = langs[0]
            result['primary_lang'] = primary.lang
            result['confidence'] = primary.prob
            for lp in langs:
                result['all_langs'][lp.lang] = lp.prob
    except LangDetectException:
        pass
    return result

def filter_english_text(subs, english_only=True):
    filtered = []
    for text, ts, coords in subs:
        cleaned = clean_subtitle_text(text)
        if not cleaned:
            continue
        info = detect_language_with_confidence(cleaned)
        if not english_only or (info['primary_lang']=='en' and info['confidence']>0.7):
            filtered.append((cleaned, ts, coords, info))
    return filtered
