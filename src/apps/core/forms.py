from django import forms


def style_widgets(form: forms.BaseForm) -> None:
    """Give every control the design-system class."""
    for field in form.fields.values():
        widget = field.widget
        css = "size-4 accent-primary" if isinstance(widget, forms.CheckboxInput) else "input"
        widget.attrs["class"] = f"{widget.attrs.get('class', '')} {css}".strip()


def focus_first_error(form: forms.BaseForm) -> None:
    """Put the cursor into the first invalid field (AK-01.3: "fokussiert das leere Feld").

    Django itself marks invalid fields with aria-invalid="true".
    """
    for name, field in form.fields.items():
        if name in form.errors:
            field.widget.attrs["autofocus"] = True
            return
