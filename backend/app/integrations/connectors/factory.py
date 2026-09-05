"""The single place a connector instance is constructed from a
connector_type. Connectors are stateless, so one instance per type is
reused rather than constructed per call."""

from __future__ import annotations

from app.integrations.connectors.base import Connector
from app.integrations.connectors.mock import MockConnector
from app.integrations.connectors.revenue_brain import RevenueBrainConnector
from app.integrations.connectors.sales_employee import SalesEmployeeConnector
from app.integrations.connectors.webhook import WebhookConnector
from app.models.enums import IntegrationConnectorType

_CONNECTORS: dict[IntegrationConnectorType, Connector] = {
    IntegrationConnectorType.MOCK: MockConnector(),
    IntegrationConnectorType.WEBHOOK: WebhookConnector(),
    IntegrationConnectorType.REVENUE_BRAIN: RevenueBrainConnector(),
    IntegrationConnectorType.SALES_EMPLOYEE: SalesEmployeeConnector(),
}


def get_connector(connector_type: IntegrationConnectorType) -> Connector:
    return _CONNECTORS[connector_type]
