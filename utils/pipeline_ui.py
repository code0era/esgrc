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
                st.info(outputs[f"msg"])

            # ── Download buttons + Re-run in a single row ──────────────────
            files = outputs.get("files", [])
            work_dir = st.session_state.get(f"{pipeline_key}_work_dir", "")

            # Collect downloadable files (PDF and CSV only)
            downloadable = []
            for fpath in files:
                if not fpath:
                    continue
                full_path = fpath if os.path.isabs(fpath) else (
                    os.path.join(work_dir, fpath) if work_dir else fpath
                )
                if os.path.exists(full_path):
                    fname = os.path.basename(full_path)
                    if fname.lower().endswith(".pdf"):
                        downloadable.append((full_path, fname, "application/pdf", "📄"))
                    elif fname.lower().endswith(".csv"):
                        downloadable.append((full_path, fname, "text/csv", "📊"))
                    elif fname.lower().endswith(".txt"):
                        downloadable.append((full_path, fname, "text/plain", "📝"))

            # Lay out: [Re-run] [Download A] [Download B] …
            n_cols = 1 + len(downloadable)
            cols = st.columns([2] + [1.5] * len(downloadable))

            with cols[0]:
                if st.button(f"Re-run Step {step_num}", key=f"rerun_{pipeline_key}_{step_num}"):
                    reset_pipeline_from(pipeline_key, step_num, total_steps)

            for idx, (full_path, fname, mime, icon) in enumerate(downloadable):
                with cols[idx + 1]:
                    try:
                        mode = "rb" if mime == "application/pdf" else "r"
                        encoding = None if mime == "application/pdf" else "utf-8"
                        with open(full_path, mode, **({"encoding": encoding} if encoding else {})) as df:
                            file_bytes = df.read()
                        if isinstance(file_bytes, str):
                            file_bytes = file_bytes.encode("utf-8")
                        st.download_button(
                            label=f"{icon} {fname}",
                            data=file_bytes,
                            file_name=fname,
                            mime=mime,
                            key=f"dl_{pipeline_key}_{step_num}_{fname}",
                            use_container_width=True,
                        )
                    except Exception:
                        pass


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
            elif step_num == total_steps:
                # The last step is the AI step, make it manual
                btn_label = f"✨ Generate AI Executive Summary (Step {step_num})"
                if st.button(btn_label, type="primary", use_container_width=True, key=f"run_{pipeline_key}_{step_num}"):
                    with st.spinner(f"Generating AI Summary (This uses API credits)..."):
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
