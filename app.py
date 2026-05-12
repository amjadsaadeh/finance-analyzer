import gradio as gr
from agents import Runner

from src.agent import finance_agent
from src.approval import format_approval_preview
from tools import FireflyClient


async def _chat_fn(message: str, history: list[dict], firefly_state, pending_state):
    if firefly_state is None:
        try:
            firefly_state = FireflyClient()
        except ValueError as e:
            yield (
                history + [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": f"Configuration error: {e}"},
                ],
                firefly_state,
                pending_state,
                gr.update(visible=False),
                "",
            )
            return

    agent_messages = list(history) + [{"role": "user", "content": message}]
    partial = list(agent_messages)
    result = Runner.run_streamed(finance_agent, agent_messages, context=firefly_state)
    assistant_text = ""

    async for event in result.stream_events():
        if event.type == "raw_response_event":
            raw = event.data
            if getattr(raw, "type", "") == "response.output_text.delta":
                delta = getattr(raw, "delta", "")
                if delta:
                    assistant_text += delta
                    yield (
                        partial + [{"role": "assistant", "content": assistant_text}],
                        firefly_state,
                        None,
                        gr.update(visible=False),
                        "",
                    )

    run_state = result.to_state()
    interruptions = run_state.get_interruptions()

    if interruptions:
        preview = format_approval_preview(interruptions)
        preview_md = "\n".join(f"- {p['summary']}" for p in preview["previews"])
        yield (
            partial + [{"role": "assistant", "content": "I want to make the following changes — please approve or reject:"}],
            firefly_state,
            run_state,
            gr.update(visible=True),
            preview_md,
        )
    else:
        final = str(getattr(result, "final_output", "") or assistant_text)
        yield (
            partial + [{"role": "assistant", "content": final}],
            firefly_state,
            None,
            gr.update(visible=False),
            "",
        )


async def _do_approval(history, firefly_state, pending_state, approved: bool):
    if pending_state is None:
        return history, None, gr.update(visible=False)

    for interruption in pending_state.get_interruptions():
        if approved:
            pending_state.approve(interruption)
        else:
            pending_state.reject(interruption)

    result = await Runner.run(finance_agent, pending_state, context=firefly_state)
    response = str(getattr(result, "final_output", ""))
    return (
        history + [{"role": "assistant", "content": response}],
        None,
        gr.update(visible=False),
    )


async def _on_approve(history, firefly_state, pending_state):
    return await _do_approval(history, firefly_state, pending_state, approved=True)


async def _on_reject(history, firefly_state, pending_state):
    return await _do_approval(history, firefly_state, pending_state, approved=False)


with gr.Blocks(title="Finance Analyzer") as demo:
    gr.Markdown("# Finance Analyzer\nAsk questions about your Firefly III finances.")

    chatbot = gr.Chatbot(type="messages", height=500, label="Conversation")
    firefly_st = gr.State(None)
    pending_st = gr.State(None)

    with gr.Group(visible=False) as approval_panel:
        gr.Markdown("### Pending changes")
        approval_preview = gr.Markdown("")
        with gr.Row():
            approve_btn = gr.Button("Approve", variant="primary")
            reject_btn = gr.Button("Reject", variant="stop")

    with gr.Row():
        msg_box = gr.Textbox(
            placeholder="Ask about your finances...",
            show_label=False,
            scale=4,
        )
        send_btn = gr.Button("Send", scale=1, variant="primary")

    chat_inputs = [msg_box, chatbot, firefly_st, pending_st]
    chat_outputs = [chatbot, firefly_st, pending_st, approval_panel, approval_preview]
    approval_inputs = [chatbot, firefly_st, pending_st]
    approval_outputs = [chatbot, pending_st, approval_panel]

    send_btn.click(_chat_fn, chat_inputs, chat_outputs).then(lambda: "", outputs=msg_box)
    msg_box.submit(_chat_fn, chat_inputs, chat_outputs).then(lambda: "", outputs=msg_box)
    approve_btn.click(_on_approve, approval_inputs, approval_outputs)
    reject_btn.click(_on_reject, approval_inputs, approval_outputs)
