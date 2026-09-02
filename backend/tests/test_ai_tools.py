from app.ai.tools.base import ToolContext, execute_tool
from app.ai.tools.registry import PHASE_4_TOOL_NAMES, TOOL_REGISTRY
from app.models.business_location import BusinessLocation
from app.models.service import Service
from app.repositories.business_location import BusinessLocationRepository
from app.repositories.service import ServiceRepository
from sqlalchemy.orm import Session

from tests.factories import make_tenant_with_owner


def _context(tenant_id) -> ToolContext:
    import uuid

    return ToolContext(tenant_id=tenant_id, receptionist_id=uuid.uuid4())


class TestToolGating:
    def test_only_registered_tools_are_ever_exposed(self):
        assert PHASE_4_TOOL_NAMES == TOOL_REGISTRY.names()

    def test_definitions_only_include_allowed_names(self):
        definitions = TOOL_REGISTRY.definitions(allowed_names={"list_services"})
        assert [d.name for d in definitions] == ["list_services"]

    def test_unknown_tool_name_is_rejected(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        result = execute_tool(
            TOOL_REGISTRY,
            call_id="c1",
            name="delete_everything",
            arguments={},
            allowed_names=PHASE_4_TOOL_NAMES,
            db=db_session,
            context=_context(tenant.id),
        )
        assert result.status == "error"

    def test_a_tool_not_in_allowed_names_is_rejected_even_if_registered(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        result = execute_tool(
            TOOL_REGISTRY,
            call_id="c1",
            name="list_services",
            arguments={},
            allowed_names=frozenset(),  # nothing enabled for this tenant/turn
            db=db_session,
            context=_context(tenant.id),
        )
        assert result.status == "error"
        assert "not available" in (result.error_message or "").lower()


class TestToolInputValidation:
    def test_invalid_input_is_rejected_not_executed(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        result = execute_tool(
            TOOL_REGISTRY,
            call_id="c1",
            name="search_business_knowledge",
            arguments={},  # missing required "query"
            allowed_names=PHASE_4_TOOL_NAMES,
            db=db_session,
            context=_context(tenant.id),
        )
        assert result.status == "error"

    def test_unexpected_extra_fields_are_rejected(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        result = execute_tool(
            TOOL_REGISTRY,
            call_id="c1",
            name="search_business_knowledge",
            arguments={"query": "hours", "tenant_id": "should-be-ignored-or-rejected"},
            allowed_names=PHASE_4_TOOL_NAMES,
            db=db_session,
            context=_context(tenant.id),
        )
        # The input model has no tenant_id field at all, and forbids extras
        # — a provider-supplied tenant_id can never reach the tool.
        assert result.status == "error"

    def test_valid_input_executes_successfully(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        result = execute_tool(
            TOOL_REGISTRY,
            call_id="c1",
            name="search_business_knowledge",
            arguments={"query": "hours"},
            allowed_names=PHASE_4_TOOL_NAMES,
            db=db_session,
            context=_context(tenant.id),
        )
        assert result.status == "ok"
        assert "results" in result.output


class TestListServicesTool:
    def test_returns_only_active_services_for_this_tenant(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        repo = ServiceRepository(db_session, tenant.id)
        repo.add(Service(tenant_id=tenant.id, name="Haircut", is_active=True))
        repo.add(Service(tenant_id=tenant.id, name="Retired Service", is_active=False))
        db_session.flush()

        result = execute_tool(
            TOOL_REGISTRY, call_id="c1", name="list_services", arguments={}, allowed_names=PHASE_4_TOOL_NAMES,
            db=db_session, context=_context(tenant.id),
        )
        names = [s["name"] for s in result.output["services"]]
        assert "Haircut" in names
        assert "Retired Service" not in names

    def test_cannot_see_another_tenants_services(self, db_session: Session):
        tenant_a, _, _ = make_tenant_with_owner(db_session, tenant_name="A")
        tenant_b, _, _ = make_tenant_with_owner(db_session, tenant_name="B")
        secret_service = Service(tenant_id=tenant_b.id, name="B's Secret Service", is_active=True)
        ServiceRepository(db_session, tenant_b.id).add(secret_service)
        db_session.flush()

        result = execute_tool(
            TOOL_REGISTRY, call_id="c1", name="list_services", arguments={}, allowed_names=PHASE_4_TOOL_NAMES,
            db=db_session, context=_context(tenant_a.id),
        )
        names = [s["name"] for s in result.output["services"]]
        assert "B's Secret Service" not in names


class TestGetBusinessHoursTool:
    def test_returns_the_primary_locations_hours(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        repo = BusinessLocationRepository(db_session, tenant.id)
        hours = {"days": [{"day_of_week": 0, "closed": False, "intervals": [{"start": "09:00", "end": "17:00"}]}]}
        repo.add(
            BusinessLocation(
                tenant_id=tenant.id, name="Main Office", is_primary=True, is_active=True, working_hours=hours
            )
        )
        db_session.flush()

        result = execute_tool(
            TOOL_REGISTRY, call_id="c1", name="get_business_hours", arguments={}, allowed_names=PHASE_4_TOOL_NAMES,
            db=db_session, context=_context(tenant.id),
        )
        assert result.status == "ok"
        assert result.output["days"][0]["day_name"] == "Monday"

    def test_no_locations_returns_empty_days_not_an_error(self, db_session: Session):
        tenant, _, _ = make_tenant_with_owner(db_session)
        result = execute_tool(
            TOOL_REGISTRY, call_id="c1", name="get_business_hours", arguments={}, allowed_names=PHASE_4_TOOL_NAMES,
            db=db_session, context=_context(tenant.id),
        )
        assert result.status == "ok"
        assert result.output["days"] == []


class TestWriteToolsAreNotExecutable:
    def test_no_write_capable_tool_exists_in_phase_4(self):
        forbidden_names = {
            "create_lead",
            "create_contact",
            "request_appointment",
            "request_viewing",
            "request_reservation",
            "request_demo",
            "request_callback",
            "request_human_handoff",
        }
        assert forbidden_names.isdisjoint(TOOL_REGISTRY.names())
