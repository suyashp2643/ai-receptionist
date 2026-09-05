"""Tenant-scoped integration health/observability summary.

Every metric below is defined precisely — exact numerator, denominator,
and time range — because a vague "success rate" or "latency" number is
worse than none. Nothing here ever counts another tenant's rows: every
query filters by `tenant_id` explicitly (see
app/repositories/integration.py's methods this module calls), and the
whole summary is built from a small, fixed number of aggregate queries —
never one query per connection or per event (see
tests/test_phase8_integration_health_performance.py for the exact count,
measured against a seeded volume).

This module never marks a connector "healthy" merely because the main API
responded — every health signal here comes from this tenant's own stored
IntegrationConnection/IntegrationOutboxEvent/IntegrationDeliveryAttempt
rows, which only change when a real delivery attempt (or lack of one) is
recorded.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import Settings
from app.models.enums import IntegrationConnectionStatus
from app.repositories.integration import IntegrationDeliveryAttemptRepository, IntegrationOutboxEventRepository
from app.services.integration_connection_service import list_connections

DEFAULT_WINDOW_HOURS = 24
MAX_WINDOW_HOURS = 24 * 7  # bounds how far back the windowed queries ever look
LATENCY_SAMPLE_LIMIT = 500  # bounds the raw-duration fetch used for percentile estimation
STALE_BACKLOG_THRESHOLD_SECONDS = 3600  # 1 hour
REPEATED_FAILURE_THRESHOLD = 3  # matches outbox_worker_service's own VERIFIED->FAILING promotion threshold


@dataclass(frozen=True)
class ConnectionStatusBreakdown:
    """A strict partition of every one of this tenant's connections into
    exactly one bucket — `active` means CONFIGURED or VERIFIED (a
    deliverable connector that is not currently failing), `paused` and
    `failing` and `disabled` map 1:1 to their own IntegrationConnectionStatus
    value. `active + paused + failing + disabled == total`, always."""

    active: int
    paused: int
    failing: int
    disabled: int
    total: int


@dataclass(frozen=True)
class DeliveryLatencySummary:
    """p50/p95 of successful delivery duration_ms within the reporting
    window. `None` for a field (never 0) when there is no successful
    delivery in the window to compute it from. Computed from a
    LIMIT-capped sample of up to `LATENCY_SAMPLE_LIMIT` of the most recent
    successful deliveries in the window (nearest-rank method), not the
    full set — an explicit, documented approximation so this endpoint's
    query cost never scales with a busy tenant's real delivery volume."""

    p50_ms: float | None
    p95_ms: float | None
    sample_size: int


@dataclass(frozen=True)
class HealthWarning:
    code: str
    message: str
    connection_id: uuid.UUID | None = None


@dataclass(frozen=True)
class TenantIntegrationHealth:
    window_hours: int
    connections: ConnectionStatusBreakdown
    pending_events: int
    retry_backlog: int
    oldest_pending_age_seconds: float | None
    dead_letter_count: int
    successful_deliveries: int
    failed_deliveries: int
    success_rate: float | None
    latency: DeliveryLatencySummary
    last_success_at: datetime | None
    last_failure_at: datetime | None
    warnings: list[HealthWarning] = field(default_factory=list)


def _percentile(sorted_values: list[int], fraction: float) -> float | None:
    if not sorted_values:
        return None
    # Nearest-rank method — simple, deterministic, no interpolation
    # ambiguity to document.
    index = max(0, min(len(sorted_values) - 1, int(round(fraction * (len(sorted_values) - 1)))))
    return float(sorted_values[index])


