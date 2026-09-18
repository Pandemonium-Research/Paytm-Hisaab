#!/bin/sh
# Build both PDFs from the one source.
#
#   hisaab-pitch.pdf        the deck you project
#   hisaab-pitch-notes.pdf  speaker notes, one page per slide
#
# Needs XeLaTeX (the rupee sign and the Kannada line will not render under pdflatex).
cd "$(dirname "$0")"

XELATEX="${XELATEX:-xelatex}"

"$XELATEX" -interaction=nonstopmode hisaab-pitch.tex
"$XELATEX" -interaction=nonstopmode -jobname=hisaab-pitch-notes \
  "\def\shownotes{1}\input{hisaab-pitch.tex}"

rm -f *.aux *.log *.out *.nav *.snm *.toc

# xelatex exits nonzero on MiKTeX update nags even when the PDF is fine,
# so check for the artefacts rather than the exit code.
for f in hisaab-pitch.pdf hisaab-pitch-notes.pdf; do
  [ -f "$f" ] || { echo "FAILED: $f not produced"; exit 1; }
done
echo "built: hisaab-pitch.pdf, hisaab-pitch-notes.pdf"
