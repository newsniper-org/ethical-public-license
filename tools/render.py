#!/usr/bin/env python3
"""NEPL 라이선스 문서들을 정본(.md)에서 네 형식으로 뽑는다.

정본:  NEPL-v1.{ko,en,ja,de}.md · NEPL-v1-EP.{ko,en,ja,de}.md   (CommonMark)
생성물: 같은 이름의 .txt (UTF-8 plain text) · .rst (reStructuredText) · .typ (Typst >= 0.14)

라이선스 제12.1조가 「형식은 규정하지 않는다」고 하므로 형식은 자유이나,
기본 템플릿은 네 형식을 함께 제공한다 — 문면은 넷이 같아야 한다(이 스크립트가 그것을 보장한다).

    python3 tools/render.py                    # 전부 다시 만든다
    python3 tools/render.py --check            # 검사만 한다(0/1)
    python3 tools/render.py --doc NEPL-v1-EP   # 한 문서만
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIC = ROOT          # 정본·생성물 모두 저장소 최상위에 둔다
LANGS = ("ko", "en", "ja", "de")
# 정본 문서들 — 각각 4언어 × 4형식.
DOCS = ("NEPL-v1", "NEPL-v1-EP")


# ---------- 공통 파서 ----------
# 인라인 마크업을 벗기고 순수 텍스트로
def plain_inline(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", s)
    s = re.sub(r"_(.+?)_", r"\1", s)
    s = re.sub(r"`(.+?)`", r"\1", s)
    return s


def wrap(s: str, width: int = 96) -> list[str]:
    """CJK 를 2폭으로 세어 접는다(단어 경계 존중, 공백 없는 CJK 는 글자 단위)."""
    def w(ch: str) -> int:
        return 2 if ord(ch) > 0x1100 and (
            0x1100 <= ord(ch) <= 0x115F or 0x2E80 <= ord(ch) <= 0xA4CF
            or 0xAC00 <= ord(ch) <= 0xD7A3 or 0xF900 <= ord(ch) <= 0xFAFF
            or 0xFE30 <= ord(ch) <= 0xFE6F or 0xFF00 <= ord(ch) <= 0xFF60
            or 0xFFE0 <= ord(ch) <= 0xFFE6) else 1

    out, line, cur = [], "", 0
    for tok in re.findall(r"\s+|\S+", s):
        if tok.isspace():
            if line:
                line += " "
                cur += 1
            continue
        tw = sum(w(c) for c in tok)
        if cur + tw > width and line:
            out.append(line.rstrip())
            line, cur = "", 0
        if tw > width:  # 긴 CJK 덩어리는 글자 단위로
            for ch in tok:
                cw = w(ch)
                if cur + cw > width:
                    out.append(line.rstrip())
                    line, cur = "", 0
                line += ch
                cur += cw
            continue
        line += tok
        cur += tw
    if line.strip():
        out.append(line.rstrip())
    return out or [""]


def parse(md: str) -> list[tuple[str, str]]:
    """(kind, payload) 블록 목록. kind: h1/h2/p/li/code/hr"""
    blocks: list[tuple[str, str]] = []
    buf: list[str] = []
    in_code = False
    code: list[str] = []
    for line in md.split("\n"):
        if line.startswith("```"):
            if in_code:
                blocks.append(("code", "\n".join(code)))
                code, in_code = [], False
            else:
                if buf:
                    blocks.append(("p", " ".join(buf)))
                    buf = []
                in_code = True
            continue
        if in_code:
            code.append(line)
            continue
        if not line.strip():
            if buf:
                blocks.append(("p", " ".join(buf)))
                buf = []
            continue
        if line.startswith("# "):
            if buf:
                blocks.append(("p", " ".join(buf))); buf = []
            blocks.append(("h1", line[2:].strip()))
        elif line.startswith("## "):
            if buf:
                blocks.append(("p", " ".join(buf))); buf = []
            blocks.append(("h2", line[3:].strip()))
        elif line.strip() == "---":
            if buf:
                blocks.append(("p", " ".join(buf))); buf = []
            blocks.append(("hr", ""))
        elif line.strip().startswith("- "):
            if buf:
                blocks.append(("p", " ".join(buf))); buf = []
            blocks.append(("li", line.strip()[2:].strip()))
        else:
            buf.append(line.strip())
    if buf:
        blocks.append(("p", " ".join(buf)))
    return blocks


# ---------- 형식별 렌더 ----------
def render_txt(blocks) -> str:
    o: list[str] = []
    prev = None
    for kind, s in blocks:
        if prev == "li" and kind != "li":
            o += [""]
        if kind == "h1":
            t = plain_inline(s)
            o += ["=" * 78, t, "=" * 78, ""]
        elif kind == "h2":
            t = plain_inline(s)
            o += [t, "-" * min(len(t) * 2, 78), ""]
        elif kind == "hr":
            o += ["-" * 78, ""]
        elif kind == "code":
            o += ["    " + l for l in s.split("\n")]
            o += [""]
        elif kind == "li":
            ls = wrap(plain_inline(s), 92)
            o += ["  - " + ls[0]] + ["    " + l for l in ls[1:]]
        else:
            o += wrap(plain_inline(s)) + [""]
        prev = kind
    return "\n".join(o).rstrip() + "\n"


def render_rst(blocks) -> str:
    def inline(s: str) -> str:
        # reStructuredText 의 인라인 마크업은 앞뒤가 공백/일부 구두점이어야 한다.
        # CJK 괄호(「」·（）) 옆에서는 성립하지 않으므로, escaped whitespace(`\ `)로 경계를 만든다.
        s = s.replace("\\", "\\\\")
        s = re.sub(r"\*\*(.+?)\*\*", lambda m: "\\ **" + m.group(1).strip() + "**\\ ", s)
        s = re.sub(r"(?<!\*)\*(?!\*)([^*\n]+?)(?<!\*)\*(?!\*)", lambda m: "\\ *" + m.group(1).strip() + "*\\ ", s)
        s = re.sub(r"_(.+?)_", lambda m: "\\ *" + m.group(1).strip() + "*\\ ", s)
        s = re.sub(r"`(.+?)`", lambda m: "\\ ``" + m.group(1) + "``\\ ", s)
        s = re.sub(r"\\ (\s)", r"\1", s)      # 이미 공백이면 escaped whitespace 불필요
        s = re.sub(r"(\s)\\ ", r"\1", s)
        s = s.strip()
        s = re.sub(r"^\\ +", "", s)           # 블록의 처음·끝에서도 불필요하다
        return re.sub(r"\\ *$", "", s).rstrip()

    def rule(t: str, ch: str) -> str:
        return ch * max(len(t) * 2, 8)

    o: list[str] = []
    prev = None
    for kind, s in blocks:
        if prev == "li" and kind != "li":
            o += [""]
        if kind == "h1":
            t = plain_inline(s)
            o += [rule(t, "="), t, rule(t, "="), ""]
        elif kind == "h2":
            t = plain_inline(s)
            o += [t, rule(t, "-"), ""]
        elif kind == "hr":
            o += ["..", "", "----", ""]
        elif kind == "code":
            o += ["::", ""] + ["   " + l for l in s.split("\n")] + [""]
        elif kind == "li":
            ls = wrap(inline(s), 92)
            o += ["- " + ls[0]] + ["  " + l for l in ls[1:]]
        else:
            o += wrap(inline(s)) + [""]
        prev = kind
    return "\n".join(o).rstrip() + "\n"


def render_typ(blocks, lang: str) -> str:
    font = {"ko": '("Noto Sans CJK KR", "NanumSquare_ac")',
            "ja": '("Noto Sans CJK JP",)',
            "en": '("Noto Sans", "DejaVu Sans")',
            "de": '("Noto Sans", "DejaVu Sans")'}[lang]

    def inline(s: str) -> str:
        # 백틱 구간은 Typst 의 원시(raw) 문법과 같으므로 그대로 두고, 그 밖의 부분만 이스케이프한다.
        # (`#raw("X")` 형태는 바로 뒤에 `(` 가 오면 함수 호출로 파싱되어 깨진다.)
        parts = re.split(r"(`[^`\n]*`)", s)
        out = []
        for i, part in enumerate(parts):
            if i % 2 == 1:            # 백틱 구간 — 손대지 않는다
                out.append(part)
                continue
            part = part.replace("\\", "\\\\").replace("#", "\\#").replace("@", "\\@")
            part = part.replace("[", "\\[").replace("]", "\\]").replace("$", "\\$")
            part = re.sub(r"\*\*(.+?)\*\*", r"#strong[\1]", part)
            part = re.sub(r"(?<!\*)\*(?!\*)([^*\n]+?)(?<!\*)\*(?!\*)", r"#emph[\1]", part)
            part = re.sub(r"_(.+?)_", r"#emph[\1]", part)
            out.append(part)
        joined = "".join(out)
        # `#strong[…](…)` 는 함수 호출로 이어 읽히므로 세미콜론으로 식을 끊는다(세미콜론은 출력되지 않는다).
        return re.sub(r"(#(?:strong|emph)\[[^\[\]]*\])(?=[(\[])", r"\1;", joined)

    o = [f"// NEPLv1 — {lang}. 생성물: tools/render.py 가 NEPL-v1.{lang}.md 에서 만든다. 손으로 고치지 않는다.",
         '#set page(paper: "a4", margin: (x: 2.2cm, y: 2.4cm))',
         f'#set text(font: {font}, lang: "{lang}", size: 10pt)',
         "#set par(justify: false, leading: 0.68em)",
         "#set heading(numbering: none)",
         '#show heading.where(level: 1): set text(size: 15pt)',
         '#show heading.where(level: 2): set text(size: 11.5pt)',
         ""]
    prev = None
    for kind, s in blocks:
        if prev == "li" and kind != "li":
            o += [""]
        if kind == "h1":
            o += [f"= {inline(s)}", ""]
        elif kind == "h2":
            o += [f"== {inline(s)}", ""]
        elif kind == "hr":
            o += ["#line(length: 100%, stroke: 0.4pt + gray)", ""]
        elif kind == "code":
            body = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            o += [f'#block(width: 100%, fill: luma(245), inset: 8pt, radius: 2pt, raw("{body}"))', ""]
        elif kind == "li":
            o += [f"- {inline(s)}"]
        else:
            o += [inline(s), ""]
        prev = kind
    return "\n".join(o).rstrip() + "\n"


# ---------- 언어 간 대조 ----------
# 번역본이 정본에 없는 실체 조항을 만들거나 조항을 빠뜨리는 것을 막는다.
HEAD_NUM_RE = re.compile(r"^E?(\d+)\.")
CLAUSE_RE = re.compile(r"^(E?\d+\.\d+(?:\.\d+)*)\s")
ITEM_RE = re.compile(r"^\(([a-z])\)")
# 번역본에는 제10.3조가 요구하는 「이것은 번역이며 한국어본이 정본이다」 한 문단이 더 있다.
TRANSLATION_NOTICE_PARAGRAPHS = 1


def structure(blocks) -> dict:
    heads: list[str] = []
    clauses: list[str] = []
    items: list[str] = []
    counts = {"h1": 0, "h2": 0, "p": 0, "li": 0, "code": 0, "hr": 0}
    for kind, s in blocks:
        counts[kind] = counts.get(kind, 0) + 1
        if kind == "h2":
            m = HEAD_NUM_RE.match(plain_inline(s))
            heads.append(m.group(1) if m else "annex")
        elif kind == "p":
            t = plain_inline(s)
            m = CLAUSE_RE.match(t)
            if m:
                clauses.append(m.group(1))
                continue
            m = ITEM_RE.match(t)
            if m:
                items.append(m.group(1))
    return {"heads": heads, "clauses": clauses, "items": items, "counts": counts}


def first_diff(a: list[str], b: list[str]) -> str:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return f"{i + 1}번째: 정본 {x!r} ↔ 번역 {y!r}"
    return f"길이: 정본 {len(a)} ↔ 번역 {len(b)}" + (
        f" (모자람 {b[len(a):] if len(b) > len(a) else a[len(b):]})" if len(a) != len(b) else "")


def cross_language(structs: dict[str, dict]) -> list[str]:
    ref = structs["ko"]
    errs: list[str] = []
    for lang in LANGS:
        if lang == "ko":
            continue
        cur = structs[lang]
        for key, label in (("heads", "절 번호"), ("clauses", "조항 번호"), ("items", "각 목 기호")):
            if cur[key] != ref[key]:
                errs.append(f"{lang}: {label} 불일치 — {first_diff(ref[key], cur[key])}")
        for key in ("h1", "h2", "li", "code", "hr"):
            if cur["counts"][key] != ref["counts"][key]:
                errs.append(f"{lang}: {key} 블록 수 불일치 — 정본 {ref['counts'][key]} ↔ 번역 {cur['counts'][key]}")
        want_p = ref["counts"]["p"] + TRANSLATION_NOTICE_PARAGRAPHS
        if cur["counts"]["p"] != want_p:
            errs.append(
                f"{lang}: 문단 수 불일치 — 정본 {ref['counts']['p']} + 번역 고지 1 = {want_p} 이어야 하는데 {cur['counts']['p']}")
    return errs


def process(stem: str, check: bool) -> tuple[list[str], list[str], list[str], dict]:
    """한 문서(4언어 × 4형식)를 쓰거나 검사한다. (stale, mismatch, cross, ko구조)"""
    stale: list[str] = []
    structs: dict[str, dict] = {}
    for lang in LANGS:
        src = LIC / f"{stem}.{lang}.md"
        if not src.exists():
            raise SystemExit(f"FAIL 정본 없음: {src.relative_to(ROOT)}")
        blocks = parse(src.read_text(encoding="utf8"))
        structs[lang] = structure(blocks)
        outs = {
            f"{stem}.{lang}.txt": render_txt(blocks),
            f"{stem}.{lang}.rst": render_rst(blocks),
            f"{stem}.{lang}.typ": render_typ(blocks, lang),
        }
        for name, text in outs.items():
            q = LIC / name
            if check:
                if not q.exists() or q.read_text(encoding="utf8") != text:
                    stale.append(name)
            else:
                q.write_text(text, encoding="utf8")
        if not check:
            print(f"[{stem} · {lang}] {len(outs)} formats ← {src.name} ({len(blocks)} blocks)")

    # 형식이 달라도 문면은 같아야 한다 — 구조 표지를 걷어내고 대조한다.
    def body_only(text: str) -> str:
        lines = []
        for l in text.split("\n"):
            t = l.strip()
            if not t or set(t) <= set("=-.:_~^\"") or t == "::":
                continue
            lines.append(t)
        joined = " ".join(lines)
        joined = re.sub(r"#strong\[|#emph\[|#raw\(\"|\"\)|#line\(length: 100%[^)]*\)", "", joined)
        joined = re.sub(r"^//.*| #set [^\n]*| #show [^\n]*|#block\([^)]*", "", joined)
        return re.sub(r"[\s`*_#=\\\[\]-]", "", joined)

    mismatch: list[str] = []
    for lang in LANGS:
        ref = body_only((LIC / f"{stem}.{lang}.md").read_text(encoding="utf8"))
        for ext in ("txt", "rst"):
            q = LIC / f"{stem}.{lang}.{ext}"
            if q.exists() and body_only(q.read_text(encoding="utf8")) != ref:
                mismatch.append(f"{stem}.{lang}.{ext}")

    return stale, mismatch, cross_language(structs), structs["ko"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="생성물이 정본과 맞는지만 확인")
    ap.add_argument("--doc", action="append", choices=DOCS,
                    help="이 문서만 처리한다(여러 번 쓸 수 있다). 기본은 전부")
    args = ap.parse_args()
    docs = tuple(args.doc) if args.doc else DOCS

    bad = False
    for stem in docs:
        stale, mismatch, cross, ko = process(stem, args.check)
        label = f"{stem}"
        if args.check:
            if stale:
                print(f"FAIL [{label}] 정본과 어긋난 생성물:", ", ".join(stale))
                print("  python3 tools/render.py 로 다시 만든다")
                bad = True
                continue
            if mismatch:
                print(f"FAIL [{label}] 형식 간 문면 불일치:", ", ".join(mismatch))
                bad = True
                continue
            if cross:
                print(f"FAIL [{label}] 언어 간 구조 불일치:")
                for e in cross:
                    print("  -", e)
                bad = True
                continue
            print(f"[{label}] OK — 12개 파일 · 형식 간 문면 일치 · 언어 간 구조 일치 "
                  f"(절 {len(ko['heads'])} · 조항 {len(ko['clauses'])} · 목 {len(ko['items'])})")
        else:
            if mismatch:
                print(f"경고 [{label}] 형식 간 문면 불일치:", ", ".join(mismatch))
            if cross:
                print(f"경고 [{label}] 언어 간 구조 불일치:")
                for e in cross:
                    print("  -", e)
            else:
                print(f"[{label}] 언어 간 대조 OK — "
                      f"절 {len(ko['heads'])} · 조항 {len(ko['clauses'])} · 목 {len(ko['items'])}")
    if args.check and not bad:
        print(f"license_render check: OK ({len(docs)}개 문서 · {len(docs) * 12}개 파일)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
