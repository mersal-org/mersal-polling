from collections.abc import Callable

from mersal.messages import TransportMessage
from mersal.retry import ErrorHandler
from mersal.transport import TransactionContext
from mersal_polling.poller import Poller, ProblemDetails

__all__ = ("ErrorHandlerPollerWrapper",)


class ErrorHandlerPollerWrapper(ErrorHandler):
    """Wraps an error handler to notify the poller when messages go to DLQ.

    This wrapper converts technical exceptions into structured ProblemDetails
    that are suitable for returning to API clients. The actual exception is
    still sent to the underlying error handler (for logging, DLQ, etc.) but
    the poller receives a sanitized error representation.
    """

    def __init__(
        self,
        poller: Poller,
        error_handler: ErrorHandler,
        problem_factory: Callable[[Exception, TransportMessage], ProblemDetails] | None = None,
    ) -> None:
        """Initialize the wrapper.

        Args:
            poller: The poller to notify when messages fail
            error_handler: The underlying error handler (e.g., DLQ handler)
            problem_factory: Optional factory to convert exceptions to ProblemDetails.
                           If not provided, uses a generic technical error.
        """
        self.poller = poller
        self.error_handler = error_handler
        self.problem_factory = problem_factory or self._default_problem_factory

    def _default_problem_factory(self, exception: Exception, message: TransportMessage) -> ProblemDetails:
        """Convert technical exceptions to generic ProblemDetails.

        This default implementation returns a generic 500 error without exposing
        internal exception details to API clients.

        Args:
            exception: The technical exception that occurred
            message: The message that failed

        Returns:
            A generic ProblemDetails for technical errors
        """
        return ProblemDetails(
            type="https://problems.mersal.dev/technical-error",
            title="Technical Error",
            status=500,
            detail="An unexpected error occurred while processing your request. Please try again later.",
            instance=f"/messages/{message.headers.message_id}",
            extensions={},
        )

    async def handle_poison_message(
        self,
        message: TransportMessage,
        transaction_context: TransactionContext,
        exception: Exception,
    ) -> None:
        """Handle a poison message by sending to DLQ and notifying the poller.

        Args:
            message: The poison message
            transaction_context: The transaction context
            exception: The exception that caused the message to be poisoned
        """
        # First, delegate to the underlying error handler (DLQ, logging, etc.)
        await self.error_handler.handle_poison_message(message, transaction_context, exception)

        # Convert the exception to a ProblemDetails for the poller/API client
        problem = self.problem_factory(exception, message)

        # Notify the poller with the structured error
        await self.poller.push(message.headers.message_id, status="failed", problem=problem)
