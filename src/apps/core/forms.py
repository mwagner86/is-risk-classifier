from django import forms


def focus_first_error(form: forms.BaseForm) -> None:
    """Put the cursor into the first invalid field (AK-01.3: "fokussiert das leere Feld").

    Django itself marks invalid fields with aria-invalid="true".
    """
    for name, field in form.fields.items():
        if name in form.errors:
            field.widget.attrs["autofocus"] = True
            return
