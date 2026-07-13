#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_findings.py — التحقّق من ملاحظات المحكّات ودمجها لمِحَكّ القيادة.

يقرأ ملفّات <auditor>.findings.json (سكيما findings-schema.md)، يتحقّق من
مطابقتها، يدمجها بالموقع (locus)، ويرفع تصادمات السيمات (موضعٌ مسّه أكثر
من محكّ) كي تُحسَم بجدول seam-ownership.md.

حتميّ، أوفلاين، بلا تبعيّات. للمحطّتين 5–6.

الاستعمال:
    python validate_findings.py <dir-with-findings-json> [--out-dir DIR]
    python validate_findings.py --self-test
"""

import sys
import os
import re
import json
import glob

SEVERITIES = {"critical", "major", "minor"}
CONFIDENCES = {"deterministic", "high", "medium", "low", "unverifiable"}
REQUIRED_FINDING = {"auditor", "finding_id", "locus", "severity", "confidence", "why", "repair"}
ASYM_AUDITORS = {
    "literature-review-auditor",
    "contribution-impact-auditor",
    "ethics-integrity-auditor",
}
# صياغاتٌ مصادِقة ممنوعة في ملاحظاتٍ لا تماثلية (asymmetric)
_CERTIFYING = ["اصيل", "أصيل", "مؤكد أن", "مؤكَّد", "مهم للحقل", "نزيه", "ثبت أن", "برهن على أن العمل"]


def _err(errors, fid, msg):
    errors.append(f"[{fid}] {msg}")


def validate_finding(f, errors):
    fid = f.get("finding_id", "?")
    missing = REQUIRED_FINDING - set(f.keys())
    if missing:
        _err(errors, fid, f"حقولٌ ناقصة: {', '.join(sorted(missing))}")
    if f.get("severity") not in SEVERITIES:
        _err(errors, fid, f"شدّةٌ غير صالحة: {f.get('severity')}")
    if f.get("confidence") not in CONFIDENCES:
        _err(errors, fid, f"ثقةٌ غير صالحة: {f.get('confidence')}")
    # الحرج/الجوهريّ يحتاج شاهداً
    if f.get("severity") in {"critical", "major"}:
        loc = f.get("locus", {}) or {}
        if not (loc.get("quote") or loc.get("anchor")):
            _err(errors, fid, "ملاحظةٌ حرجة/جوهرية بلا شاهد (quote/anchor)")
    # اللاتماثليّ لا يُصادِق
    if f.get("asymmetric") is True or f.get("auditor") in ASYM_AUDITORS:
        why = str(f.get("why", ""))
        for bad in _CERTIFYING:
            if bad in why:
                _err(errors, fid, f"صياغةٌ مصادِقة ممنوعة في ملاحظةٍ لا تماثلية: «{bad}»")
                break
    # سقف النزاهة
    if f.get("auditor") == "ethics-integrity-auditor":
        cats = str(f.get("why", "")) + str(f.get("category", ""))
        for bad in ["سوء سلوك", "تلفيق", "سرقة", "انتحال مؤكد"]:
            if bad in cats:
                _err(errors, fid, f"تجاوزُ سقف النزاهة (اتهام): «{bad}»")
                break


def locus_key(locus):
    if not isinstance(locus, dict):
        return ("?", "?", "?")
    ch = str(locus.get("chapter", "?")).strip()
    pg = str(locus.get("page", "?")).strip()
    pr = str(locus.get("paragraph", "?")).strip()
    return (ch, pg, pr)


def load_files(directory):
    files = sorted(glob.glob(os.path.join(directory, "*.findings.json")))
    docs = []
    for path in files:
        with open(path, "r", encoding="utf-8") as fh:
            docs.append((os.path.basename(path), json.load(fh)))
    return docs


def process(docs):
    errors = []
    merged = []
    by_locus = {}
    for fname, doc in docs:
        auditor = doc.get("auditor", "?")
        if doc.get("skipped_reason"):
            continue  # مُخفى بسببٍ معلَن — لا ملاحظات
        for f in doc.get("findings", []):
            f.setdefault("auditor", auditor)
            validate_finding(f, errors)
            merged.append(f)
            by_locus.setdefault(locus_key(f.get("locus", {})), []).append(f)

    # تصادمات السيمات: موضعٌ مسّه أكثر من محكّ مختلف
    collisions = []
    for key, group in by_locus.items():
        auditors = sorted({g.get("auditor") for g in group})
        if len(auditors) > 1:
            collisions.append({
                "locus": {"chapter": key[0], "page": key[1], "paragraph": key[2]},
                "auditors": auditors,
                "finding_ids": [g.get("finding_id") for g in group],
                "resolve_with": "references/seam-ownership.md",
            })

    # ترتيب الدمج بالموقع ثم الشدّة
    sev_rank = {"critical": 0, "major": 1, "minor": 2}
    merged.sort(key=lambda f: (locus_key(f.get("locus", {})),
                               sev_rank.get(f.get("severity"), 9)))
    return errors, merged, collisions


def run(directory, out_dir):
    docs = load_files(directory)
    if not docs:
        print(f"لا ملفّات *.findings.json في: {directory}", file=sys.stderr)
        return 2
    errors, merged, collisions = process(docs)

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "merged.json"), "w", encoding="utf-8") as fh:
        json.dump({"count": len(merged), "findings": merged}, fh,
                  ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "collisions.json"), "w", encoding="utf-8") as fh:
        json.dump({"count": len(collisions), "collisions": collisions}, fh,
                  ensure_ascii=False, indent=2)

    print(f"محكّاتٌ مقروءة: {len(docs)}")
    print(f"ملاحظاتٌ مدموجة: {len(merged)}")
    print(f"تصادماتُ سيمات: {len(collisions)}  → تُحسَم بـ seam-ownership.md")
    if errors:
        print(f"\n⚠︎ مخالفاتُ سكيما ({len(errors)}):")
        for e in errors:
            print("  -", e)
        return 1
    print("مطابقةُ السكيما: سليمة ✅")
    return 0


# ----------------------------------------------------------------------
def self_test():
    ok = True
    good = {
        "auditor": "citation-auditor",
        "findings": [{
            "auditor": "citation-auditor", "finding_id": "cit-1",
            "locus": {"chapter": "ف2", "page": 42, "paragraph": 3, "quote": "…(12)…"},
            "severity": "major", "confidence": "high",
            "why": "لا مقابل في القائمة", "repair": "أضِف المرجع",
        }],
    }
    # ملاحظتان على موقعٍ واحد من محكّين → تصادم سيم
    other = {
        "auditor": "argumentation-writing-auditor",
        "findings": [{
            "auditor": "argumentation-writing-auditor", "finding_id": "arg-1",
            "locus": {"chapter": "ف2", "page": 42, "paragraph": 3, "quote": "ومن ثمّ"},
            "severity": "major", "confidence": "medium",
            "why": "الرابط يَعِد لزوماً لا يُقيمه", "repair": "أزِل الرابط أو أقِم اللزوم",
        }],
    }
    # مخالفة: لا تماثليّ بصياغةٍ مصادِقة
    bad = {
        "auditor": "literature-review-auditor",
        "findings": [{
            "auditor": "literature-review-auditor", "finding_id": "lit-1",
            "locus": {"chapter": "ف1", "page": 5, "paragraph": 1, "quote": "…"},
            "severity": "minor", "confidence": "low", "asymmetric": True,
            "why": "البحث اصيل ولا سابقة له", "repair": "—",
        }],
    }
    errors, merged, collisions = process(
        [("citation-auditor.findings.json", good),
         ("argumentation-writing-auditor.findings.json", other),
         ("literature-review-auditor.findings.json", bad)]
    )
    # نتوقّع: تصادمٌ واحد (الموقع المشترك)، ومخالفةٌ واحدة على الأقلّ (الصياغة المصادِقة)
    if len(collisions) != 1:
        print(f"[FAIL] تصادمات متوقّعة=1 · فعليّ={len(collisions)}"); ok = False
    else:
        print(f"[OK] تصادمُ سيمٍ واحد على الموقع المشترك: {collisions[0]['auditors']}")
    if not any("مصادِقة" in e for e in errors):
        print("[FAIL] لم تُلتقَط الصياغة المصادِقة في ملاحظةٍ لا تماثلية"); ok = False
    else:
        print("[OK] التُقِطت الصياغة المصادِقة الممنوعة")
    if len(merged) != 3:
        print(f"[FAIL] ملاحظاتٌ مدموجة متوقّعة=3 · فعليّ={len(merged)}"); ok = False
    else:
        print("[OK] دُمِجت الملاحظات الثلاث ورُتّبت بالموقع")
    print("النتيجة:", "نجح ✅" if ok else "فشل ❌")
    return 0 if ok else 1


def main(argv):
    if "--self-test" in argv:
        return self_test()
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print("الاستعمال: python validate_findings.py <dir> [--out-dir DIR]", file=sys.stderr)
        return 2
    directory = args[0]
    out_dir = "."
    if "--out-dir" in argv:
        i = argv.index("--out-dir")
        if i + 1 < len(argv):
            out_dir = argv[i + 1]
    return run(directory, out_dir)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
