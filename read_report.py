import codecs
with codecs.open("report.txt", "r", "utf-16le", errors="ignore") as f:
    text = f.read()
with codecs.open("report_utf8.txt", "w", "utf-8") as f:
    f.write(text)
