# MS6/app/execution/builders/data_builder.py

from .base_builder import BaseBuilder
from app.execution.build_context import BuildContext
from app.internals.clients import DataServiceClient
from app.logging_config import logger
import asyncio

class DataBuilder(BaseBuilder):
    """
    Fetches and prepares on-the-fly data (e.g., user-uploaded files) by calling
    the Data Service (MS10) via gRPC. This builder runs early in the pipeline
    to gather context for subsequent steps.
    """
    def __init__(self):
        self.data_client = DataServiceClient()

    async def build(self, context: BuildContext) -> BuildContext:
        """
        If the job contains file inputs, this method calls the Data Service
        concurrently to retrieve the parsed content for all of them.
        """
        # If there are no inputs in the job, there's nothing to do.
        if not context.job.inputs:
            return context

        logger.info(f"[{context.job.id}] DataBuilder: Found {len(context.job.inputs)} input(s). Preparing to fetch content.")
        
        # Create a list of tasks for asyncio.gather to run concurrently.
        fetch_tasks = []
        for inp in context.job.inputs:
            # We only care about inputs of type 'file_id' that have an actual ID.
            if inp.get('type') == 'file_id' and inp.get('id'):
                task = self.data_client.get_file_content(
                    file_id=inp['id'], 
                    user_id=context.job.user_id
                )
                fetch_tasks.append(task)
        
        if not fetch_tasks:
            logger.info(f"[{context.job.id}] DataBuilder: No valid 'file_id' inputs found to process.")
            return context

        # Run all gRPC calls in parallel and wait for all of them to complete.
        results = await asyncio.gather(*fetch_tasks)
        
        # Store the list of parsed content dictionaries in the build context.
        # The PromptBuilder will use this data later.
        context.on_the_fly_data = results
        
        logger.info(f"[{context.job.id}] DataBuilder: Successfully fetched and parsed content for {len(results)} item(s).")
        return context