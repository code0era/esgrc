import streamlit as st
import os
import time

def init_pipeline_state(pipeline_key: str, total_steps: int):
    """Initializes the UI states for a progressive pipeline."""
    if pipeline_key not in st.session_state:
        st.session_state[pipeline_key] = {i: "pending" for i in range(1, total_steps + 1)}

def reset_pipeline_from(pipeline_key: str, step_num: int, total_steps: int):
    """Resets the state of a step and all subsequent steps to 'pending'."""
    for i in range(step_num, total_steps + 1):
        st.session_state[pipeline_key][i] = "pending"
    st.rerun()

def complete_step(pipeline_key: str, step_num: int, outputs: dict):
    """Marks a step as complete and stores its outputs."""
    st.session_state[pipeline_key][step_num] = "completed"
    st.session_state[f"{pipeline_key}_out_{step_num}"] = outputs
    st.rerun()


def _display_step_outputs(pipeline_key: str, step_num: int, outputs: dict):
    """Read and render every output file produced by a step directly in the UI."""
    work_dir = st.session_state.get(f"{pipeline_key}_work_dir", "")

    files = outputs.get("files", [])
    if not files:
        return

    for filepath in files:
        if not filepath:
            continue

        # Resolve full path
        if not os.path.isabs(filepath):
            full_path = os.path.join(work_dir, filepath) if work_dir else filepath
        else:
            full_path = filepath

        fname = os.path.basename(full_path)

        if not os.path.exists(full_path):
            st.warning(f"⚠️ File not found: `{fname}`")
            continue

        # ── TXT: show content inline as markdown ──────────────────────────────
        if fname.endswith(".txt"):
            with open(full_path, "r", encoding="utf-8", errors="replace") as rf:
                content = rf.read()
            if content.strip():
                st.markdown(f"---\n**📄 {fname}**")
                st.markdown(content)
            else:
                st.warning(f"⚠️ `{fname}` is empty.")

        # ── PDF: offer download button ────────────────────────────────────────
        elif fname.endswith(".pdf"):
            with open(full_path, "rb") as pf:
                pdf_bytes = pf.read()
            st.download_button(
                label=f"⬇️ Download {fname}",
                data=pdf_bytes,
                file_name=fname,
                mime="application/pdf",
                key=f"dl_{pipeline_key}_{step_num}_{fname}"
            )

        # ── CSV: show first 100 rows as dataframe ────────────────────────────
        elif fname.endswith(".csv"):
            import pandas as pd
            try:
                df = pd.read_csv(full_path, nrows=100)
                st.markdown(f"**📊 {fname}** (first 100 rows)")
                st.dataframe(df, use_container_width=True)
            except Exception:
                st.markdown(f"- `{fname}`")

        else:
            st.markdown(f"- `{fname}`")


def render_pipeline_step(
    pipeline_key: str,
    step_num: int,
    total_steps: int,
    title: str,
    description: str,
    render_inputs_func,  # A function that renders the form/inputs and returns (True, input_kwargs) when ready to run
    run_func,            # The actual engine function to run with the inputs
):
    """
    Renders a single step in a progressive pipeline.
    If the previous step is not completed, this step is hidden.
    """
    state = st.session_state.get(pipeline_key, {}).get(step_num, "pending")
    prev_state = "completed" if step_num == 1 else st.session_state.get(pipeline_key, {}).get(step_num - 1, "pending")

    if prev_state != "completed":
        return  # Hide if previous step is not done

    st.markdown(f"<h3 style='color: #162130; margin-top: 1rem;'>Step {step_num}: {title}</h3>", unsafe_allow_html=True)

    if state == "completed":
        outputs = st.session_state.get(f"{pipeline_key}_out_{step_num}", {})

        with st.expander(f"✅ Step {step_num} Completed", expanded=True):
            st.success("Analysis complete.")

            if "msg" in outputs:
                st.info(outputs["msg"])

            # ── Render all output files inline ────────────────────────────────
            _display_step_outputs(pipeline_key, step_num, outputs)

            if st.button(f"Re-run Step {step_num}", key=f"rerun_{pipeline_key}_{step_num}"):
                reset_pipeline_from(pipeline_key, step_num, total_steps)

    elif state == "pending":
        st.markdown(f"<p style='color:#64748B;'>{description}</p>", unsafe_allow_html=True)
        # Render the input UI
        ready_to_run, kwargs = render_inputs_func()

        if ready_to_run:
            if step_num == 1:
                btn_label = "Run Full Pipeline →" if total_steps > 1 else "Run Step 1 →"
                if st.button(btn_label, type="primary", use_container_width=True, key=f"run_{pipeline_key}_{step_num}"):
                    with st.spinner(f"Processing Step {step_num}..."):
                        success, results, msg = run_func(**kwargs)
                        if success:
                            results["msg"] = msg
                            complete_step(pipeline_key, step_num, results)
                        else:
                            st.error(msg)
            else:
                # Auto-run subsequent steps without button click
                with st.spinner(f"Automating Step {step_num}..."):
                    success, results, msg = run_func(**kwargs)
                    if success:
                        results["msg"] = msg
                        complete_step(pipeline_key, step_num, results)
                    else:
                        st.error(msg)

    st.markdown("<hr style='border: 1px solid rgba(0,0,0,0.1); margin-top: 1.5rem; margin-bottom: 1.5rem;'/>", unsafe_allow_html=True)
