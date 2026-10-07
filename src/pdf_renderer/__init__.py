"""Stand-alone PDF renderer for the risk export (M-03).

Runs in its own container without database access and without Django. It receives the rows to
print as JSON and returns the PDF; it never decides what may be exported.
"""
