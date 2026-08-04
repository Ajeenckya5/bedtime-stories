"""Typed errors. Each maps to a distinct operational response."""

class BedtimeError(Exception):
    """Base class. Anything raised by this package derives from it."""
    user_message = "Something went wrong while writing your story."


class ConfigError(BedtimeError):
    user_message = "The story service is not configured correctly."


class ProviderError(BedtimeError):
    """Upstream model failure that survived all retries."""
    user_message = "The storyteller is having trouble right now. Please try again."


class RateLimitedError(ProviderError):
    user_message = "Too many stories at once - please wait a moment and try again."


class CircuitOpenError(ProviderError):
    """Fail fast: the upstream is known-bad, do not add load to it."""
    user_message = "The storyteller is resting. Please try again in a minute."


class BudgetExceededError(BedtimeError):
    user_message = "The story budget for today has been used up."


class StructuredOutputError(BedtimeError):
    """The model returned something we could not parse into the schema even
    after a repair attempt."""
    user_message = "The storyteller got confused. Please try again."


class UnsafeRequestError(BedtimeError):
    """Input guardrail refusal - carries a child-appropriate redirect."""
    def __init__(self, message: str, user_message: str):
        super().__init__(message)
        self.user_message = user_message
