# Biên dịch báo cáo. Bắt buộc dùng XeLaTeX vì tài liệu nạp phông hệ thống.
#
#   make          biên dịch đầy đủ (kể cả tài liệu tham khảo)
#   make quick    biên dịch một lượt, xem nhanh khi đang sửa nội dung
#   make clean    xoá tệp trung gian
#   make view     mở tệp PDF

MAIN = main

all:
	latexmk -xelatex -interaction=nonstopmode $(MAIN).tex

quick:
	xelatex -interaction=nonstopmode $(MAIN).tex

# Dùng khi máy không có latexmk
manual:
	xelatex -interaction=nonstopmode $(MAIN).tex
	biber $(MAIN)
	xelatex -interaction=nonstopmode $(MAIN).tex
	xelatex -interaction=nonstopmode $(MAIN).tex

clean:
	latexmk -C 2>/dev/null || true
	rm -f *.aux *.bbl *.bcf *.blg *.log *.out *.toc *.lof *.lot \
	      *.run.xml *.fls *.fdb_latexmk *.synctex.gz
	rm -f chapters/*.aux

view: all
	open $(MAIN).pdf 2>/dev/null || xdg-open $(MAIN).pdf

.PHONY: all quick manual clean view
