"""
Generic async queue processor for sequential background processing.

This module provides a reusable pattern for processing items asynchronously
in FIFO order with a background worker task. It eliminates code duplication
between StatusQueue, QueryQueue, and future queue-based services.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Generic, TypeVar

from nxs.logger import get_logger

logger = get_logger("queue_processor")

T = TypeVar("T")


@dataclass
class QueueItem(Generic[T]):
    """
    Generic queue item wrapping a payload with optional metadata.

    The metadata dict can be used to pass additional context without
    modifying the payload type.
    """

    payload: T
    metadata: dict[str, Any] = field(default_factory=dict)


class AsyncQueueProcessor(Generic[T]):
    """
    Generic async FIFO queue processor with background worker.

    Processes items sequentially in submission order, ensuring FIFO semantics.
    Supports both synchronous and asynchronous processors.

    Type Parameters:
        T: Type of items to process

    Example:
        ```python
        # Synchronous processor
        def process_status(update: StatusUpdate) -> None:
            panel.apply_update(update)

        status_processor = AsyncQueueProcessor[StatusUpdate](
            processor=process_status,
            name="StatusQueue"
        )

        # Asynchronous processor
        async def process_query(item: QueryItem) -> None:
            await agent.process(item.query)

        query_processor = AsyncQueueProcessor[QueryItem](
            processor=process_query,
            name="QueryQueue"
        )
        ```

    Lifecycle:
        1. Create instance with processor function
        2. Call `start()` to begin background worker
        3. Call `enqueue(item)` to add items for processing
        4. Call `stop()` to gracefully shutdown

    Error Handling:
        - Processor exceptions are logged but don't stop the worker
        - Worker continues processing remaining items after errors
        - Graceful cancellation on stop()
    """

    def __init__(
        self,
        processor: Callable[[T], None] | Callable[[T], Awaitable[None]],
        *,
        name: str = "AsyncQueue",
        max_size: int = 0,
    ):
        """
        Initialize the async queue processor.

        Args:
            processor: Function or coroutine to process each item.
                      Receives item payload of type T.
                      Exceptions are logged but don't stop processing.
            name: Human-readable name for logging (default: "AsyncQueue")
            max_size: Maximum queue size. 0 = unlimited (default: 0)

        Note:
            The processor is automatically detected as sync or async using
            asyncio.iscoroutinefunction(). Both types are supported.
        """
        self._processor = processor
        self._name = name
        self._queue: asyncio.Queue[QueueItem[T]] = asyncio.Queue(maxsize=max_size)
        self._worker_task: asyncio.Task | None = None
        self._running = False
        self._is_async_processor = asyncio.iscoroutinefunction(processor)

        logger.debug(
            f"Created {self._name} (processor_type={'async' if self._is_async_processor else 'sync'}, "
            f"max_size={'unlimited' if max_size == 0 else max_size})"
        )

    async def start(self) -> None:
        """
        Start the background worker task.

        This begins processing items from the queue asynchronously.
        Items are processed sequentially in FIFO order.

        Raises:
            No exceptions - already running is logged as warning
        """
        if self._running:
            logger.warning(f"{self._name} already running")
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        logger.info(f"{self._name} started")

    async def stop(self) -> None:
        """
        Stop the background worker task and wait for cleanup.

        This performs graceful shutdown:
        1. Sets running flag to False
        2. Cancels worker task if running
        3. Waits for worker to finish cleanup

        After stop(), the processor can be restarted with start().
        """
        if not self._running:
            return

        self._running = False
        logger.info(f"Stopping {self._name}...")

        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                logger.info(f"{self._name} worker cancelled successfully")

        logger.info(f"{self._name} stopped")

    async def enqueue(self, item: T, **metadata: Any) -> None:
        """
        Enqueue an item for processing.

        Items are processed in FIFO order by the background worker.

        Args:
            item: The payload to process (type T)
            **metadata: Optional metadata attached to the queue item.
                       Not passed to processor, but available for debugging.

        Raises:
            RuntimeError: If the processor is not running. Call start() first.
            asyncio.QueueFull: If max_size is set and queue is full.

        Example:
            ```python
            await processor.enqueue(status_update, source="agent")
            await processor.enqueue(query_item, user_id=123)
            ```
        """
        if not self._running:
            raise RuntimeError(f"{self._name} is not running. Call start() first.")

        queue_item = QueueItem(payload=item, metadata=metadata)
        await self._queue.put(queue_item)
        logger.debug(f"{self._name}: Enqueued item (queue_size={self._queue.qsize()})")

    @property
    def is_running(self) -> bool:
        """Check if the processor is currently running."""
        return self._running

    @property
    def queue_size(self) -> int:
        """Get the current number of pending items in the queue."""
        return self._queue.qsize()

    async def _worker(self) -> None:
        """
        Background worker task that processes items sequentially.

        This runs in a loop, processing items one at a time from the queue.
        Processing is sequential to ensure FIFO ordering.

        Error Handling:
            - Processor exceptions are logged and don't stop the worker
            - Worker continues processing remaining items
            - Graceful shutdown on CancelledError
        """
        logger.info(f"{self._name} worker started")

        while self._running:
            try:
                # Wait for an item from the queue (blocks until one is available)
                queue_item = await self._queue.get()

                # Process the item (sync or async based on processor type)
                try:
                    if self._is_async_processor:
                        # Type checked: we know this is a coroutine function
                        await self._processor(queue_item.payload)  # type: ignore[misc]
                    else:
                        # Type checked: we know this is a regular function
                        self._processor(queue_item.payload)
                except Exception as e:
                    logger.error(f"Error in {self._name} processor: {e}", exc_info=True)
                    # Continue processing other items even if one fails

                # Mark the item as done
                self._queue.task_done()

            except asyncio.CancelledError:
                logger.info(f"{self._name} worker task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in {self._name} worker loop: {e}", exc_info=True)
                # Try to mark task done even if error occurred
                try:
                    self._queue.task_done()
                except ValueError:
                    # task_done() called more times than items in queue
                    pass

        logger.info(f"{self._name} worker stopped")

    async def wait_until_empty(self, timeout: float | None = None) -> bool:
        """
        Wait until all queued items have been processed.

        Useful for graceful shutdown or testing.

        Args:
            timeout: Maximum time to wait in seconds. None = wait forever.

        Returns:
            True if queue became empty, False if timeout occurred

        Example:
            ```python
            # Enqueue items
            await processor.enqueue(item1)
            await processor.enqueue(item2)

            # Wait for processing to complete
            if await processor.wait_until_empty(timeout=5.0):
                print("All items processed")
            else:
                print("Timeout waiting for queue to empty")
            ```
        """
        try:
            await asyncio.wait_for(self._queue.join(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logger.warning(f"{self._name}: Timeout waiting for queue to empty")
            return False
