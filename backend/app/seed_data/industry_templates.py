"""Versioned industry template definitions.

Editing an existing entry's content here and re-running the seed does
NOTHING to already-seeded rows — see seed_industry_templates() below. To
change a template's content, bump its `version` and add a new entry; the
old version stays exactly as any tenant that already selected it saw it.
"""

from dataclasses import dataclass, field

from app.core.allowlists import MANDATORY_SAFETY_RULES
from app.schemas.qualification import QualificationField, QualificationSchema
from app.seed_data.field_helpers import contact_fields, select_field

_DEFAULT_WORKFLOW_STAGES = [
    "greeting",
    "discovery",
    "qualification",
    "contact_capture",
    "handoff_or_confirmation",
]


@dataclass(frozen=True)
class TemplateDefinition:
    key: str
    version: int
    name: str
    description: str
    icon: str
    terminology: dict[str, str]
    welcome_message: str
    suggested_questions: list[str]
    qualification_fields: list[QualificationField]
    actions: list[str]
    safety_rules: list[str] = field(default_factory=list)
    workflow_stages: list[str] = field(default_factory=lambda: list(_DEFAULT_WORKFLOW_STAGES))

    def qualification_schema_json(self) -> dict:
        return QualificationSchema(fields=self.qualification_fields).model_dump(mode="json")


REAL_ESTATE = TemplateDefinition(
    key="real_estate",
    version=1,
    name="Real Estate Agency",
    description="For residential and commercial real estate agencies handling buyer, renter, and investor enquiries.",
    icon="home",
    terminology={"visitor": "prospect", "enquiry": "property enquiry", "service": "listing"},
    welcome_message=(
        "Hi! I'm here to help with buying, renting, or investing in property. " "What are you looking for today?"
    ),
    suggested_questions=[
        "What listings do you have available right now?",
        "Can you help me find a rental in my budget?",
        "I'm interested in investing — what should I know?",
        "Can I schedule a viewing?",
    ],
    qualification_fields=[
        select_field(
            "enquiry_type",
            "What are you looking to do?",
            [("buy", "Buy"), ("rent", "Rent"), ("invest", "Invest")],
            required=True,
            order=0,
        ),
        QualificationField(key="preferred_location", label="Preferred location", type="short_text", display_order=1),
        select_field(
            "property_type",
            "Property type",
            [
                ("apartment", "Apartment"),
                ("house", "House"),
                ("condo", "Condo"),
                ("commercial", "Commercial"),
                ("land", "Land"),
            ],
            required=False,
            order=2,
        ),
        QualificationField(key="budget_min", label="Minimum budget", type="currency", display_order=3),
        QualificationField(key="budget_max", label="Maximum budget", type="currency", display_order=4),
        QualificationField(key="currency", label="Currency", type="short_text", max_length=3, display_order=5),
        QualificationField(key="bedrooms", label="Bedrooms", type="number", display_order=6),
        select_field(
            "timeline",
            "Timeline",
            [
                ("immediate", "Immediately"),
                ("1_3_months", "1–3 months"),
                ("3_6_months", "3–6 months"),
                ("browsing", "Just browsing"),
            ],
            required=False,
            order=7,
        ),
        QualificationField(
            key="financing_required",
            label="Do you need financing?",
            type="boolean",
            display_order=8,
        ),
        *contact_fields(start_order=9),
    ],
    actions=[
        "answer_questions",
        "capture_contact",
        "qualify_lead",
        "request_callback",
        "request_viewing",
        "request_human_handoff",
    ],
    safety_rules=[
        "Only share property details, pricing, and availability confirmed in approved business content.",
        "Never guarantee financing approval or investment returns.",
    ],
)

CLINIC = TemplateDefinition(
    key="clinic",
    version=1,
    name="Clinic / Dental Practice",
    description="For medical and dental clinics handling administrative appointment intake only.",
    icon="stethoscope",
    terminology={"visitor": "patient", "enquiry": "appointment request", "service": "appointment"},
    welcome_message=(
        "Hello, welcome to our practice. I can help with appointment booking and general "
        "administrative questions. For medical concerns, our clinical team will assist you directly."
    ),
    suggested_questions=[
        "What are your opening hours?",
        "I'd like to book an appointment.",
        "Are you accepting new patients?",
        "What insurance do you accept?",
    ],
    qualification_fields=[
        QualificationField(
            key="service_required",
            label="What service do you need?",
            type="short_text",
            required=True,
            display_order=0,
        ),
        QualificationField(key="preferred_location", label="Preferred location", type="short_text", display_order=1),
        QualificationField(
            key="preferred_doctor",
            label="Preferred doctor (if any)",
            type="short_text",
            display_order=2,
        ),
        select_field(
            "new_or_existing_patient",
            "Are you a new or existing patient?",
            [("new", "New patient"), ("existing", "Existing patient")],
            required=True,
            order=3,
        ),
        QualificationField(key="preferred_date", label="Preferred date", type="date", display_order=4),
        QualificationField(key="preferred_time", label="Preferred time", type="time", display_order=5),
        *contact_fields(start_order=6),
    ],
    actions=[
        "answer_questions",
        "capture_contact",
        "qualify_lead",
        "request_appointment",
        "request_human_handoff",
    ],
    safety_rules=list(MANDATORY_SAFETY_RULES["clinic"]),
)

