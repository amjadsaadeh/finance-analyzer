import argparse
import logging
import os
from datetime import datetime
from dotenv import load_dotenv

from agents import add_trace_processor, set_default_openai_api
from agents.tracing import TracingProcessor, Span, Trace

load_dotenv(override=False)

# Use chat_completions API instead of responses API for compatibility with openai 2.34.0
set_default_openai_api("chat_completions")

# Set up logging for tracing
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("finance_analyzer.tracing")


class LoggingTracingProcessor(TracingProcessor):
    """Logs trace and span events to stdout."""

    def on_trace_start(self, trace: Trace) -> None:
        logger.info(f"TRACE START: {trace.name} (id: {trace.trace_id})")

    def on_trace_end(self, trace: Trace) -> None:
        logger.info(f"TRACE END: {trace.name} (id: {trace.trace_id})")

    def on_span_start(self, span: Span) -> None:
        span_data = span.span_data
        name = getattr(span_data, "name", span_data.type) if span_data else span_data.type
        logger.info(f"  SPAN START: {name} (id: {span.span_id})")

    def on_span_end(self, span: Span) -> None:
        span_data = span.span_data
        name = getattr(span_data, "name", span_data.type) if span_data else span_data.type
        # Calculate duration if both timestamps are datetime objects
        if isinstance(span.started_at, datetime) and isinstance(span.ended_at, datetime):
            duration = (span.ended_at - span.started_at).total_seconds()
            logger.info(f"  SPAN END: {name} (id: {span.span_id}, duration: {duration:.2f}s)")
        else:
            logger.info(f"  SPAN END: {name} (id: {span.span_id})")

    def shutdown(self) -> None:
        pass

    def force_flush(self) -> None:
        pass


# Add our logging processor
add_trace_processor(LoggingTracingProcessor())

from app import demo


def main():
    parser = argparse.ArgumentParser(description="Finance Analyzer")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="IP address to serve on")
    parser.add_argument("--port", type=int, default=7860, help="Port to serve on")
    args = parser.parse_args()
    demo.launch(server_name=args.host, server_port=args.port)


if __name__ == "__main__":
    main()
