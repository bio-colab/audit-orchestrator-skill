#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
place_marker.py — يرسّخ علامات تعليق حول أول ظهور لنصّ اقتباس داخل document.xml.

مهارة docx تُنشئ التعليق عبر comment.py وتطبع قصاصة العلامات، لكنها تترك
لك مهمة وضع تلك العلامات في الموضع الصحيح. هذه الأداة تتمّم ذلك جراحياً:
تجد أول <w:r> يحوي النص الهدف (بعد دمج الـ runs) وتلفّه بـ
commentRangeStart/End + commentReference — دون تفكيك الملف أو تغيير تنسيقه.

سير العمل الكامل (من داخل مجلد مُفكّك):
    1) unzip file.docx -d unpacked/ ; find unpacked -type l -delete
    2) python <docx>/scripts/merge_runs.py unpacked/
    3) python <docx>/scripts/comment.py unpacked/ "نص الملاحظة"   # يعيد رقم التعليق id
    4) python place_marker.py unpacked/word/document.xml --id 0 --target "(Smith, 2020)"
    5) (cd unpacked && zip -Xr ../out.docx .)
    6) python <docx>/scripts/office/validate.py out.docx --original file.docx

يضع علامة واحدة لكل استدعاء. للملاحظات المتعددة، كرّر الخطوتين 3–4.
"""
import sys, re, argparse

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

RANGE_START = '<w:commentRangeStart w:id="{id}"/>'
RANGE_END   = '<w:commentRangeEnd w:id="{id}"/>'
REF_RUN     = ('<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr>'
               '<w:commentReference w:id="{id}"/></w:r>')

def find_run_with_text(xml, target):
    """يجد أول <w:r>...</w:r> يحوي النص الهدف داخل <w:t>. يعيد (start,end) أو None.

    يفترض أنّ merge_runs.py شُغّل مسبقاً فصار النص متصلاً داخل run واحد.
    كخطة بديلة، يبحث عن أقرب تطابق جزئي على مستوى <w:t>.
    """
    # طبّع الهدف: أزل الفراغات الزائدة
    tnorm = re.sub(r"\s+", " ", target.strip())
    # مرّ على كل <w:r>...</w:r>
    for m in re.finditer(r"<w:r\b[^>]*>.*?</w:r>", xml, re.S):
        run = m.group(0)
        texts = re.findall(r"<w:t\b[^>]*>(.*?)</w:t>", run, re.S)
        joined = re.sub(r"\s+", " ", "".join(texts)).strip()
        if tnorm and tnorm in joined:
            return m.start(), m.end()
    # بديل: تطابق على مستوى <w:t> منفرد
    for m in re.finditer(r"<w:t\b[^>]*>(.*?)</w:t>", xml, re.S):
        if tnorm in re.sub(r"\s+", " ", m.group(1)).strip():
            # وسّع لحدود الـ run الحاوي
            rstart = xml.rfind("<w:r", 0, m.start())
            rend = xml.find("</w:r>", m.end())
            if rstart != -1 and rend != -1:
                return rstart, rend + len("</w:r>")
    return None

def place(xml, cid, target):
    span = find_run_with_text(xml, target)
    if not span:
        return None
    s, e = span
    run = xml[s:e]
    injected = (RANGE_START.format(id=cid) + run +
                RANGE_END.format(id=cid) + REF_RUN.format(id=cid))
    return xml[:s] + injected + xml[e:]

def main():
    ap = argparse.ArgumentParser(description="ترسيخ علامات تعليق حول اقتباس في document.xml.")
    ap.add_argument("document_xml", help="مسار unpacked/word/document.xml")
    ap.add_argument("--id", required=True, help="رقم التعليق الذي أعاده comment.py")
    ap.add_argument("--target", required=True, help="نص الاقتباس المراد التعليق عليه (كما يظهر)")
    ap.add_argument("--dry-run", action="store_true", help="اعرض هل وُجد الهدف دون كتابة")
    args = ap.parse_args()

    with open(args.document_xml, encoding="utf-8") as f:
        xml = f.read()
    out = place(xml, args.id, args.target)
    if out is None:
        print(f"✗ لم يُعثر على النص الهدف: «{args.target}». "
              "تأكّد من تشغيل merge_runs.py أولاً، أو قصّر النص الهدف.", file=sys.stderr)
        sys.exit(2)
    if args.dry_run:
        print(f"✓ وُجد الهدف وسيُلفّ بعلامات التعليق #{args.id} (تشغيل تجريبي، لم يُكتب).")
        return
    with open(args.document_xml, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"✓ رُسّخت علامات التعليق #{args.id} حول «{args.target}».")

if __name__ == "__main__":
    main()
