"""Starter project templates for "Create Project" (blank, modern, dashboard, calculator)."""
import os


def blank(path):
    """Create the blank template files"""
    html = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>My App</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<h1>Welcome to My App</h1>
<p>Start building your application here.</p>
<script src="script.js"></script>
</body>
</html>'''
    
    css = '''body {
font-family: Arial, sans-serif;
max-width: 800px;
margin: 0 auto;
padding: 20px;
background: #f5f5f5;
}

h1 {
color: #333;
}

p {
color: #666;
line-height: 1.6;
}'''
    
    js = '''console.log("App loaded!");'''
    
    with open(os.path.join(path, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(html)
    with open(os.path.join(path, 'style.css'), 'w', encoding='utf-8') as f:
        f.write(css)
    with open(os.path.join(path, 'script.js'), 'w', encoding='utf-8') as f:
        f.write(js)

def modern(path):
    """Create modern template with beautiful UI"""
    blank(path)  # base style.css / script.js; the index.html below replaces blank's
    # Similar to sample_project - create files for modern design
    html = '''<!DOCTYPE html>
<html>
<head>
<title>Modern App</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="container">
    <header><h1>🎨 Modern Application</h1></header>
    <main>
        <section class="card">
            <h2>Beautiful Design</h2>
            <p>A modern, responsive application built with HTML5 and CSS3.</p>
        </section>
    </main>
</div>
<script src="script.js"></script>
</body>
</html>'''
    
    with open(os.path.join(path, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(html)
    

def dashboard(path):
    """Create dashboard template"""
    blank(path)  # base style.css / script.js; the index.html below replaces blank's
    html = '''<!DOCTYPE html>
<html>
<head>
<title>Dashboard</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="dashboard">
    <h1>📊 Dashboard</h1>
    <div class="widgets">
        <div class="widget"><h3>Widget 1</h3><p>Data here</p></div>
        <div class="widget"><h3>Widget 2</h3><p>Data here</p></div>
    </div>
</div>
<script src="script.js"></script>
</body>
</html>'''
    
    with open(os.path.join(path, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(html)
    

def calculator(path):
    """Create calculator template"""
    blank(path)  # base style.css / script.js; the index.html below replaces blank's
    html = '''<!DOCTYPE html>
<html>
<head>
<title>Calculator</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="calculator">
    <div class="display" id="display">0</div>
    <div class="buttons">
        <button onclick="clear_display()">C</button>
        <button onclick="append_operator('/')">/</button>
        <button onclick="append_operator('*')">*</button>
        <button onclick="delete_last()">←</button>
        
        <button onclick="append_number('7')">7</button>
        <button onclick="append_number('8')">8</button>
        <button onclick="append_number('9')">9</button>
        <button onclick="append_operator('-')">-</button>
        
        <button onclick="append_number('4')">4</button>
        <button onclick="append_number('5')">5</button>
        <button onclick="append_number('6')">6</button>
        <button onclick="append_operator('+')">+</button>
        
        <button onclick="append_number('1')">1</button>
        <button onclick="append_number('2')">2</button>
        <button onclick="append_number('3')">3</button>
        <button onclick="calculate()" class="equals">=</button>
        
        <button onclick="append_number('0')" class="zero">0</button>
        <button onclick="append_number('.')">.</button>
    </div>
</div>
<script src="script.js"></script>
</body>
</html>'''
    
    with open(os.path.join(path, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(html)
    


TEMPLATES = {'blank': blank, 'modern': modern, 'dashboard': dashboard, 'calculator': calculator}


def write_template(path, template='blank'):
    """Write the starter files of ``template`` into ``path`` (unknown names fall back to blank)."""
    os.makedirs(path, exist_ok=True)
    TEMPLATES.get(template, blank)(path)
