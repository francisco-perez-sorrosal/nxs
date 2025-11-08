"""
QueryManager - Manages query queue and sequential processing.

This module provides a queue-based system for processing user queries
in FIFO order, ensuring results are displayed in submission order.
"""

import asyncio
from collections import namedtuple
from typing import Callable, Awaitable
from nxs.logger import get_logger

logger = get_logger("query_manager")

# Query item for the queue
QueryItem = namedtuple("QueryItem", ["query", "query_id"])


class QueryManager:
    """
    Manages query queue and sequential processing.
    
    Ensures queries are processed in FIFO order and results are displayed
    in submission order, even if processing times vary.
    """

    def __init__(self, processor: Callable[[str, int], Awaitable[None]]):
        """
        Initialize the QueryManager.

        Args:
            processor: Async function that processes queries.
                      Takes (query: str, query_id: int) as arguments.
        """
        self._query_processor = processor
        self._query_queue: asyncio.Queue[QueryItem] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._next_query_id = 0
        self._running = False

    async def start(self) -> None:
        """
        Start the query worker task.
        
        This begins processing queries from the queue sequentially.
        """
        if self._running:
            logger.warning("QueryManager already running")
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("QueryManager started")

    async def stop(self) -> None:
        """
        Stop the query worker task and wait for it to finish.
        
        This will cancel any pending work and clean up resources.
        """
        if not self._running:
            return

        self._running = False
        logger.info("Stopping QueryManager...")

        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                logger.info("QueryManager worker task cancelled successfully")

        logger.info("QueryManager stopped")

    async def enqueue(self, query: str) -> int:
        """
        Enqueue a query for processing.

        Args:
            query: The user query text to process

        Returns:
            Sequential query ID for this query

        Raises:
            RuntimeError: If the manager is not running
        """
        if not self._running:
            raise RuntimeError("QueryManager is not running. Call start() first.")

        # Assign a sequential ID to this query for FIFO ordering
        query_id = self._next_query_id
        self._next_query_id += 1

        # Enqueue the query
        query_item = QueryItem(query=query, query_id=query_id)
        await self._query_queue.put(query_item)
        logger.info(f"Enqueued query (query_id={query_id}): '{query[:50]}{'...' if len(query) > 50 else ''}'")

        return query_id

    @property
    def is_running(self) -> bool:
        """Check if the QueryManager is running."""
        return self._running

    @property
    def queue_size(self) -> int:
        """Get the current number of pending queries in the queue."""
        return self._query_queue.qsize()

    async def _worker(self) -> None:
        """
        Worker task that processes queries from the queue sequentially.
        
        This runs in a loop, processing queries one at a time to ensure
        FIFO ordering of results.
        """
        logger.info("QueryManager worker started")

        while self._running:
            try:
                # Wait for a query from the queue (blocks until one is available)
                query_item = await self._query_queue.get()
                logger.info(
                    f"Worker picked up query (query_id={query_item.query_id}): "
                    f"'{query_item.query[:50]}{'...' if len(query_item.query) > 50 else ''}'"
                )

                # Process the query (this will block until it completes)
                # Since we process sequentially, results will naturally be in FIFO order
                try:
                    await self._query_processor(query_item.query, query_item.query_id)
                    logger.info(f"Query processing completed (query_id={query_item.query_id})")
                except Exception as e:
                    logger.error(f"Error processing query (query_id={query_item.query_id}): {e}", exc_info=True)
                    # Continue processing other queries even if one fails

                # Mark the query as done
                self._query_queue.task_done()

            except asyncio.CancelledError:
                logger.info("QueryManager worker task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in QueryManager worker: {e}", exc_info=True)
                # Continue processing other queries even if one fails
                try:
                    self._query_queue.task_done()
                except ValueError:
                    # task_done() called more times than there were items placed in the queue
                    pass

        logger.info("QueryManager worker stopped")
