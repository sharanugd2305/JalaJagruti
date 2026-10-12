"""Error types and shared status vocabulary."""


class JalaJagrutiError(RuntimeError):
    """Base class: every error carries an actionable message."""


class ConfigurationError(JalaJagrutiError):
    pass


class DataValidationError(JalaJagrutiError):
    pass


class ServiceError(JalaJagrutiError):
    """External API failure (after retries)."""

    def __init__(self, service: str, message: str, hint: str | None = None):
        self.service = service
        self.hint = hint
        full = f"[{service}] {message}"
        if hint:
            full += f"\n  How to fix: {hint}"
        super().__init__(full)


class AuthenticationError(ServiceError):
    pass


class InsufficientDataError(JalaJagrutiError):
    pass


# ---- status vocabulary used across outputs -----------------------------------
INSUFFICIENT = "INSUFFICIENT_INPUT_DATA"

PRED_STATUS_PREDICTED = "PREDICTED_OUT_OF_SAMPLE"          # 2025, compared with actuals
PRED_STATUS_FORECAST = "FORECAST_WITHIN_VALIDATED_HORIZON"
PRED_STATUS_FORECAST_EXTRAP = "FORECAST_BEYOND_VALIDATED_HORIZON"

SPATIAL_IN_WARD = "STATION_IN_WARD"
SPATIAL_IDW = "INTERPOLATED_IDW"
SPATIAL_NONE = "NO_STATION_WITHIN_RANGE"
