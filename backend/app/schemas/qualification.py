from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.allowlists import (
    QUALIFICATION_FIELD_TYPES,
    QUALIFICATION_RULE_TYPES,
    SELECT_FIELD_TYPES,
)
from app.core.text_safety import validate_plain_text, validate_safe_key, validate_time_hhmm

MAX_QUALIFICATION_FIELDS = 40
MAX_SELECT_OPTIONS = 30
MAX_QUALIFICATION_RULES = 40


class QualificationFieldOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Annotated[str, Field(min_length=1, max_length=100)]
    label: Annotated[str, Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def _sanitize(self) -> "QualificationFieldOption":
        self.value = validate_plain_text(self.value, max_length=100)
        self.label = validate_plain_text(self.label, max_length=100)
        return self


class QualificationField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: Annotated[str, Field(min_length=1, max_length=64)]
    label: Annotated[str, Field(min_length=1, max_length=200)]
    type: str
    description: str | None = None
    required: bool = False
    options: list[QualificationFieldOption] | None = None
    min_value: float | None = None
    max_value: float | None = None
    max_length: Annotated[int | None, Field(gt=0, le=100_000)] = None
    display_order: int = 0
    is_sensitive: bool = False

    @model_validator(mode="after")
    def _validate(self) -> "QualificationField":
        self.key = validate_safe_key(self.key)
        self.label = validate_plain_text(self.label, max_length=200)
        if self.description:
            self.description = validate_plain_text(self.description, max_length=500)

        if self.type not in QUALIFICATION_FIELD_TYPES:
            raise ValueError(f"Unsupported field type: {self.type!r}")

        is_select = self.type in SELECT_FIELD_TYPES
        if is_select:
            if not self.options:
                raise ValueError(f"Field {self.key!r} of type {self.type!r} requires options.")
            if len(self.options) > MAX_SELECT_OPTIONS:
                raise ValueError(f"Field {self.key!r} has too many options (max {MAX_SELECT_OPTIONS}).")
            values = [o.value for o in self.options]
            if len(values) != len(set(values)):
                raise ValueError(f"Field {self.key!r} has duplicate option values.")
        elif self.options is not None:
            raise ValueError(f"Field {self.key!r} of type {self.type!r} must not define options.")

        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValueError(f"Field {self.key!r} has min_value greater than max_value.")

        return self


class QualificationSchema(BaseModel):
    """The full set of qualification fields for one receptionist workflow."""

    model_config = ConfigDict(extra="forbid")

    fields: list[QualificationField] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_collection(self) -> "QualificationSchema":
        if len(self.fields) > MAX_QUALIFICATION_FIELDS:
            raise ValueError(f"Too many qualification fields (max {MAX_QUALIFICATION_FIELDS}).")
        keys = [f.key for f in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("Qualification field keys must be unique.")
        return self


class QualificationRule(BaseModel):
    """One declarative rule. No expression language, no eval — `type` is
    restricted to QUALIFICATION_RULE_TYPES and each type's required
    companion fields are checked explicitly below."""

    model_config = ConfigDict(extra="forbid")

    type: str
    field_key: str | None = None
    field_keys: list[str] | None = None  # for required_fields_completed
    value: Any = None
    values: list[Any] | None = None  # for one_of

    @model_validator(mode="after")
    def _validate(self) -> "QualificationRule":
        if self.type not in QUALIFICATION_RULE_TYPES:
            raise ValueError(f"Unsupported qualification rule type: {self.type!r}")

        if self.type == "required_fields_completed":
            pass  # field_keys optional (None = "all required fields")
        elif self.type in ("equals", "numeric_min", "numeric_max", "consent_required"):
            if not self.field_key:
                raise ValueError(f"Rule type {self.type!r} requires field_key.")
            if self.type in ("numeric_min", "numeric_max") and not isinstance(self.value, int | float):
                raise ValueError(f"Rule type {self.type!r} requires a numeric value.")
        elif self.type == "one_of":
            if not self.field_key:
                raise ValueError("Rule type 'one_of' requires field_key.")
            if not self.values:
                raise ValueError("Rule type 'one_of' requires a non-empty values list.")

        if self.field_key:
            self.field_key = validate_safe_key(self.field_key)
        if self.field_keys:
            self.field_keys = [validate_safe_key(k) for k in self.field_keys]

        return self


class QualificationRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rules: list[QualificationRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_collection(self) -> "QualificationRules":
        if len(self.rules) > MAX_QUALIFICATION_RULES:
            raise ValueError(f"Too many qualification rules (max {MAX_QUALIFICATION_RULES}).")
        return self


class WorkingInterval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: str
    end: str

    @model_validator(mode="after")
    def _validate(self) -> "WorkingInterval":
        self.start = validate_time_hhmm(self.start)
        self.end = validate_time_hhmm(self.end)
        if self.start >= self.end:
            # Overnight ranges (end < start) are deliberately not supported
            # in Phase 3 — see docs/database-schema.md known limitations.
            raise ValueError("Interval start must be earlier than end (overnight hours are not supported).")
        return self


class DayWorkingHours(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day_of_week: Literal[0, 1, 2, 3, 4, 5, 6]  # 0 = Monday .. 6 = Sunday
    closed: bool = False
    intervals: list[WorkingInterval] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate(self) -> "DayWorkingHours":
        if self.closed:
            if self.intervals:
                raise ValueError("A closed day must not have intervals.")
            return self
        if not self.intervals:
            raise ValueError("An open day must have at least one interval.")
        sorted_intervals = sorted(self.intervals, key=lambda i: i.start)
        for a, b in zip(sorted_intervals, sorted_intervals[1:], strict=False):
            if a.end > b.start:
                raise ValueError("Working-hour intervals must not overlap.")
        return self


class WorkingHours(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: list[DayWorkingHours] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_collection(self) -> "WorkingHours":
        seen_days = [d.day_of_week for d in self.days]
        if len(seen_days) != len(set(seen_days)):
            raise ValueError("Duplicate day_of_week entries in working hours.")
        return self
