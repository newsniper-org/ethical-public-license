# NEPL 라이선스 템플릿 저장소
set shell := ["bash", "-euo", "pipefail", "-c"]

default:
    @just --list --unsorted

# .md 정본 → .txt/.rst/.typ (12개 파일)
render:
    python3 tools/render.py

# 생성물이 정본과 맞는지, 형식 간 문면이 같은지
check:
    python3 tools/render.py --check

# 네 언어 .typ 를 PDF 로 (폰트 경로는 로컬 기준)
pdf:
    mkdir -p build
    for l in ko en ja de; do \
      typst compile --font-path /usr/share/fonts/noto-cjk --font-path /usr/share/fonts/nanum \
        "NEPL-v1.$l.typ" "build/NEPL-v1.$l.pdf"; \
    done
    @ls build/
