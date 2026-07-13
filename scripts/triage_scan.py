#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
triage_scan.py — مُشير الفرز لمِحَكّ القيادة.

يرفع «إشارةً» للعائلة المعرفية من كثافة معجمها في نصّ الوثيقة،
مع تعزيزٍ لأوائل النصّ (بديلٌ رخيصٌ للملخّص/المقدمة).

هذا **إشارةٌ لا حكم**. الحسم النهائيّ بالشجرة القانونية (paradigm-triage.md).
حتميّ، أوفلاين، بلا تبعيّات خارجية. يقرأ .docx (بلا python-docx) و .txt/.md.

الاستعمال:
    python triage_scan.py file.docx [--json out.json]
    python triage_scan.py --self-test
"""

import sys
import os
import re
import json
import zipfile

# ----------------------------------------------------------------------
# تطبيع عربيّ خفيف: إزالة التشكيل وتوحيد الألف والياء، لتحسين المطابقة
_TASHKEEL = re.compile(r'[\u0617-\u061A\u064B-\u0652\u0670\u0640]')

def normalize(text):
    text = _TASHKEEL.sub('', text)
    text = text.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
    text = text.replace('ى', 'ي')
    return text

# ----------------------------------------------------------------------
# معجم الإشارة لكلّ عائلة (مطبَّعٌ مسبقاً عند الاستعمال)
FAMILY_KEYWORDS = {
    "كمّية-وضعية": [
        "متغير", "فرضية", "استبيان", "عينة", "احصاء", "احصائي", "معامل",
        "الانحدار", "ارتباط", "دلاله احصائيه", "توزيع", "المتوسط",
        "انحراف معياري", "p-value", "spss", "قياس", "المقياس",
    ],
    "كيفية-تأويلية": [
        "ظاهراتيه", "نظريه مجذره", "اثنوغرافيا", "دراسه حاله", "مقابله",
        "الترميز", "التشبع", "المشاركين", "المبحوثين", "المعطيات النوعيه",
    ],
    "نصّية-هرمنيوطيقية": [
        "نقد ادبي", "تحليل خطاب", "تاويل", "هرمنيوطيقا", "النص", "الروايه",
        "القصيده", "بنيه سرديه", "الخطاب", "الدلاله", "المدونه", "السيميائيه",
    ],
    "تاريخية": [
        "ارشيف", "وثيقه", "مصدر تاريخي", "حقبه", "تسلسل زمني", "الوقائع",
        "سجلات", "نقد المصادر", "المخطوط", "الحوليات",
    ],
    "مقارنة": [
        "مقارنه", "المقارن", "الموازنه", "حالتان", "نماذج مقارنه",
        "دراسه مقارنه", "المنهج المقارن",
    ],
    "فقهية-قانونية": [
        "الفقه", "الشريعه", "القاعده الاصوليه", "المذهب", "النص القانوني",
        "الماده", "الحكم الشرعي", "الادله", "الترجيح", "الاجتهاد", "المصلحه",
        "الضروره", "الاصول", "التاصيل",
    ],
    "مختلطة": [
        "منهج مختلط", "الدمج", "كمي وكيفي", "mixed methods", "التثليث",
        "المناهج المختلطه",
    ],
}
FAMILY_KEYWORDS_N = {
    fam: [normalize(k.lower()) for k in kws] for fam, kws in FAMILY_KEYWORDS.items()
}

FRONT_CHARS = 1800   # مقدار «أوائل النصّ» المعزَّز (بديل الملخّص/المقدمة)
FRONT_BOOST = 2       # وزن الظهور في أوائل النصّ

# ----------------------------------------------------------------------
def read_docx_text(path):
    """يستخرج النصّ من .docx بلا تبعيّات (فكّ الأرشيف + تجريد الوسوم)."""
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist()
                 if n == 'word/document.xml' or
                 (n.startswith('word/') and n.endswith('.xml') and 'document' in n)]
        if 'word/document.xml' in z.namelist():
            names = ['word/document.xml']
        chunks = []
        for n in names:
            xml = z.read(n).decode('utf-8', errors='ignore')
            # النصّ داخل <w:t ...>...</w:t>
            for m in re.findall(r'<w:t[^>]*>(.*?)</w:t>', xml, flags=re.DOTALL):
                chunks.append(m)
        return ' '.join(chunks)

def read_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == '.docx':
        return read_docx_text(path)
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

# ----------------------------------------------------------------------
def score_text(text):
    text_n = normalize(text.lower())
    front = text_n[:FRONT_CHARS]
    scores = {}
    for fam, kws in FAMILY_KEYWORDS_N.items():
        s = 0
        for kw in kws:
            if not kw:
                continue
            s += text_n.count(kw)
            s += FRONT_BOOST * front.count(kw)   # تعزيز أوائل النصّ
        scores[fam] = s
    return scores

def decide(scores):
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_fam, top = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0
    if top == 0:
        return "ملتبس", "low"
    ratio = top / (second + 0.001)
    if top >= 5 and ratio >= 1.8:
        conf = "high"
    elif top >= 3 and ratio >= 1.3:
        conf = "medium"
    else:
        conf = "low"
    return top_fam, conf

def analyze(path):
    text = read_text(path)
    scores = score_text(text)
    signal, confidence = decide(scores)
    return {
        "signal": signal,
        "confidence": confidence,
        "scores": scores,
        "note": ("إشارةٌ لا حكم؛ تُحسَم العائلة بالشجرة القانونية. "
                 "عند التبس أو تقارب الإشارتين: اسأل المستخدم."),
        "verdict_authority": "references/paradigm-triage.md",
    }

# ----------------------------------------------------------------------
def self_test():
    ok = True
    samples = {
        "فقهية-قانونية": (
            "تتناول هذه الرسالة الحكم الشرعي في فقه الضروره والمصلحه، "
            "وتعتمد على الادله والترجيح بين اقوال المذهب وفق القاعده الاصوليه، "
            "مع التاصيل من النص القانوني والاجتهاد."
        ),
        "كمّية-وضعية": (
            "اعتمدت الدراسه المنهج الكمي عبر استبيان وزّع على عينه، "
            "وحُلّلت البيانات احصائيا بمعامل الانحدار والارتباط ودلاله احصائيه "
            "باستخدام spss لقياس المتغير."
        ),
        "نصّية-هرمنيوطيقية": (
            "يقوم البحث على نقد ادبي وتحليل خطاب النص في الروايه، "
            "معتمداً التاويل الهرمنيوطيقي للدلاله والبنيه السرديه في المدونه."
        ),
    }
    for expected, text in samples.items():
        scores = score_text(text)
        signal, conf = decide(scores)
        status = "OK" if signal == expected else "FAIL"
        if signal != expected:
            ok = False
        print(f"[{status}] متوقَّع={expected} · إشارة={signal} · ثقة={conf} · درجات={scores}")
    print("النتيجة:", "نجح ✅" if ok else "فشل ❌")
    return 0 if ok else 1

# ----------------------------------------------------------------------
def main(argv):
    if "--self-test" in argv:
        return self_test()
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print("الاستعمال: python triage_scan.py file.docx [--json out.json]", file=sys.stderr)
        return 2
    path = args[0]
    if not os.path.exists(path):
        print(f"لا يوجد الملفّ: {path}", file=sys.stderr)
        return 2
    result = analyze(path)
    out = None
    if "--json" in argv:
        i = argv.index("--json")
        if i + 1 < len(argv):
            out = argv[i + 1]
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"كُتِب: {out}")
    else:
        print(payload)
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
