
import sys
import os
from docx import Document

def read_docx(file_path):
    try:
        doc = Document(file_path)
        full_text = []
        for para in doc.paragraphs:
            if para.text.strip():
                full_text.append(para.text)
        return '\n'.join(full_text)
    except Exception as e:
        return f"Error reading file: {str(e)}"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python read_docx.py <path_to_docx>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    content = read_docx(file_path)
    with open("problem_statement.txt", "w") as f:
        f.write(content)
    print("Content written to problem_statement.txt")