HOTEL = TemplateDefinition(
    key="hotel",
    version=1,
    name="Boutique Hotel",
    description="For hotels and boutique stays handling reservation enquiries and guest questions.",
    icon="bed",
    terminology={"visitor": "guest", "enquiry": "reservation enquiry", "service": "stay"},
    welcome_message="Welcome! I can help with reservations, amenities, and general questions about your stay.",
    suggested_questions=[
        "Do you have rooms available this weekend?",
        "What amenities do you offer?",
        "Is early check-in possible?",
        "Can I request a specific room type?",
    ],
    qualification_fields=[
        QualificationField(key="check_in", label="Check-in date", type="date", required=True, display_order=0),
        QualificationField(key="check_out", label="Check-out date", type="date", required=True, display_order=1),
        QualificationField(
            key="guest_count",
            label="Number of guests",
            type="number",
            required=True,
            display_order=2,
        ),
        select_field(
            "room_preference",
            "Room preference",
            [("standard", "Standard"), ("deluxe", "Deluxe"), ("suite", "Suite")],
            required=False,
            order=3,
        ),
        QualificationField(key="amenities", label="Amenities of interest", type="long_text", display_order=4),
        QualificationField(
            key="special_requirements",
            label="Special requirements",
            type="long_text",
            display_order=5,
        ),
        *contact_fields(start_order=6),
    ],
    actions=["answer_questions", "capture_contact", "request_reservation", "request_human_handoff"],
    safety_rules=[
        "Only confirm availability, pricing, and policies from approved business content — "
        "never invent room availability.",
    ],
)

RESTAURANT = TemplateDefinition(
    key="restaurant",
    version=1,
    name="Restaurant",
    description="For restaurants handling reservation requests and menu questions.",
    icon="utensils",
    terminology={"visitor": "guest", "enquiry": "reservation request", "service": "table"},
    welcome_message="Hi there! I can help with reservations, menu questions, and hours.",
    suggested_questions=[
        "Can I book a table for tonight?",
        "Do you have vegetarian options?",
        "What are your hours?",
        "Do you take large party bookings?",
    ],
    qualification_fields=[
        QualificationField(key="party_size", label="Party size", type="number", required=True, display_order=0),
        QualificationField(
            key="reservation_date",
            label="Preferred date",
            type="date",
            required=True,
            display_order=1,
        ),
        QualificationField(
            key="reservation_time",
            label="Preferred time",
            type="time",
            required=True,
            display_order=2,
        ),
        QualificationField(
            key="dietary_requirements",
            label="Dietary requirements",
            type="long_text",
            display_order=3,
        ),
        QualificationField(key="occasion", label="Special occasion", type="short_text", display_order=4),
        *contact_fields(start_order=5),
    ],
    actions=["answer_questions", "capture_contact", "request_reservation", "request_human_handoff"],
    safety_rules=[
        "Only state menu items, prices, and allergen information confirmed in approved business content.",
    ],
)

