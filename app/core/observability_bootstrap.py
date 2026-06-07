from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import FastAPI, Response

from app.config import (
    get_otel_enabled,
    get_otel_endpoint,
    get_otel_environment,
    get_otel_protocol,
    get_otel_sample_ratio,
    get_otel_service_name,
    get_prometheus_enabled,
    get_prometheus_export_mode,
    get_prometheus_metrics_path,
)

logger = logging.getLogger("app.observability")


class ObservabilityConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ObservabilityBootstrapState:
    otel_enabled: bool
    prometheus_enabled: bool
    metrics_path: str | None = None


_BOOTSTRAPPED_APPS: set[int] = set()


def configure_external_observability(app: FastAPI) -> ObservabilityBootstrapState:
    app_id = id(app)
    if app_id in _BOOTSTRAPPED_APPS:
        return ObservabilityBootstrapState(
            otel_enabled=get_otel_enabled(),
            prometheus_enabled=get_prometheus_enabled(),
            metrics_path=get_prometheus_metrics_path() if get_prometheus_enabled() else None,
        )

    if get_otel_enabled():
        _configure_otel(app)
    if get_prometheus_enabled():
        _configure_prometheus(app)

    _BOOTSTRAPPED_APPS.add(app_id)
    return ObservabilityBootstrapState(
        otel_enabled=get_otel_enabled(),
        prometheus_enabled=get_prometheus_enabled(),
        metrics_path=get_prometheus_metrics_path() if get_prometheus_enabled() else None,
    )


def reset_observability_bootstrap_for_tests() -> None:
    _BOOTSTRAPPED_APPS.clear()


def _configure_otel(app: FastAPI) -> None:
    endpoint = get_otel_endpoint()
    if not endpoint:
        raise ObservabilityConfigurationError("OTEL_ENABLED=true requires OTEL_EXPORTER_OTLP_ENDPOINT.")

    try:
        from opentelemetry import metrics
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import DEPLOYMENT_ENVIRONMENT, SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    except ImportError as exc:
        raise ObservabilityConfigurationError(
            "OpenTelemetry export requires opentelemetry-sdk, opentelemetry-exporter-otlp, "
            "and opentelemetry-instrumentation-fastapi."
        ) from exc

    protocol = get_otel_protocol()
    if protocol not in {"http/protobuf", "http"}:
        raise ObservabilityConfigurationError(
            f"Unsupported OTEL_EXPORTER_OTLP_PROTOCOL '{protocol}'. Use http/protobuf for this backend."
        )

    resource = Resource.create(
        {
            SERVICE_NAME: get_otel_service_name(),
            DEPLOYMENT_ENVIRONMENT: get_otel_environment(),
        }
    )
    current_provider = trace.get_tracer_provider()
    if current_provider.__class__.__name__ == "ProxyTracerProvider":
        provider = TracerProvider(resource=resource, sampler=TraceIdRatioBased(get_otel_sample_ratio()))
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
    else:
        logger.info("OpenTelemetry tracer provider already configured; reusing existing provider.")

    current_meter_provider = metrics.get_meter_provider()
    if current_meter_provider.__class__.__name__ == "_ProxyMeterProvider":
        metric_exporter = OTLPMetricExporter(endpoint=_metric_endpoint(endpoint))
        metric_reader = PeriodicExportingMetricReader(metric_exporter)
        metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))
    else:
        logger.info("OpenTelemetry meter provider already configured; reusing existing provider.")

    FastAPIInstrumentor.instrument_app(app)


def _configure_prometheus(app: FastAPI) -> None:
    mode = get_prometheus_export_mode()
    if mode != "endpoint":
        raise ObservabilityConfigurationError(
            f"Unsupported PROMETHEUS_EXPORT_MODE '{mode}'. Use endpoint for this backend."
        )

    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    except ImportError as exc:
        raise ObservabilityConfigurationError("Prometheus export requires prometheus-client.") from exc

    metrics_path = get_prometheus_metrics_path()
    existing_paths = {getattr(route, "path", None) for route in app.routes}
    if metrics_path in existing_paths:
        return

    async def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.add_api_route(metrics_path, metrics, methods=["GET"], include_in_schema=False)


def _metric_endpoint(trace_endpoint: str) -> str:
    if trace_endpoint.endswith("/v1/traces"):
        return f"{trace_endpoint[:-len('/v1/traces')]}/v1/metrics"
    return trace_endpoint
