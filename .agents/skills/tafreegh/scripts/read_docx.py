import sys
import zipfile
import xml.etree.ElementTree as ET

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def extract_text(docx_path):
    try:
        with zipfile.ZipFile(docx_path) as z:
            xml_content = z.read('word/document.xml')
        root = ET.fromstring(xml_content)
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        
        paragraphs = []
        for p in root.iterfind('.//w:p', ns):
            para_text = ""
            currently_bold = False
            for r in p.iterfind('.//w:r', ns):
                # Check if this run is bold
                is_bold = False
                rPr = r.find('w:rPr', ns)
                if rPr is not None:
                    b = rPr.find('w:b', ns)
                    bCs = rPr.find('w:bCs', ns)
                    if b is not None:
                        val = b.get(f"{{{ns['w']}}}val")
                        if val not in ['0', 'false', 'False', 'off']:
                            is_bold = True
                    if bCs is not None:
                        val = bCs.get(f"{{{ns['w']}}}val")
                        if val not in ['0', 'false', 'False', 'off']:
                            is_bold = True
                
                texts = [node.text for node in r.iterfind('.//w:t', ns) if node.text]
                run_text = "".join(texts)
                if run_text:
                    if is_bold and not currently_bold:
                        para_text += "**"
                        currently_bold = True
                    elif not is_bold and currently_bold:
                        para_text += "**"
                        currently_bold = False
                    
                    para_text += run_text
            
            if currently_bold:
                para_text += "**"
                
            paragraphs.append(para_text)
            
        text = "\n\n".join(paragraphs)
        text = text.replace("** **", " ")
        text = text.replace("****", "")
        return text.strip()
    except Exception as e:
        return f"Error reading docx: {e}"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: py read_docx.py <path_to_docx>")
        sys.exit(1)
    print(extract_text(sys.argv[1]))