AUTOMOTIVE = TemplateDefinition(
    key="automotive",
    version=1,
    name="Automotive Dealership",
    description="For dealerships handling new and used vehicle enquiries and test-drive requests.",
    icon="car",
    terminology={"visitor": "shopper", "enquiry": "vehicle enquiry", "service": "vehicle"},
    welcome_message="Welcome! I can help you find a vehicle, answer questions, or set up a test drive.",
    suggested_questions=[
        "What SUVs do you have in stock?",
        "Can I trade in my current vehicle?",
        "I'd like to book a test drive.",
        "What financing options are available?",
    ],
    qualification_fields=[
        QualificationField(
            key="vehicle_interest",
            label="Make/model of interest",
            type="short_text",
            display_order=0,
        ),
        select_field(
            "new_or_used",
            "New or used?",
            [("new", "New"), ("used", "Used")],
            required=False,
            order=1,
        ),
        QualificationField(key="budget_min", label="Minimum budget", type="currency", display_order=2),
        QualificationField(key="budget_max", label="Maximum budget", type="currency", display_order=3),
        QualificationField(key="trade_in", label="Do you have a trade-in?", type="boolean", display_order=4),
        QualificationField(
            key="preferred_test_drive_date",
            label="Preferred test-drive date",
            type="date",
            display_order=5,
        ),
        QualificationField(
            key="financing_required",
            label="Do you need financing?",
            type="boolean",
            display_order=6,
        ),
        *contact_fields(start_order=7),
    ],
    actions=[
        "answer_questions",
        "capture_contact",
        "qualify_lead",
        "request_test_drive",
        "request_human_handoff",
    ],
    safety_rules=[
        "Only confirm inventory, pricing, and financing terms from approved business content.",
        "Never guarantee loan or financing approval.",
    ],
)

LAW_FIRM = TemplateDefinition(
    key="law_firm",
    version=1,
    name="Law Firm",
    description="For law firms handling administrative client intake only — no legal advice is given.",
    icon="scale",
    terminology={
        "visitor": "prospective client",
        "enquiry": "consultation request",
        "service": "consultation",
    },
    welcome_message=(
        "Hello, thank you for reaching out. I can help schedule a consultation and answer general "
        "administrative questions. I'm not able to provide legal advice."
    ),
    suggested_questions=[
        "I'd like to schedule a consultation.",
        "What areas of law do you practice?",
        "What are your consultation fees?",
        "How quickly can someone speak with me?",
    ],
    qualification_fields=[
        QualificationField(
            key="matter_type",
            label="What type of matter is this?",
            type="short_text",
            required=True,
            display_order=0,
        ),
        QualificationField(key="brief_description", label="Brief description", type="long_text", display_order=1),
        select_field(
            "preferred_consultation_type",
            "Preferred consultation type",
            [("in_person", "In person"), ("phone", "Phone"), ("video", "Video")],
            required=False,
            order=2,
        ),
        select_field(
            "urgency",
            "How urgent is this matter?",
            [("urgent", "Urgent"), ("soon", "Soon"), ("no_rush", "No rush")],
            required=False,
            order=3,
        ),
        QualificationField(key="preferred_date", label="Preferred date", type="date", display_order=4),
        *contact_fields(start_order=5),
    ],
    actions=[
        "answer_questions",
        "capture_contact",
        "qualify_lead",
        "request_appointment",
        "request_human_handoff",
    ],
    safety_rules=list(MANDATORY_SAFETY_RULES["law_firm"]),
)

EDUCATION = TemplateDefinition(
    key="education",
    version=1,
    name="Education Provider",
    description="For schools, training providers, and course platforms handling enrollment enquiries.",
    icon="graduation-cap",
    terminology={
        "visitor": "prospective student",
        "enquiry": "enrollment enquiry",
        "service": "program",
    },
    welcome_message="Hi! I can help answer questions about our programs and enrollment.",
    suggested_questions=[
        "What programs do you offer?",
        "When does the next term start?",
        "Is this program available online?",
        "What are the admission requirements?",
    ],
    qualification_fields=[
        QualificationField(
            key="program_of_interest",
            label="Program of interest",
            type="short_text",
            required=True,
            display_order=0,
        ),
        select_field(
            "education_level",
            "Current education level",
            [
                ("high_school", "High school"),
                ("undergraduate", "Undergraduate"),
                ("graduate", "Graduate"),
                ("professional", "Working professional"),
            ],
            required=False,
            order=1,
        ),
        QualificationField(key="start_term", label="Preferred start term", type="short_text", display_order=2),
        select_field(
            "delivery_mode",
            "Preferred delivery mode",
            [("in_person", "In person"), ("online", "Online"), ("hybrid", "Hybrid")],
            required=False,
            order=3,
        ),
        select_field(
            "timeline",
            "Timeline",
            [
                ("immediate", "Ready now"),
                ("this_year", "This year"),
                ("exploring", "Just exploring"),
            ],
            required=False,
            order=4,
        ),
        *contact_fields(start_order=5),
    ],
    actions=[
        "answer_questions",
        "capture_contact",
        "qualify_lead",
        "request_callback",
        "request_human_handoff",
    ],
    safety_rules=[
        "Only confirm program details, dates, and requirements from approved business content.",
        "Never guarantee admission or scholarship outcomes.",
    ],
)

