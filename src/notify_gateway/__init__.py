"""Stand-in for the external e-mail/SMS provider (decision 4, iteration 6).

A small HTTP service: e-mails go by SMTP to Mailpit, SMS are only logged. NOTIFY_FAILURE_MODE
forces the outages of AK-03.3 (``timeout`` or ``5xx``). Standard library only, no Django and
no database access.
"""
