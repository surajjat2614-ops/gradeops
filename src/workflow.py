
from langgraph.graph import StateGraph, END
from state import GradeOpsState         
from rubric_factory import generate_rubric
from grader import grading_node

def rubric_node(state: GradeOpsState):
    rubric = generate_rubric(state["question_text"], state["marking_scheme_text"])
    if rubric is None:
        raise ValueError("Rubric generation failed — check model output")
    return {"rubric": rubric}

def build_grading_graph():
    workflow = StateGraph(GradeOpsState)

    workflow.add_node("create_rubric", rubric_node)
    workflow.add_node("grade_paper", grading_node)

    workflow.set_entry_point("create_rubric")
    workflow.add_edge("create_rubric", "grade_paper")
    workflow.add_edge("grade_paper", END)

    return workflow.compile()
