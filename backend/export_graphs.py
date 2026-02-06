
import os
import sys
import asyncio

# Add backend to path to allow imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.graphs.resume_intelligence import build_resume_intelligence_graph
from app.services.graphs.reporting import build_reporting_graph
from app.services.graphs.orchestrator import build_orchestrator_graph
from app.services.graphs.interview_orchestration import build_interview_graph
from app.services.graphs.jd_intelligence import build_jd_intelligence_graph
from app.services.graphs.focus_area import build_focus_area_graph
from app.services.graphs.evaluation import build_evaluation_graph

OUTPUT_DIR = "graph_visualizations"
os.makedirs(OUTPUT_DIR, exist_ok=True)

graphs = {
    "resume_intelligence": build_resume_intelligence_graph(),
    "reporting": build_reporting_graph(),
    "orchestrator": build_orchestrator_graph(),
    "interview_orchestration": build_interview_graph(),
    "jd_intelligence": build_jd_intelligence_graph(),
    "focus_area": build_focus_area_graph(),
    "evaluation": build_evaluation_graph(),
}

def export_graphs():
    print(f"Exporting graphs to {OUTPUT_DIR}...")
    
    for name, graph in graphs.items():
        print(f"Processing {name}...")
        try:
            # Generate Mermaid syntax
            mermaid_code = graph.get_graph().draw_mermaid()
            mermaid_path = f"{OUTPUT_DIR}/{name}.mermaid"
            with open(mermaid_path, "w") as f:
                f.write(mermaid_code)
            print(f"  - Saved Mermaid syntax: {mermaid_path}")
            
            # Try to generate PNG
            try:
                png_data = graph.get_graph().draw_mermaid_png()
                png_path = f"{OUTPUT_DIR}/{name}.png"
                with open(png_path, "wb") as f:
                    f.write(png_data)
                print(f"  - Saved PNG: {png_path}")
            except Exception as e:
                print(f"  - Could not generate PNG automatically: {e}")
                print(f"    (You can copy the content of {mermaid_path} to https://mermaid.live to visualize it)")

        except Exception as e:
            print(f"Failed to export {name}: {e}")

    print("Export complete.")

if __name__ == "__main__":
    export_graphs()