HOME_SERVICES = TemplateDefinition(
    key="home_services",
    version=1,
    name="Home Services Company",
    description="For plumbing, HVAC, electrical, cleaning, and similar home-service businesses.",
    icon="wrench",
    terminology={"visitor": "customer", "enquiry": "service request", "service": "job"},
    welcome_message="Hi! I can help schedule a service visit or answer questions about what we offer.",
    suggested_questions=[
        "I have a leak — can someone come out today?",
        "Do you offer free estimates?",
        "What areas do you service?",
        "Can I schedule a routine maintenance visit?",
    ],
    qualification_fields=[
        QualificationField(
            key="service_type",
            label="What service do you need?",
            type="short_text",
            required=True,
            display_order=0,
        ),
        select_field(
            "property_type",
            "Property type",
            [("residential", "Residential"), ("commercial", "Commercial")],
            required=False,
            order=1,
        ),
        QualificationField(key="issue_description", label="Describe the issue", type="long_text", display_order=2),
        QualificationField(key="preferred_date", label="Preferred date", type="date", display_order=3),
        select_field(
            "urgency",
            "Urgency",
            [("emergency", "Emergency"), ("soon", "Soon"), ("flexible", "Flexible")],
            required=False,
            order=4,
        ),
        QualificationField(key="address_or_area", label="Address or area", type="short_text", display_order=5),
        *contact_fields(start_order=6),
    ],
    actions=[
        "answer_questions",
        "capture_contact",
        "qualify_lead",
        "request_service_visit",
        "request_human_handoff",
    ],
    safety_rules=[
        "Only confirm pricing and availability from approved business content.",
        "For genuine emergencies (gas leaks, electrical hazards, flooding), direct the "
        "customer to call emergency services or an emergency line immediately.",
    ],
)

SAAS = TemplateDefinition(
    key="saas",
    version=1,
    name="SaaS Company",
    description="For B2B and B2C software companies handling product enquiries and demo requests.",
    icon="cloud",
    terminology={"visitor": "prospect", "enquiry": "product enquiry", "service": "plan"},
    welcome_message="Hi! I can answer questions about our product and help set up a demo.",
    suggested_questions=[
        "What does your product do?",
        "Can I get a demo?",
        "What's included in the free plan?",
        "Do you integrate with our existing tools?",
    ],
    qualification_fields=[
        QualificationField(key="company_name", label="Company name", type="short_text", display_order=0),
        select_field(
            "team_size",
            "Team size",
            [("1_10", "1–10"), ("11_50", "11–50"), ("51_200", "51–200"), ("200_plus", "200+")],
            required=False,
            order=1,
        ),
        QualificationField(key="use_case", label="Primary use case", type="long_text", display_order=2),
        QualificationField(
            key="current_solution",
            label="Current solution (if any)",
            type="short_text",
            display_order=3,
        ),
        select_field(
            "timeline",
            "Timeline",
            [
                ("immediate", "Ready now"),
                ("this_quarter", "This quarter"),
                ("exploring", "Just exploring"),
            ],
            required=False,
            order=4,
        ),
        QualificationField(key="budget_range", label="Budget range", type="short_text", display_order=5),
        *contact_fields(start_order=6),
    ],
    actions=[
        "answer_questions",
        "capture_contact",
        "qualify_lead",
        "request_demo",
        "request_human_handoff",
    ],
    safety_rules=[
        "Only state pricing, features, and integrations confirmed in approved business content.",
    ],
)

CUSTOM = TemplateDefinition(
    key="custom",
    version=1,
    name="Custom / Other Business",
    description="A minimal starting point for any business type — define your own qualification fields.",
    icon="settings",
    terminology={"visitor": "visitor", "enquiry": "enquiry", "service": "service"},
    welcome_message="Hi! How can I help you today?",
    suggested_questions=[
        "What services do you offer?",
        "What are your hours?",
        "How can I get in touch with your team?",
    ],
    qualification_fields=list(contact_fields(start_order=0)),
    actions=["answer_questions", "capture_contact", "qualify_lead", "request_human_handoff"],
    safety_rules=[
        "Only answer using approved business content — say so clearly when information is not available.",
    ],
)

ALL_TEMPLATES: list[TemplateDefinition] = [
    REAL_ESTATE,
    CLINIC,
    HOTEL,
    RESTAURANT,
    AUTOMOTIVE,
    LAW_FIRM,
    EDUCATION,
    HOME_SERVICES,
    SAAS,
    CUSTOM,
]