def get_tenant_integration_health(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    settings: Settings,
    window_hours: int = DEFAULT_WINDOW_HOURS,
) -> TenantIntegrationHealth:
    window_hours = max(1, min(window_hours, MAX_WINDOW_HOURS))
    now = datetime.now(UTC)
    since = now - timedelta(hours=window_hours)

    # Query 1: this tenant's own connection rows (bounded — see
    # list_connections' own limit=200 cap). Every status-breakdown count
    # AND every connection-level warning below comes from this single
    # fetch — never a per-connection follow-up query.
    connections = list_connections(db, tenant_id)

    active = paused = failing = disabled = 0
    warnings: list[HealthWarning] = []
    for connection in connections:
        if connection.status == IntegrationConnectionStatus.PAUSED:
            paused += 1
        elif connection.status == IntegrationConnectionStatus.FAILING:
            failing += 1
        elif connection.status == IntegrationConnectionStatus.DISABLED:
            disabled += 1
        else:
            active += 1

        if connection.failure_count >= REPEATED_FAILURE_THRESHOLD:
            warnings.append(
                HealthWarning(
                    code="repeated_failures",
                    message=(f"'{connection.name}' has failed {connection.failure_count} consecutive deliveries."),
                    connection_id=connection.id,
                )
            )
        if connection.status == IntegrationConnectionStatus.DISABLED:
            warnings.append(
                HealthWarning(
                    code="disabled_connector", message=f"'{connection.name}' is disabled.", connection_id=connection.id
                )
            )
        if connection.signing_secret_ciphertext and not settings.integration_encryption_key:
            warnings.append(
                HealthWarning(
                    code="missing_encryption_configuration",
                    message=(
                        f"'{connection.name}' has a stored signing secret, but "
                        "INTEGRATION_ENCRYPTION_KEY is not configured — deliveries will fail."
                    ),
                    connection_id=connection.id,
                )
            )
        elif (
            connection.signing_secret_key_version is not None
            and connection.signing_secret_key_version != settings.integration_encryption_key_version
        ):
            warnings.append(
                HealthWarning(
                    code="unsupported_key_version",
                    message=(
                        f"'{connection.name}''s signing secret was encrypted under key version "
                        f"{connection.signing_secret_key_version}, but the configured key is version "
                        f"{settings.integration_encryption_key_version} — it cannot be decrypted."
                    ),
                    connection_id=connection.id,
                )
            )

    connection_breakdown = ConnectionStatusBreakdown(
        active=active, paused=paused, failing=failing, disabled=disabled, total=len(connections)
    )

    # Query 2: outbox status counts for this tenant (GROUP BY).
    outbox_repo = IntegrationOutboxEventRepository(db)
    status_counts = outbox_repo.status_counts_for_tenant(tenant_id)
    pending_events = status_counts.get("pending", 0)
    dead_letter_count = status_counts.get("dead_letter", 0)

    # Query 3: retry backlog + oldest pending age (one aggregate row).
    retry_backlog, oldest_pending_at = outbox_repo.pending_backlog_summary(tenant_id)
    oldest_pending_age_seconds = (now - oldest_pending_at).total_seconds() if oldest_pending_at else None

    if oldest_pending_age_seconds is not None and oldest_pending_age_seconds > STALE_BACKLOG_THRESHOLD_SECONDS:
        warnings.append(
            HealthWarning(
                code="stale_backlog",
                message=(
                    f"The oldest pending event has been waiting " f"{int(oldest_pending_age_seconds // 60)} minutes."
                ),
            )
        )

    attempt_repo = IntegrationDeliveryAttemptRepository(db, tenant_id)

    # Query 4: success/failure attempt counts within the window (one
    # aggregate row).
    successful_deliveries, failed_deliveries = attempt_repo.window_summary(since=since)
    total_attempts = successful_deliveries + failed_deliveries
    success_rate = (successful_deliveries / total_attempts) if total_attempts > 0 else None

    # Query 5: bounded raw-duration sample for percentile estimation.
    duration_sample = sorted(attempt_repo.success_duration_sample(since=since, limit=LATENCY_SAMPLE_LIMIT))
    latency = DeliveryLatencySummary(
        p50_ms=_percentile(duration_sample, 0.5),
        p95_ms=_percentile(duration_sample, 0.95),
        sample_size=len(duration_sample),
    )

    # Query 6: last success / last failure, all-time (one aggregate row).
    last_success_at, last_failure_at = attempt_repo.last_success_and_failure()

    return TenantIntegrationHealth(
        window_hours=window_hours,
        connections=connection_breakdown,
        pending_events=pending_events,
        retry_backlog=retry_backlog,
        oldest_pending_age_seconds=oldest_pending_age_seconds,
        dead_letter_count=dead_letter_count,
        successful_deliveries=successful_deliveries,
        failed_deliveries=failed_deliveries,
        success_rate=success_rate,
        latency=latency,
        last_success_at=last_success_at,
        last_failure_at=last_failure_at,
        warnings=warnings,
    )
