"""
QueryQueue - FIFO queue for sequential query processing.

This module provides a queue-based system for processing user queries
in FIFO order, ensuring results are displayed in submission order.

Implementation:
    Uses AsyncQueueProcessor for background processing, eliminating code
    duplication with StatusQueue and establishing a reusable pattern.
"""

from collections import namedtuple
from typing import Awaitable, Callable

from nxs.logger import get_logger
from nxs.presentation.services.queue_processor import AsyncQueueProcessor

logger = get_logger("query_queue")

# Query item for the queue
QueryItem = namedtuple("QueryItem", ["query", "query_id"])


class QueryQueue:
    """
    FIFO queue for sequential query processing.

    Ensures queries are processed in FIFO order and results are displayed
    in submission order, even if processing times vary.

    This class wraps AsyncQueueProcessor with query-specific functionality,
    including sequential ID generation and query-specific error handling.
    """

    def __init__(self, processor: Callable[[str, int], Awaitable[None]]):
        """
        Initialize the QueryQueue.

        Args:
            processor: Async function that processes queries.
                      Takes (query: str, query_id: int) as arguments.
        """
        self._query_processor = processor
        self._next_query_id = 0

        # Define async processor that handles query items
        async def process_query_item(item: QueryItem) -> None:
            """Process a query item with ID."""
            await self._query_processor(item.query, item.query_id)

        # Create the underlying queue processor
        self._processor = AsyncQueueProcessor[QueryItem](
            processor=process_query_item,
            name="QueryQueue",
        )

    async def start(self) -> None:
        """
        Start the query worker task.

        This begins processing queries from the queue sequentially.
        """
        await self._processor.start()

    async def stop(self) -> None:
        """
        Stop the query worker task and wait for it to finish.

        This will cancel any pending work and clean up resources.
        """
        await self._processor.stop()

    async def enqueue(self, query: str) -> int:
        """
        Enqueue a query for processing.

        Args:
            query: The user query text to process

        Returns:
            Sequential query ID for this query

        Raises:
            RuntimeError: If the queue is not running
        """
        # Assign a sequential ID to this query for FIFO ordering
        query_id = self._next_query_id
        self._next_query_id += 1

        # Enqueue the query
        query_item = QueryItem(query=query, query_id=query_id)
        await self._processor.enqueue(query_item)
        logger.info(f"Enqueued query (query_id={query_id}): '{query[:50]}{'...' if len(query) > 50 else ''}'")

        return query_id

    @property
    def is_running(self) -> bool:
        """Check if the QueryQueue is running."""
        return self._processor.is_running

    @property
    def queue_size(self) -> int:
        """Get the current number of pending queries in the queue."""
        return self._processor.queue_size
