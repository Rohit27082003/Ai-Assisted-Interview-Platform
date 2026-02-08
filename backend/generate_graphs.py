import os
import sys

# Add backend to path so imports work
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.services.graphs.interview_graph import build_interview_graph
from app.services.graphs.reporting import build_reporting_graph
from app.services.graphs.jd_intelligence import build_jd_intelligence_graph
from app.services.graphs.resume_intelligence import build_resume_intelligence_graph

OUTPUT_DIR = "backend/graph_visuals"

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

def generate_visual(name, graph_builder):
    print(f"Generating visual for {name}...")
    try:
        # Check if it needs arguments
        try:
             graph = graph_builder()
        except TypeError:
             # handle interview graph which might take optional args but has defaults?
             # actually build_interview_graph takes optional checkpointer, so calling with () should work.
             # but let's be safe.
             graph = graph_builder()
        
        png_data = graph.get_graph().draw_mermaid_png()
        
        output_path = os.path.join(OUTPUT_DIR, f"{name}.png")
        with open(output_path, "wb") as f:
            f.write(png_data)
        
        print(f"Saved to {output_path}")
    except Exception as e:
        print(f"Failed to generate {name}: {e}")
        import traceback
        traceback.print_exc()

def main():
    print("Starting graph generation...")
    
    generate_visual("interview_graph", build_interview_graph)
    generate_visual("reporting_graph", build_reporting_graph)
    generate_visual("jd_intelligence_graph", build_jd_intelligence_graph)
    generate_visual("resume_intelligence_graph", build_resume_intelligence_graph)
    
    print("Done.")

if __name__ == "__main__":
    main()
