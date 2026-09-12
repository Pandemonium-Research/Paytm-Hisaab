#!/bin/sh
# Build both PDFs from the one source.
#
#   hisaab-pitch.pdf        the deck you project
#   hisaab-pitch-notes.pdf  presenter view: each slide with its notes beside it
#
# Needs XeLaTeX (the rupee sign and the Kannada line will not render under pdflatex).
set -e
cd "$(dirname "$0")"

XELATEX="${XELATEX:-xelatex}"

"$XELATEX" -interaction=nonstopmode hisaab-pitch.tex
"$XELATEX" -interaction=nonstopmode -jobname=hisaab-pitch-notes \
  "\def\shownotes{1}\input{hisaab-pitch.tex}"

rm -f *.aux *.log *.out *.nav *.snm *.toc
echo "built: hisaab-pitch.pdf, hisaab-pitch-notes.pdf"
