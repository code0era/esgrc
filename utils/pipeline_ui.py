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
        return # Hide if previous step is not done
        
    st.markdown(f"<h3 style='color: #0D6F73;'>Step {step_num}: {title}</h3>", unsafe_allow_html=True)
    
    if state == "completed":
        # Greyed out completed band
        with st.expander(f"✅ Step {step_num} Completed", expanded=False):
            st.success("Analysis complete.")
            outputs = st.session_state.get(f"{pipeline_key}_out_{step_num}", {})
            if "files" in outputs:
                st.markdown("**Generated Files:**")
                for f in outputs["files"]:
                    st.markdown(f"- `{f}`")
            if "msg" in outputs:
                st.info(outputs["msg"])
                
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
    
    st.markdown("<hr style='border: 1px solid #E0EDE9;'/>", unsafe_allow_html=True)
