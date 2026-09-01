"""Reusable qualification-field builders shared across industry templates —
keeps the standard "name / email / phone / consent" contact block from being
retyped ten times with subtly different wording."""

from app.schemas.qualification import QualificationField, QualificationFieldOption


def contact_fields(start_order: int) -> list[QualificationField]:
    return [
        QualificationField(
            key="name",
            label="Full name",
            type="short_text",
            required=True,
            display_order=start_order,
        ),
        QualificationField(
            key="email",
            label="Email address",
            type="email",
            required=True,
            display_order=start_order + 1,
        ),
        QualificationField(
            key="phone",
            label="Phone number",
            type="phone",
            required=False,
            display_order=start_order + 2,
        ),
        QualificationField(
            key="consent",
            label="I agree to be contacted about this enquiry",
            type="boolean",
            required=True,
            is_sensitive=True,
            display_order=start_order + 3,
        ),
    ]


def select_field(
    key: str, label: str, options: list[tuple[str, str]], *, required: bool, order: int
) -> QualificationField:
    return QualificationField(
        key=key,
        label=label,
        type="single_select",
        required=required,
        options=[QualificationFieldOption(value=v, label=lbl) for v, lbl in options],
        display_order=order,
    )
