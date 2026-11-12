import time
from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableConfig
from loguru import logger
from surreal_commands import CommandInput, CommandOutput, command

from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.notebook import Source
from open_notebook.domain.transformation import Transformation
from open_notebook.exceptions import ConfigurationError, ContextLengthExceededError
from open_notebook.utils.job_input_guard import (
    UnsafeJobInput,
    require_record_id,
    same_upload,
)

try:
    from open_notebook.graphs.source import source_graph
    from open_notebook.graphs.transformation import graph as transform_graph
except ImportError as e:
    logger.error(f"Failed to import graphs: {e}")
    raise ValueError("graphs not available")


def _bind_content_to_source(content_state: Dict[str, Any], source: Source) -> None:
    """The file/URL processed must be the one recorded on the source itself.

    Stops a job from pointing an existing source at another file or URL (e.g.
    reading an arbitrary uploaded file into someone else's source).
    """
    asset = getattr(source, "asset", None)
    file_path = content_state.get("file_path")
    url = content_state.get("url")
    if file_path and not same_upload(file_path, getattr(asset, "file_path", None)):
        raise UnsafeJobInput("file_path does not match the source's uploaded file.")
    if url and url != getattr(asset, "url", None):
        raise UnsafeJobInput("url does not match the source's URL.")


class SourceProcessingInput(CommandInput):
    source_id: str
    content_state: Dict[str, Any]
    notebook_ids: List[str]
    transformations: List[str]
    embed: bool


class SourceProcessingOutput(CommandOutput):
    success: bool
    source_id: str
    embedded_chunks: int = 0
    insights_created: int = 0
    processing_time: float
    error_message: Optional[str] = None


@command(
    "process_source",
    app="open_notebook",
    retry={
        "max_attempts": 15,  # Handle deep queues (workaround for SurrealDB v2 transaction conflicts)
        "wait_strategy": "exponential_jitter",
        "wait_min": 1,
        "wait_max": 120,  # Allow queue to drain
        "stop_on": [
            ValueError,
            ConfigurationError,
            ContextLengthExceededError,
        ],  # Don't retry validation/config errors
        "retry_log_level": "debug",  # Avoid log noise during transaction conflicts
    },
)
async def process_source_command(
    input_data: SourceProcessingInput,
) -> SourceProcessingOutput:
    """
    Process source content using the source_graph workflow
    """
    start_time = time.time()

    try:
        logger.info(f"Starting source processing for source: {input_data.source_id}")
        logger.info(f"Notebook IDs: {input_data.notebook_ids}")
        logger.info(f"Transformations: {input_data.transformations}")
        logger.info(f"Embed: {input_data.embed}")

        # 0. Validate job input against the records it claims to process
        # (docs/security/BACKGROUND_JOB_SECURITY.md). Applies to every caller.
        require_record_id(input_data.source_id, "source")
        for nb_id in input_data.notebook_ids:
            require_record_id(nb_id, "notebook")
        for trans_id in input_data.transformations:
            require_record_id(trans_id, "transformation")
        allowed_keys = {"url", "file_path", "content", "delete_source"}
        unknown = set(input_data.content_state) - allowed_keys
        if unknown:
            raise UnsafeJobInput(f"Unsupported content_state keys: {sorted(unknown)}")

        # 1. Load transformation objects from IDs
        transformations = []
        for trans_id in input_data.transformations:
            logger.info(f"Loading transformation: {trans_id}")
            transformation = await Transformation.get(trans_id)
            if not transformation:
                raise ValueError(f"Transformation '{trans_id}' not found")
            transformations.append(transformation)

        logger.info(f"Loaded {len(transformations)} transformations")

        # 2. Get existing source record to update its command field
        source = await Source.get(input_data.source_id)
        if not source:
            raise ValueError(f"Source '{input_data.source_id}' not found")
        _bind_content_to_source(input_data.content_state, source)

        # Update source with command reference
        source.command = (
            ensure_record_id(input_data.execution_context.command_id)
            if input_data.execution_context
            else None
        )
        await source.save()

        logger.info(f"Updated source {source.id} with command reference")

        # 3. Process source with all notebooks
        logger.info(f"Processing source with {len(input_data.notebook_ids)} notebooks")

        # Execute source_graph with all notebooks.
        # LangGraph accepts a partial state dict at runtime, but its typed
        # overloads require the full state type (langgraph typing limitation).
        result = await source_graph.ainvoke(  # type: ignore[call-overload]
            {
                "content_state": input_data.content_state,
                "notebook_ids": input_data.notebook_ids,  # Use notebook_ids (plural) as expected by SourceState
                "apply_transformations": transformations,
                "embed": input_data.embed,
                "source_id": input_data.source_id,  # Add the source_id to the state
            }
        )

        processed_source = result["source"]

        # 4. Gather processing results (notebook associations handled by source_graph)
        # Note: embedding is fire-and-forget (async job), so we can't query the
        # count here — it hasn't completed yet. The embed_source_command logs
        # the actual count when it finishes.
        insights_list = await processed_source.get_insights()
        insights_created = len(insights_list)

        processing_time = time.time() - start_time
        embed_status = "submitted" if input_data.embed else "skipped"
        logger.info(
            f"Successfully processed source: {processed_source.id} in {processing_time:.2f}s"
        )
        logger.info(f"Created {insights_created} insights, embedding {embed_status}")

        return SourceProcessingOutput(
            success=True,
            source_id=str(processed_source.id),
            embedded_chunks=0,
            insights_created=insights_created,
            processing_time=processing_time,
        )

    except ValueError as e:
        # Validation errors are permanent failures. Re-raise so surreal-commands
        # marks the job as `failed` (stop_on=[ValueError] already prevents
        # pointless retries). Returning a success=False result instead marks the
        # job `completed` (is_success() checks job status, not the payload),
        # which hid extraction failures and left the source without a retryable
        # `failed` status in the UI.
        logger.error(f"Source processing failed (permanent): {e}")
        raise
    except Exception as e:
        # The source can be deleted while this job runs (a reviewer rejecting a
        # submission deletes it, file included). Every later step then fails,
        # and retrying 15 times would only re-run the extraction against a
        # record that is gone - so treat it as a permanent failure.
        if await _source_is_gone(input_data.source_id):
            logger.info(
                f"Source {input_data.source_id} was deleted while processing; "
                "stopping without retry"
            )
            raise ValueError(
                f"Source '{input_data.source_id}' was deleted while processing"
            ) from e
        # Transient failure - will be retried (surreal-commands logs final failure)
        logger.debug(f"Transient error processing source {input_data.source_id}: {e}")
        raise


