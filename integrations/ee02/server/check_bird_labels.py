import ast
from pathlib import Path
from playwright.sync_api import sync_playwright
src=Path('/opt/bird-renderer/avian-visitors/frame/shoot.py').read_text()
strings=[n.value for n in ast.walk(ast.parse(src)) if isinstance(n,ast.Constant) and isinstance(n.value,str)]
validate=next(s for s in strings if 'const errors = []' in s and 'getExtentOfChar' in s)
fix=next(s for s in strings if "btn.querySelectorAll('.gtile-label')" in s)
with sync_playwright() as p:
 b=p.chromium.launch(headless=True)
 page=b.new_page(viewport={'width':600,'height':800})
 page.set_content('''<div id="tile"><svg class="gtile-label" width="300" height="100"><path id="test" d="M100 60 L140 60"/><text style="font:24px serif"><textPath href="#test" startOffset="50%" text-anchor="middle">Cedar Waxwing</textPath></text></svg></div>''')
 before=page.evaluate(validate)
 assert before, 'Guard must reject truncated long label'
 page.evaluate('() => {const btn=document.querySelector("#tile");'+fix+'}')
 after=page.evaluate(validate)
 assert not after, after
 page.eval_on_selector('#tile','e => e.style.transform="translateX(-130px)"')
 assert page.evaluate(validate), 'Guard must reject offscreen glyphs'
 print('PASS: detects path truncation; fitted Cedar Waxwing retains every glyph; detects viewport clipping')
 b.close()
