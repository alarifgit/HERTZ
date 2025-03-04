# hertz/services/api_queue.py
import asyncio
import logging
from typing import Callable, TypeVar, Any, Awaitable

logger = logging.getLogger(__name__)
T = TypeVar('T')

class AsyncRequestQueue:
    """
    Queue for limiting concurrent API requests to avoid rate limits
    
    This class helps prevent sending too many requests at once to an API
    by limiting the number of concurrent operations. It's especially useful
    for services like YouTube API which have strict rate limits.
    """
    
    def __init__(self, concurrency: int = 4):
        """
        Initialize the queue with a concurrency limit
        
        Args:
            concurrency: Maximum number of concurrent requests
        """
        self.semaphore = asyncio.Semaphore(concurrency)
        self.active_tasks = 0
    
    async def add(self, func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        """
        Add a function to the queue and execute it when a slot is available
        
        Args:
            func: Async function to execute
            *args: Arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function
            
        Returns:
            The result of the function call
        """
        async with self.semaphore:
            self.active_tasks += 1
            logger.debug(f"Starting API task ({self.active_tasks} active)")
            try:
                return await func(*args, **kwargs)
            finally:
                self.active_tasks -= 1
                logger.debug(f"Finished API task ({self.active_tasks} active)")
    
    async def add_batch(self, func: Callable[..., Awaitable[T]], args_list: list[tuple], **common_kwargs: Any) -> list[T]:
        """
        Process a batch of requests through the queue
        
        Args:
            func: Async function to execute for each item
            args_list: List of argument tuples to pass to the function
            **common_kwargs: Common keyword arguments to pass to all function calls
            
        Returns:
            List of results from all function calls
        """
        tasks = []
        for args in args_list:
            task = self.add(func, *args, **common_kwargs)
            tasks.append(task)
        
        return await asyncio.gather(*tasks, return_exceptions=True)