async def _source_is_gone(source_id: str) -> bool:
    """True only when the DB positively reports the source no longer exists.
    Any lookup error counts as "still there", so real outages keep retrying."""
    try:
        rows = await repo_query(
            "SELECT VALUE id FROM $id", {"id": ensure_record_id(source_id)}
        )
        return not rows
    except Exception:
        return False


# =============================================================================
# RUN TRANSFORMATION COMMAND
# =============================================================================


class RunTransformationInput(CommandInput):
    """Input for running a transformation on an existing source."""

    source_id: str
    transformation_id: str


class RunTransformationOutput(CommandOutput):
    """Output from transformation command."""

    success: bool
    source_id: str
    transformation_id: str
    processing_time: float
    error_message: Optional[str] = None


@command(
    "run_transformation",
    app="open_notebook",
    retry={
        "max_attempts": 5,
        "wait_strategy": "exponential_jitter",
        "wait_min": 1,
        "wait_max": 60,
        "stop_on": [
            ValueError,
            ConfigurationError,
            ContextLengthExceededError,
        ],  # Don't retry validation/config errors
        "retry_log_level": "warning",
    },
)
async def run_transformation_command(
    input_data: RunTransformationInput,
) -> RunTransformationOutput:
    """
    Run a transformation on an existing source to generate an insight.

    This command runs the transformation graph which:
    1. Loads the source and transformation
    2. Calls the LLM to generate insight content
    3. Creates the insight via create_insight command (fire-and-forget)

    Use this command for UI-triggered insight generation to avoid blocking
    the HTTP request while the LLM processes.

    Retry Strategy:
    - Retries up to 5 times for transient failures (network, timeout, etc.)
    - Uses exponential-jitter backoff (1-60s)
    - Does NOT retry permanent failures (ValueError for validation errors)
    """
    start_time = time.time()
    # Job input is never trusted (docs/security/BACKGROUND_JOB_SECURITY.md).
    require_record_id(input_data.source_id, "source")
    require_record_id(input_data.transformation_id, "transformation")

    try:
        logger.info(
            f"Running transformation {input_data.transformation_id} "
            f"on source {input_data.source_id}"
        )

        # Load source
        source = await Source.get(input_data.source_id)
        if not source:
            raise ValueError(f"Source '{input_data.source_id}' not found")

        # Load transformation
        transformation = await Transformation.get(input_data.transformation_id)
        if not transformation:
            raise ValueError(
                f"Transformation '{input_data.transformation_id}' not found"
            )

        # Run transformation graph (includes LLM call + insight creation).
        # LangGraph accepts a partial state dict at runtime, but its typed
        # overloads require the full state type (langgraph typing limitation).
        await transform_graph.ainvoke(  # type: ignore[call-overload]
            input=dict(source=source, transformation=transformation),
            config=RunnableConfig(configurable={"model_id": transformation.model_id}),
        )

        processing_time = time.time() - start_time
        logger.info(
            f"Successfully ran transformation {input_data.transformation_id} "
            f"on source {input_data.source_id} in {processing_time:.2f}s"
        )

        return RunTransformationOutput(
            success=True,
            source_id=input_data.source_id,
            transformation_id=input_data.transformation_id,
            processing_time=processing_time,
        )

    except ValueError as e:
        # Validation errors are permanent failures - don't retry
        processing_time = time.time() - start_time
        logger.error(
            f"Failed to run transformation {input_data.transformation_id} "
            f"on source {input_data.source_id}: {e}"
        )
        return RunTransformationOutput(
            success=False,
            source_id=input_data.source_id,
            transformation_id=input_data.transformation_id,
            processing_time=processing_time,
            error_message=str(e),
        )
    except Exception as e:
        # Transient failure - will be retried (surreal-commands logs final failure)
        logger.debug(
            f"Transient error running transformation {input_data.transformation_id} "
            f"on source {input_data.source_id}: {e}"
        )
        raise
