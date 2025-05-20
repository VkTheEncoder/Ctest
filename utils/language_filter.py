import re
import fasttext
from langdetect import detect_langs
from langdetect.lang_detect_exception import LangDetectException

model = fasttext.load_model('lid.176.bin')


def clean_subtitle_text(text):
    text = re.sub(r'[|\\/{}<>*_~]', '', text)
    text = re.sub(r'\s+', ' ', text)
    lines = text.split('\n')
    out=[]
    for line in lines:
        if re.match(r'^[\d:,.\s-]+$', line): continue
        if len(line.strip())<=1: continue
        out.append(line.strip())
    return ' '.join(out)


def detect_language_with_confidence(text):
    info = {'primary_lang':'unknown','confidence':0.0,'all_langs':{}}
    try:
        labels, scores = model.predict(text, k=3)
        langs=[l.replace('__label__','') for l in labels]
        info['primary_lang']=langs[0]
        info['confidence']=float(scores[0])
        for l,s in zip(langs,scores): info['all_langs'][l]=float(s)
    except:
        try:
            langs = detect_langs(text)
            if langs:
                info['primary_lang']=langs[0].lang
                info['confidence']=langs[0].prob
                for l in langs: info['all_langs'][l.lang]=l.prob
        except LangDetectException:
            pass
    return info


def filter_english_text(subs, english_only=True):
    out=[]
    for txt, ts, coords in subs:
        clean = clean_subtitle_text(txt)
        if not clean: continue
        lang = detect_language_with_confidence(clean)
        if english_only:
            if lang['primary_lang']=='en' and lang['confidence']>0.7:
                out.append((clean, ts, coords, lang))
        else:
            out.append((clean, ts, coords, lang))
    return out
